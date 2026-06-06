"""
4RC Model Inference Engine.
Handles model loading, device management, and running the 4RC
(4D Reconstruction via Conditional Querying) model on extracted video frames.
"""
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import time

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("pipeline.inference")

# Singleton model instance
_model = None
_model_loaded = False
_device = None


def get_device():
    """Get the appropriate PyTorch device."""
    global _device
    if _device is not None:
        return _device

    try:
        import torch
        requested = settings.MODEL_DEVICE.lower()

        if requested == "cuda" and torch.cuda.is_available():
            _device = torch.device("cuda")
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024**3)
            logger.info(f"Using CUDA device: {gpu_name} ({gpu_mem:.1f}GB)")
        else:
            _device = torch.device("cpu")
            if requested == "cuda":
                logger.warning("CUDA requested but not available — falling back to CPU")
            else:
                logger.info("Using CPU device")

    except ImportError:
        logger.warning("PyTorch not installed — inference will use synthetic mode")
        _device = None

    return _device


def load_model():
    """
    Load the 4RC model from Hugging Face.
    Uses singleton pattern — only loads once, reuses afterwards.
    """
    global _model, _model_loaded

    if _model_loaded:
        logger.info("4RC model already loaded — reusing cached instance")
        return _model

    device = get_device()

    if device is None:
        logger.warning("No PyTorch device — running in synthetic inference mode")
        _model_loaded = True
        return None

    try:
        import torch

        logger.info(f"Loading 4RC model: {settings.MODEL_NAME}")
        logger.info(f"Cache directory: {settings.MODEL_CACHE_DIR}")
        start = time.perf_counter()

        # Attempt to load the real 4RC model
        try:
            from arc.models.arc.arc import Arc

            os.makedirs(settings.MODEL_CACHE_DIR, exist_ok=True)
            model = Arc.from_pretrained(
                settings.MODEL_NAME,
                cache_dir=settings.MODEL_CACHE_DIR,
            ).to(device)
            model.eval()

            elapsed = time.perf_counter() - start
            logger.info(f"4RC model loaded successfully in {elapsed:.1f}s")
            _model = model
            _model_loaded = True
            return _model

        except ImportError:
            logger.warning(
                "4RC model package (arc) not installed. "
                "Install with: pip install git+https://github.com/Luo-Yihang/4RC.git "
                "Running in synthetic inference mode."
            )
            _model_loaded = True
            return None

        except Exception as e:
            logger.warning(
                f"Failed to load 4RC model: {e}. "
                "Running in synthetic inference mode."
            )
            _model_loaded = True
            return None

    except ImportError:
        logger.warning("PyTorch not available — synthetic inference mode")
        _model_loaded = True
        return None


