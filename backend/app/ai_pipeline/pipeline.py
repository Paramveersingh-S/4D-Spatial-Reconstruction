"""
End-to-End 4RC Pipeline Orchestrator.
Coordinates the full video → frames → inference → point cloud → trajectories pipeline.
Provides progress callbacks that update job status in real-time.
"""
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

from ..core.config import settings
from ..core.logging import get_logger
from ..services.storage import local_storage
from ..services import firebase_client

from .video_processor import VideoProcessor
from .inference import run_inference
from .point_cloud_generator import PointCloudGenerator
from .trajectory_extractor import TrajectoryExtractor

logger = get_logger("pipeline.orchestrator")


# ──────────────────────────────────────────────
# Pipeline Stage Definitions
# ──────────────────────────────────────────────

PIPELINE_STAGES = [
    {"name": "extracting_frames", "label": "Extracting video frames", "weight": 10},
    {"name": "extracting_flow", "label": "Computing optical flow & encoding", "weight": 15},
    {"name": "reconstructing_4d", "label": "Running 4RC 4D reconstruction", "weight": 40},
    {"name": "generating_point_cloud", "label": "Generating point cloud (PLY)", "weight": 20},
    {"name": "extracting_trajectories", "label": "Extracting motion trajectories", "weight": 10},
    {"name": "compiling_assets", "label": "Compiling & uploading final assets", "weight": 5},
]


async def _update_progress(
    video_id: str,
    stage_index: int,
    stage_name: str,
    sub_progress: float = 0.0,
) -> None:
    """Update job progress in both local storage and Firebase."""
    # Calculate overall progress
    total_weight = sum(s["weight"] for s in PIPELINE_STAGES)
    completed_weight = sum(PIPELINE_STAGES[i]["weight"] for i in range(stage_index))
    current_weight = PIPELINE_STAGES[stage_index]["weight"] if stage_index < len(PIPELINE_STAGES) else 0
    overall_progress = (completed_weight + current_weight * sub_progress / 100) / total_weight * 100

    updates = {
        "status": stage_name,
        "progress": round(overall_progress, 1),
        "current_step": PIPELINE_STAGES[stage_index]["label"] if stage_index < len(PIPELINE_STAGES) else "Complete",
        "steps_completed": stage_index,
    }

    await local_storage.update_job(video_id, updates)

    if firebase_client.is_firebase_connected():
        await firebase_client.update_job_status(
            video_id,
            status=stage_name,
            progress=round(overall_progress, 1),
            current_step=updates["current_step"],
            steps_completed=stage_index,
        )


