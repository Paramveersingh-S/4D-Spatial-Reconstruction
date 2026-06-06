"""
FastAPI REST API routes for The Impossible Drone Camera backend.
Handles video upload, processing triggers, status polling, and result retrieval.
"""
import uuid
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import asyncio
import json

from .schemas import (
    VideoUploadResponse,
    ProcessingTriggerResponse,
    JobStatusResponse,
    ProcessingResultResponse,
    JobListResponse,
    JobListItem,
    ErrorResponse,
    HealthResponse,
    JobStatus,
    ProcessingOptions,
)
from ..core.config import settings
from ..core.logging import get_logger
from ..services.storage import local_storage
from ..services import firebase_client
from ..ai_pipeline.pipeline import run_full_pipeline

logger = get_logger("api.routes")

router = APIRouter()


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Detailed system health check."""
    try:
        import torch
        gpu_available = torch.cuda.is_available()
    except ImportError:
        gpu_available = False

    device = settings.MODEL_DEVICE
    if device == "cuda" and not gpu_available:
        device = "cpu (cuda requested but unavailable)"

    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        model_loaded=False,  # Updated when model is actually loaded
        firebase_connected=firebase_client.is_firebase_connected(),
        gpu_available=gpu_available,
        device=device,
    )


# ──────────────────────────────────────────────
# Video Upload
# ──────────────────────────────────────────────

@router.post("/upload", response_model=VideoUploadResponse, tags=["Ingestion"])
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a raw drone video (MP4/MOV) for 4RC processing.
    Returns a unique video_id for tracking the reconstruction job.
    """
    # Validate file type
    allowed_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska"]
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: {', '.join(allowed_types)}",
        )

    # Validate file extension
    filename = file.filename or "unknown.mp4"
    ext = Path(filename).suffix.lower()
    if ext not in [".mp4", ".mov", ".avi", ".mkv"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension: {ext}. Allowed: .mp4, .mov, .avi, .mkv",
        )

    # Read content
    content = await file.read()
    size_bytes = len(content)

    # Validate file size
    if size_bytes > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_bytes / 1024 / 1024:.1f}MB. Maximum: {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Generate unique video ID
    video_id = f"vid_{uuid.uuid4().hex[:12]}"

    # Save to storage
    storage_path = await local_storage.save_upload(video_id, content, filename)

    # Create job metadata
    job_metadata = {
        "filename": filename,
        "size_bytes": size_bytes,
        "storage_path": storage_path,
        "content_type": file.content_type,
    }
    await local_storage.create_job(video_id, job_metadata)

    # Also create in Firebase if connected
    if firebase_client.is_firebase_connected():
        await firebase_client.create_job(video_id, job_metadata)

    logger.info(f"Video uploaded: {video_id} ({filename}, {size_bytes / 1024:.1f}KB)")

    return VideoUploadResponse(
        video_id=video_id,
        filename=filename,
        size_bytes=size_bytes,
        storage_path=storage_path,
        status=JobStatus.UPLOADED,
    )


# ──────────────────────────────────────────────
# Process Video (Trigger 4RC Pipeline)
# ──────────────────────────────────────────────

@router.post("/process/{video_id}", response_model=ProcessingTriggerResponse, tags=["Processing"])
async def trigger_processing(video_id: str, background_tasks: BackgroundTasks):
    """
    Trigger the 4RC reconstruction pipeline for an uploaded video.
    Processing runs asynchronously in the background.
    """
    # Check job exists
    job = await local_storage.get_job(video_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    # Check not already processing
    current_status = job.get("status", "unknown")
    if current_status in ["processing", "extracting_frames", "extracting_flow",
                           "reconstructing_4d", "generating_point_cloud",
                           "extracting_trajectories", "compiling_assets"]:
        raise HTTPException(
            status_code=409,
            detail=f"Video {video_id} is already being processed (status: {current_status})",
        )

    # Update status to processing
    await local_storage.update_job(video_id, {"status": "processing", "progress": 0.0})
    if firebase_client.is_firebase_connected():
        await firebase_client.update_job_status(video_id, "processing")

    # Launch pipeline as background task
    background_tasks.add_task(run_full_pipeline, video_id)

    logger.info(f"Processing triggered for: {video_id}")

    return ProcessingTriggerResponse(
        video_id=video_id,
        status=JobStatus.PROCESSING,
        message=f"4RC reconstruction pipeline started for {video_id}",
        estimated_time_seconds=60,
    )


# ──────────────────────────────────────────────
# Job Status
# ──────────────────────────────────────────────

@router.get("/status/{video_id}", response_model=JobStatusResponse, tags=["Processing"])
async def get_job_status(video_id: str):
    """Get the current processing status of a reconstruction job."""
    job = await local_storage.get_job(video_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {video_id} not found")

    return JobStatusResponse(
        video_id=video_id,
        status=JobStatus(job.get("status", "pending")),
        progress=job.get("progress", 0.0),
        current_step=job.get("current_step"),
        steps_completed=job.get("steps_completed", 0),
        total_steps=job.get("total_steps", 6),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
        error_message=job.get("error_message"),
        metadata={k: v for k, v in job.items() if k not in [
            "video_id", "status", "progress", "current_step",
            "steps_completed", "total_steps", "created_at",
            "updated_at", "error_message",
        ]},
    )


# ──────────────────────────────────────────────
# Processing Results
# ──────────────────────────────────────────────

@router.get("/results/{video_id}", tags=["Results"])
async def get_results(video_id: str):
    """
    Fetch the processed reconstruction results (point cloud + trajectories).
    Only available after job status is COMPLETED.
    """
    job = await local_storage.get_job(video_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {video_id} not found")

    if job.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job {video_id} is not completed (status: {job.get('status')}). Wait for completion.",
        )

    # Load results from stored metadata
    results = job.get("results", {})
    return {
        "video_id": video_id,
        "status": "completed",
        "point_cloud_url": results.get("point_cloud_url", ""),
        "trajectory_url": results.get("trajectory_url", ""),
        "tracked_objects": results.get("tracked_objects", []),
        "point_cloud_metadata": results.get("point_cloud_metadata", {}),
        "total_frames_processed": results.get("total_frames_processed", 0),
        "processing_time_seconds": results.get("processing_time_seconds", 0),
        "model_version": settings.MODEL_NAME,
    }


# ──────────────────────────────────────────────
# Job Management
# ──────────────────────────────────────────────

@router.get("/jobs", response_model=JobListResponse, tags=["Jobs"])
async def list_jobs():
    """List all reconstruction jobs."""
    jobs = await local_storage.list_jobs()

    items = [
        JobListItem(
            video_id=j.get("video_id", "unknown"),
            filename=j.get("filename", "unknown"),
            status=JobStatus(j.get("status", "pending")),
            progress=j.get("progress", 0.0),
            created_at=j.get("created_at"),
            tracked_objects_count=len(j.get("results", {}).get("tracked_objects", [])),
        )
        for j in jobs
    ]

    return JobListResponse(jobs=items, total_count=len(items))


@router.delete("/jobs/{video_id}", tags=["Jobs"])
async def delete_job(video_id: str):
    """Delete a reconstruction job and all associated files."""
    job = await local_storage.get_job(video_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {video_id} not found")

    # Check not currently processing
    if job.get("status") in ["processing", "extracting_frames", "extracting_flow",
                              "reconstructing_4d"]:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a job that is currently processing. Wait for completion or failure.",
        )

    deleted = await local_storage.delete_job(video_id)
    if firebase_client.is_firebase_connected():
        await firebase_client.delete_job(video_id)

    return {"message": f"Job {video_id} deleted", "deleted": deleted}


# ──────────────────────────────────────────────
# File Serving (for local storage mode)
# ──────────────────────────────────────────────

@router.get("/files/{video_id}/{filename}", tags=["Files"])
async def serve_file(video_id: str, filename: str):
    """Serve a processed file (PLY, JSON) for download."""
    file_path = local_storage.get_processed_file_path(video_id, filename)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"File not found: {video_id}/{filename}")

    # Determine media type
    ext = file_path.suffix.lower()
    media_types = {
        ".ply": "application/octet-stream",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )


# ──────────────────────────────────────────────
# WebSocket Real-time Status
# ──────────────────────────────────────────────

@router.websocket("/ws/status/{video_id}")
async def websocket_status(websocket: WebSocket, video_id: str):
    """
    WebSocket endpoint for real-time job status streaming.
    Pushes status updates every second while the job is processing.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for job: {video_id}")

    try:
        last_status = None
        while True:
            job = await local_storage.get_job(video_id)
            if not job:
                await websocket.send_json({"error": f"Job {video_id} not found"})
                break

            current_status = job.get("status")

            # Send update if status changed or first message
            if current_status != last_status or last_status is None:
                await websocket.send_json({
                    "video_id": video_id,
                    "status": current_status,
                    "progress": job.get("progress", 0.0),
                    "current_step": job.get("current_step"),
                    "steps_completed": job.get("steps_completed", 0),
                    "total_steps": job.get("total_steps", 6),
                })
                last_status = current_status

            # Stop if terminal state
            if current_status in ["completed", "failed", "cancelled"]:
                break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job: {video_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {video_id}: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