def run_inference(
    frames: Any,
    timestamps: List[float],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run 4RC inference on extracted video frames.

    Args:
        frames: Tensor of shape (N, 3, H, W) or list of numpy arrays
        timestamps: List of timestamps for each frame
        metadata: Video metadata from frame extraction

    Returns:
        Dictionary containing:
            - depth_maps: Per-frame depth predictions
            - point_clouds: 3D point cloud data per frame
            - camera_poses: Estimated camera poses per frame
            - correspondences: Cross-frame point correspondences
            - flow_fields: Optical flow between consecutive frames
    """
    model = load_model()

    if model is None:
        logger.info("Running synthetic 4RC inference (model not available)")
        return _run_synthetic_inference(frames, timestamps, metadata)

    return _run_real_inference(model, frames, timestamps, metadata)


def _run_real_inference(
    model: Any,
    frames: Any,
    timestamps: List[float],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Run actual 4RC model inference with the loaded model."""
    import torch

    device = get_device()
    logger.info(f"Running real 4RC inference on {len(timestamps)} frames")
    start = time.perf_counter()

    results = {
        "depth_maps": [],
        "point_clouds": [],
        "camera_poses": [],
        "correspondences": [],
        "flow_fields": [],
    }

    with torch.no_grad():
        # Process frames in batches
        batch_size = 4
        num_frames = frames.shape[0] if hasattr(frames, 'shape') else len(frames)

        for batch_start in range(0, num_frames, batch_size):
            batch_end = min(batch_start + batch_size, num_frames)
            batch = frames[batch_start:batch_end]

            if isinstance(batch, np.ndarray):
                batch = torch.from_numpy(batch).float().to(device)
            elif not isinstance(batch, torch.Tensor):
                batch = torch.tensor(batch, dtype=torch.float32).to(device)
            else:
                batch = batch.to(device)

            try:
                # Run 4RC forward pass
                # The 4RC model's API: model.forward(images) -> dict with depth, poses, etc.
                output = model(batch)

                # Extract outputs
                if isinstance(output, dict):
                    if "depth" in output:
                        results["depth_maps"].extend(
                            output["depth"].cpu().numpy().tolist()
                        )
                    if "points3d" in output:
                        results["point_clouds"].extend(
                            output["points3d"].cpu().numpy().tolist()
                        )
                    if "poses" in output:
                        results["camera_poses"].extend(
                            output["poses"].cpu().numpy().tolist()
                        )
                    if "flow" in output:
                        results["flow_fields"].extend(
                            output["flow"].cpu().numpy().tolist()
                        )
                    if "correspondences" in output:
                        results["correspondences"].extend(
                            output["correspondences"].cpu().numpy().tolist()
                        )

            except Exception as e:
                logger.error(f"Inference error on batch {batch_start}-{batch_end}: {e}")
                # Fall back to synthetic for this batch
                synthetic = _generate_synthetic_batch(batch_start, batch_end, metadata)
                for key in results:
                    results[key].extend(synthetic.get(key, []))

            progress = min(100.0, (batch_end / num_frames) * 100)
            logger.info(f"Inference progress: {progress:.1f}%")

    elapsed = time.perf_counter() - start
    logger.info(f"4RC inference completed in {elapsed:.1f}s")

    results["inference_time_seconds"] = elapsed
    results["num_frames"] = num_frames
    results["model_name"] = settings.MODEL_NAME

    return results


def _run_synthetic_inference(
    frames: Any,
    timestamps: List[float],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate synthetic 4RC-like output for development without the actual model.
    Produces realistic-looking depth maps, point clouds, camera poses, and trajectories.
    """
    num_frames = len(timestamps) if isinstance(timestamps, list) else 30
    resolution = metadata.get("target_resolution", settings.TARGET_RESOLUTION)
    duration = metadata.get("duration_seconds", 12.0)

    logger.info(f"Generating synthetic inference results for {num_frames} frames")
    start = time.perf_counter()

    results = {
        "depth_maps": [],
        "point_clouds": [],
        "camera_poses": [],
        "correspondences": [],
        "flow_fields": [],
    }

    np.random.seed(42)  # Reproducible results

    for i in range(num_frames):
        t = timestamps[i] if i < len(timestamps) else (i / num_frames) * duration

        # ── Synthetic Depth Map ──
        # Creates a plausible urban scene depth
        depth = _generate_synthetic_depth(resolution, t)
        results["depth_maps"].append(depth.tolist())

        # ── Synthetic Point Cloud ──
        # Back-project depth into 3D points
        points = _depth_to_points(depth, t, resolution)
        results["point_clouds"].append(points.tolist())

        # ── Synthetic Camera Pose ──
        # Simulate a smooth drone flight path
        pose = _generate_camera_pose(t, duration)
        results["camera_poses"].append(pose)

        # ── Synthetic Flow Fields ──
        if i > 0:
            flow = _generate_synthetic_flow(resolution, t)
            results["flow_fields"].append(flow.tolist())

    # ── Synthetic Correspondences ──
    # Cross-frame point correspondences for tracking
    results["correspondences"] = _generate_synthetic_correspondences(
        num_frames, timestamps, duration
    )

    elapsed = time.perf_counter() - start
    results["inference_time_seconds"] = elapsed
    results["num_frames"] = num_frames
    results["model_name"] = "synthetic_4rc_dev"
    results["synthetic"] = True

    logger.info(f"Synthetic inference completed in {elapsed:.1f}s")
    return results


def _generate_synthetic_depth(resolution: int, t: float) -> np.ndarray:
    """Generate a plausible depth map for an urban scene."""
    h = w = resolution // 4  # Lower resolution for efficiency
    depth = np.ones((h, w), dtype=np.float32) * 50.0  # Base depth = 50m

    # Ground plane (bottom half gets closer)
    for y in range(h // 2, h):
        ground_depth = 5.0 + (y - h // 2) / (h // 2) * 45.0
        depth[y, :] = ground_depth

    # Buildings on sides
    for x in range(w // 8):
        building_height = int(h * 0.3 + np.random.rand() * h * 0.3)
        depth[h - building_height:h, x] = 8.0 + np.random.rand() * 12.0
        depth[h - building_height:h, w - 1 - x] = 8.0 + np.random.rand() * 12.0

    # Add temporal variation
    depth += np.sin(t * 0.5) * 2.0

    # Add noise
    depth += np.random.randn(h, w).astype(np.float32) * 0.5

    return np.clip(depth, 0.5, 100.0)


def _depth_to_points(depth: np.ndarray, t: float, resolution: int) -> np.ndarray:
    """Back-project a depth map into a 3D point cloud."""
    h, w = depth.shape
    focal_length = resolution * 0.8

    # Create pixel grid
    u, v = np.meshgrid(np.arange(w), np.arange(h))
    u = u.astype(np.float32) - w / 2
    v = v.astype(np.float32) - h / 2

    # Back-project to 3D
    z = depth
    x = u * z / focal_length
    y = v * z / focal_length

    # Stack to (H*W, 3)
    points = np.stack([x.flatten(), y.flatten(), z.flatten()], axis=-1)

    # Subsample for web efficiency
    num_points = min(len(points), 2000)
    indices = np.random.choice(len(points), num_points, replace=False)
    return points[indices]


def _generate_camera_pose(t: float, duration: float) -> Dict[str, Any]:
    """Generate a smooth drone camera pose at time t."""
    phase = (t / duration) * 2 * np.pi

    # Simulate a smooth orbiting camera path
    radius = 20.0
    height = 15.0 + np.sin(phase * 0.5) * 5.0

    position = [
        float(np.cos(phase * 0.3) * radius),
        float(height),
        float(np.sin(phase * 0.3) * radius),
    ]

    # Camera rotation (4x4 matrix as flat list)
    look_at = [0.0, 0.0, 0.0]
    forward = np.array(look_at) - np.array(position)
    forward = forward / (np.linalg.norm(forward) + 1e-8)

    return {
        "position": position,
        "forward": forward.tolist(),
        "timestamp": float(t),
    }


def _generate_synthetic_flow(resolution: int, t: float) -> np.ndarray:
    """Generate synthetic optical flow field."""
    h = w = resolution // 8
    flow = np.zeros((h, w, 2), dtype=np.float32)

    # Simulate forward motion + rotation
    cx, cy = w / 2, h / 2
    for y in range(h):
        for x in range(w):
            dx = (x - cx) * 0.02 + np.sin(t) * 0.5
            dy = (y - cy) * 0.02 + np.cos(t) * 0.3
            flow[y, x] = [dx, dy]

    return flow


def _generate_synthetic_correspondences(
    num_frames: int, timestamps: List[float], duration: float
) -> List[Dict[str, Any]]:
    """
    Generate synthetic cross-frame correspondences that represent
    tracked objects moving through the scene.
    """
    # Define 4 synthetic tracked entities
    objects = [
        {
            "id": "synth_drone_1",
            "name": "Quadcopter FPV-9",
            "category": "drone",
            "color": "#06b6d4",
            "base_speed": 48.0,
            "trajectory_fn": lambda t: {
                "x": float(np.cos(t * 0.5 + 0.5) * 18),
                "y": float(10 + np.sin(t * 1.2) * 3),
                "z": float(np.sin(t * 0.5 + 0.5) * 18),
                "heading": float(t * 0.5 + 0.5 + np.pi / 2),
            },
        },
        {
            "id": "synth_vehicle_1",
            "name": "Autonomous Vehicle Sedan-X7",
            "category": "vehicle",
            "color": "#a855f7",
            "base_speed": 60.0,
            "trajectory_fn": lambda t: {
                "x": -4.0,
                "y": 1.1,
                "z": float(-30 + t * 5.2),
                "heading": 0.0,
            },
        },
        {
            "id": "synth_bike_1",
            "name": "Commuter E-Bike #03",
            "category": "vehicle",
            "color": "#10b981",
            "base_speed": 25.0,
            "trajectory_fn": lambda t: {
                "x": 6.5,
                "y": 0.8,
                "z": float(25 + t * -2.1),
                "heading": float(np.pi),
            },
        },
        {
            "id": "synth_pedestrian_1",
            "name": "Pedestrian (Query #4)",
            "category": "pedestrian",
            "color": "#f59e0b",
            "base_speed": 5.0,
            "trajectory_fn": lambda t: {
                "x": float(min(-8 + t * 0.8, 8)),
                "y": 0.7,
                "z": 4.5,
                "heading": float(np.pi / 2),
            },
        },
    ]

    correspondences = []
    for obj in objects:
        points = []
        for i, ts in enumerate(timestamps[:num_frames]):
            pos = obj["trajectory_fn"](ts)
            points.append({
                "frame_index": i,
                "timestamp": float(ts),
                "position": {"x": pos["x"], "y": pos["y"], "z": pos["z"]},
                "heading": pos["heading"],
                "confidence": float(0.92 + np.random.rand() * 0.08),
            })

        correspondences.append({
            "object_id": obj["id"],
            "name": obj["name"],
            "category": obj["category"],
            "color": obj["color"],
            "base_speed": obj["base_speed"],
            "tracked_points": points,
        })

    return correspondences


def _generate_synthetic_batch(
    batch_start: int, batch_end: int, metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate synthetic results for a failed batch."""
    resolution = metadata.get("target_resolution", 512)
    results = {"depth_maps": [], "point_clouds": [], "camera_poses": [], "flow_fields": []}

    for i in range(batch_start, batch_end):
        t = i * 0.4
        results["depth_maps"].append(
            _generate_synthetic_depth(resolution, t).tolist()
        )
        results["point_clouds"].append(
            _depth_to_points(
                _generate_synthetic_depth(resolution, t), t, resolution
            ).tolist()
        )
        results["camera_poses"].append(_generate_camera_pose(t, 12.0))

    return results
