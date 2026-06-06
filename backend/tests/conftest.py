"""
Shared test fixtures for the 4RC backend test suite.
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment variables BEFORE importing app modules
os.environ["USE_LOCAL_STORAGE"] = "true"
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["MODEL_DEVICE"] = "cpu"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"


@pytest.fixture(scope="session")
def test_storage_dir():
    """Create a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory(prefix="4rc_test_") as tmpdir:
        os.environ["LOCAL_STORAGE_PATH"] = tmpdir
        os.environ["TEMP_DIR"] = os.path.join(tmpdir, "temp")
        yield tmpdir


@pytest.fixture
def app(test_storage_dir):
    """Create a FastAPI test application."""
    # Force reimport to pick up test env vars
    from app.main import app
    return app


@pytest.fixture
def client(app):
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def sample_video_bytes():
    """Generate minimal valid-looking video bytes for upload testing."""
    # This is a minimal MP4 header (ftyp + moov atoms)
    # Not a real playable video, but enough for upload validation
    ftyp = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom'
    moov = b'\x00\x00\x00\x08moov'
    mdat = b'\x00\x00\x00\x10mdat' + b'\x00' * 8
    return ftyp + moov + mdat


@pytest.fixture
def sample_video_file(tmp_path, sample_video_bytes):
    """Create a temporary sample video file."""
    video_path = tmp_path / "test_drone_clip.mp4"
    video_path.write_bytes(sample_video_bytes)
    return str(video_path)


@pytest.fixture
def sample_job_metadata():
    """Sample job metadata for testing."""
    return {
        "filename": "test_drone_clip.mp4",
        "size_bytes": 1024,
        "storage_path": "uploads/test_123/test_drone_clip.mp4",
        "content_type": "video/mp4",
    }


@pytest.fixture
def sample_inference_results():
    """Sample 4RC inference results for testing."""
    import numpy as np

    return {
        "depth_maps": [np.random.rand(32, 32).tolist() for _ in range(5)],
        "point_clouds": [np.random.rand(100, 3).tolist() for _ in range(5)],
        "camera_poses": [
            {"position": [0, 10, 0], "forward": [0, 0, 1], "timestamp": i * 0.5}
            for i in range(5)
        ],
        "correspondences": [
            {
                "object_id": "test_obj_1",
                "name": "Test Drone",
                "category": "drone",
                "color": "#06b6d4",
                "base_speed": 48.0,
                "tracked_points": [
                    {
                        "frame_index": i,
                        "timestamp": i * 0.5,
                        "position": {"x": float(i), "y": 10.0, "z": float(i * 2)},
                        "heading": 0.0,
                        "confidence": 0.95,
                    }
                    for i in range(5)
                ],
            }
        ],
        "flow_fields": [],
        "inference_time_seconds": 1.5,
        "num_frames": 5,
        "model_name": "synthetic_4rc_test",
        "synthetic": True,
    }