async def run_full_pipeline(video_id: str) -> None:
    """
    Execute the complete 4RC reconstruction pipeline for a video.

    Stages:
        1. Extract frames from uploaded video
        2. Compute optical flow / encode video features
        3. Run 4RC model inference (depth, points, correspondences)
        4. Generate PLY point cloud
        5. Extract motion trajectories
        6. Compile and store final assets

    This function is designed to run as a FastAPI BackgroundTask.
    """
    pipeline_start = time.perf_counter()
    logger.info(f"{'='*60}")
    logger.info(f"  4RC Pipeline Started: {video_id}")
    logger.info(f"{'='*60}")

    try:
        # ── Get job metadata ──
        job = await local_storage.get_job(video_id)
        if not job:
            logger.error(f"Job not found: {video_id}")
            return

        filename = job.get("filename", "unknown.mp4")
        storage_path = job.get("storage_path", "")

        # Resolve the actual video file path
        video_path = local_storage.get_upload_path(video_id, filename)
        if not video_path:
            raise FileNotFoundError(
                f"Video file not found for job {video_id}. "
                f"Expected at uploads/{video_id}/{filename}"
            )

        # Setup temp directory for this job
        temp_dir = local_storage.get_temp_dir(video_id)
        output_dir = local_storage.get_processed_dir(video_id)

        # ──────────────────────────────────────────
        # Stage 1: Extract Frames
        # ──────────────────────────────────────────
        logger.info("[Stage 1/6] Extracting video frames...")
        await _update_progress(video_id, 0, "extracting_frames", 0)

        video_processor = VideoProcessor()
        frame_data = video_processor.extract_frames(
            str(video_path),
            output_dir=str(temp_dir / "frames"),
        )

        frames = frame_data["frames"]
        timestamps = frame_data["timestamps"]
        video_metadata = frame_data["metadata"]

        logger.info(
            f"[Stage 1/6] Extracted {len(frames)} frames from "
            f"{video_metadata.get('total_frames', '?')} total "
            f"({video_metadata.get('duration_seconds', 0):.1f}s video)"
        )
        await _update_progress(video_id, 0, "extracting_frames", 100)

        # ──────────────────────────────────────────
        # Stage 2: Optical Flow / Feature Encoding
        # ──────────────────────────────────────────
        logger.info("[Stage 2/6] Computing optical flow & encoding features...")
        await _update_progress(video_id, 1, "extracting_flow", 0)

        # Convert frames to tensor for model input
        frame_tensor = video_processor.frames_to_tensor(frames)
        logger.info(f"[Stage 2/6] Frame tensor prepared: shape={getattr(frame_tensor, 'shape', 'N/A')}")
        await _update_progress(video_id, 1, "extracting_flow", 100)

        # ──────────────────────────────────────────
        # Stage 3: 4RC Model Inference
        # ──────────────────────────────────────────
        logger.info("[Stage 3/6] Running 4RC model inference...")
        await _update_progress(video_id, 2, "reconstructing_4d", 0)

        inference_results = run_inference(
            frames=frame_tensor,
            timestamps=timestamps,
            metadata=video_metadata,
        )

        is_synthetic = inference_results.get("synthetic", False)
        inference_time = inference_results.get("inference_time_seconds", 0)
        logger.info(
            f"[Stage 3/6] Inference complete in {inference_time:.1f}s "
            f"({'synthetic' if is_synthetic else 'real 4RC model'})"
        )
        await _update_progress(video_id, 2, "reconstructing_4d", 100)

        # ──────────────────────────────────────────
        # Stage 4: Point Cloud Generation
        # ──────────────────────────────────────────
        logger.info("[Stage 4/6] Generating PLY point cloud...")
        await _update_progress(video_id, 3, "generating_point_cloud", 0)

        ply_path = str(output_dir / "point_cloud.ply")
        pcg = PointCloudGenerator()
        point_cloud_metadata = pcg.generate(
            inference_results=inference_results,
            timestamps=timestamps,
            output_path=ply_path,
        )

        logger.info(
            f"[Stage 4/6] Point cloud: {point_cloud_metadata['num_points']} points, "
            f"{point_cloud_metadata['file_size_bytes'] / 1024:.1f}KB"
        )
        await _update_progress(video_id, 3, "generating_point_cloud", 100)

        # ──────────────────────────────────────────
        # Stage 5: Trajectory Extraction
        # ──────────────────────────────────────────
        logger.info("[Stage 5/6] Extracting motion trajectories...")
        await _update_progress(video_id, 4, "extracting_trajectories", 0)

        trajectory_path = str(output_dir / "trajectories.json")
        te = TrajectoryExtractor()
        trajectory_data = te.extract(
            inference_results=inference_results,
            timestamps=timestamps,
            output_path=trajectory_path,
        )

        tracked_objects = trajectory_data.get("tracked_objects", [])
        logger.info(
            f"[Stage 5/6] Extracted {len(tracked_objects)} tracked objects"
        )
        await _update_progress(video_id, 4, "extracting_trajectories", 100)

        # ──────────────────────────────────────────
        # Stage 6: Compile & Store Assets
        # ──────────────────────────────────────────
        logger.info("[Stage 6/6] Compiling final assets...")
        await _update_progress(video_id, 5, "compiling_assets", 0)

        # Generate file URLs
        point_cloud_url = local_storage.get_processed_file_url(video_id, "point_cloud.ply")
        trajectory_url = local_storage.get_processed_file_url(video_id, "trajectories.json")

        # Upload to Firebase Storage if connected
        if firebase_client.is_firebase_connected():
            point_cloud_url = await firebase_client.upload_to_storage(
                ply_path, f"processed/{video_id}/point_cloud.ply"
            )
            trajectory_url = await firebase_client.upload_to_storage(
                trajectory_path, f"processed/{video_id}/trajectories.json"
            )

        # Build results summary
        pipeline_elapsed = time.perf_counter() - pipeline_start

        results = {
            "point_cloud_url": point_cloud_url,
            "trajectory_url": trajectory_url,
            "point_cloud_metadata": point_cloud_metadata,
            "tracked_objects": [
                {
                    "id": obj["id"],
                    "name": obj["name"],
                    "category": obj["category"],
                    "color": obj["color"],
                    "base_speed": obj["base_speed"],
                    "confidence": obj.get("confidence", 0.95),
                    "trajectory_points": len(obj.get("trajectory", [])),
                }
                for obj in tracked_objects
            ],
            "total_frames_processed": len(frames),
            "processing_time_seconds": round(pipeline_elapsed, 2),
            "model_version": inference_results.get("model_name", settings.MODEL_NAME),
            "is_synthetic": is_synthetic,
        }

        # Update job as completed
        await local_storage.update_job(video_id, {
            "status": "completed",
            "progress": 100.0,
            "current_step": "Pipeline completed",
            "steps_completed": 6,
            "results": results,
        })

        if firebase_client.is_firebase_connected():
            await firebase_client.update_job_status(
                video_id,
                status="completed",
                progress=100.0,
                current_step="Pipeline completed",
                steps_completed=6,
                metadata={"results": results},
            )

        # Cleanup temp files
        local_storage.cleanup_temp(video_id)

        logger.info(f"{'='*60}")
        logger.info(f"  4RC Pipeline Completed: {video_id}")
        logger.info(f"  Total time: {pipeline_elapsed:.1f}s")
        logger.info(f"  Frames processed: {len(frames)}")
        logger.info(f"  Objects tracked: {len(tracked_objects)}")
        logger.info(f"  Point cloud: {point_cloud_metadata['num_points']} points")
        logger.info(f"  Mode: {'Synthetic' if is_synthetic else 'Real 4RC'}")
        logger.info(f"{'='*60}")

    except Exception as e:
        pipeline_elapsed = time.perf_counter() - pipeline_start
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Pipeline failed for {video_id}: {error_msg}")
        logger.error(traceback.format_exc())

        await local_storage.update_job(video_id, {
            "status": "failed",
            "progress": 0.0,
            "error_message": error_msg,
            "current_step": "Pipeline failed",
        })

        if firebase_client.is_firebase_connected():
            await firebase_client.update_job_status(
                video_id,
                status="failed",
                metadata={"error_message": error_msg},
            )
