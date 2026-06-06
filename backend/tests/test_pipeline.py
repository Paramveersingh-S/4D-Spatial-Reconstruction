"""
Tests for the AI pipeline components: video processor, point cloud generator,
trajectory extractor, and inference engine.
"""
import os
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest


class TestVideoProcessor:
    """Test the video frame extraction module."""

    def test_synthetic_frames_generation(self):
        from app.ai_pipeline.video_processor import VideoProcessor

        vp = VideoProcessor(max_frames=10, target_resolution=64)
        result = vp._generate_synthetic_frames("fake_path.mp4")

        assert "frames" in result
        assert "timestamps" in result
        assert "metadata" in result
        assert len(result["frames"]) == 10
        assert len(result["timestamps"]) == 10
        assert result["metadata"]["synthetic"] is True

    def test_frame_shapes(self):
        from app.ai_pipeline.video_processor import VideoProcessor

        vp = VideoProcessor(max_frames=5, target_resolution=64)
        result = vp._generate_synthetic_frames("fake.mp4")

        for frame in result["frames"]:
            assert isinstance(frame, np.ndarray)
            assert frame.shape == (64, 64, 3)
            assert frame.dtype == np.uint8

    def test_frames_to_tensor(self):
        from app.ai_pipeline.video_processor import VideoProcessor

        vp = VideoProcessor(max_frames=3, target_resolution=32)
        result = vp._generate_synthetic_frames("fake.mp4")
        tensor = vp.frames_to_tensor(result["frames"])

        assert tensor is not None
        # Shape should be (N, 3, H, W) or (N, H, W, 3) depending on PyTorch availability
        if hasattr(tensor, 'shape'):
            assert len(tensor.shape) >= 3


class TestPointCloudGenerator:
    """Test PLY point cloud generation."""

    def test_generate_from_inference(self, sample_inference_results):
        from app.ai_pipeline.point_cloud_generator import PointCloudGenerator

        pcg = PointCloudGenerator(density_factor=1.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_cloud.ply")
            timestamps = [i * 0.5 for i in range(5)]

            metadata = pcg.generate(
                inference_results=sample_inference_results,
                timestamps=timestamps,
                output_path=output_path,
            )

            assert os.path.exists(output_path)
            assert metadata["num_points"] > 0
            assert metadata["format"] == "ply"
            assert metadata["file_size_bytes"] > 0
            assert "bounds_min" in metadata
            assert "bounds_max" in metadata

    def test_ply_file_valid_header(self, sample_inference_results):
        from app.ai_pipeline.point_cloud_generator import PointCloudGenerator

        pcg = PointCloudGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.ply")
            pcg.generate(
                inference_results=sample_inference_results,
                timestamps=[0.0, 0.5, 1.0, 1.5, 2.0],
                output_path=output_path,
            )

            with open(output_path, "rb") as f:
                header = b""
                while True:
                    line = f.readline()
                    header += line
                    if b"end_header" in line:
                        break

                header_str = header.decode("ascii")
                assert "ply" in header_str
                assert "element vertex" in header_str
                assert "property float x" in header_str

    def test_default_environment_fallback(self):
        from app.ai_pipeline.point_cloud_generator import PointCloudGenerator

        pcg = PointCloudGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "default.ply")
            # Empty inference results should trigger default environment
            metadata = pcg.generate(
                inference_results={},
                timestamps=[0.0],
                output_path=output_path,
            )

            assert metadata["num_points"] > 1000  # Default env has many points


class TestTrajectoryExtractor:
    """Test motion trajectory extraction."""

    def test_extract_from_correspondences(self, sample_inference_results):
        from app.ai_pipeline.trajectory_extractor import TrajectoryExtractor

        te = TrajectoryExtractor()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "trajectories.json")
            timestamps = [i * 0.5 for i in range(5)]

            result = te.extract(
                inference_results=sample_inference_results,
                timestamps=timestamps,
                output_path=output_path,
            )

            assert os.path.exists(output_path)
            assert "tracked_objects" in result
            assert len(result["tracked_objects"]) >= 1

            # Verify structure
            obj = result["tracked_objects"][0]
            assert "id" in obj
            assert "name" in obj
            assert "trajectory" in obj
            assert len(obj["trajectory"]) > 0

    def test_trajectory_json_valid(self, sample_inference_results):
        from app.ai_pipeline.trajectory_extractor import TrajectoryExtractor

        te = TrajectoryExtractor()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "traj.json")
            te.extract(
                inference_results=sample_inference_results,
                timestamps=[0.0, 0.5, 1.0],
                output_path=output_path,
            )

            with open(output_path) as f:
                data = json.load(f)

            assert "version" in data
            assert "tracked_objects" in data
            assert isinstance(data["tracked_objects"], list)

    def test_default_trajectories(self):
        from app.ai_pipeline.trajectory_extractor import TrajectoryExtractor

        te = TrajectoryExtractor()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "default_traj.json")
            result = te.extract(
                inference_results={},
                timestamps=[i * 0.2 for i in range(60)],
                output_path=output_path,
            )

            # Should generate 4 default objects matching frontend
            assert len(result["tracked_objects"]) == 4

            # Check known object IDs
            obj_ids = [o["id"] for o in result["tracked_objects"]]
            assert "obj-fpv-drone" in obj_ids
            assert "obj-sedan-x7" in obj_ids

    def test_speed_estimation(self):
        from app.ai_pipeline.trajectory_extractor import TrajectoryExtractor

        te = TrajectoryExtractor()

        # Moving object: 10 m/s = 36 km/h
        trajectory = [
            {"t": 0.0, "x": 0, "y": 0, "z": 0},
            {"t": 1.0, "x": 10, "y": 0, "z": 0},
            {"t": 2.0, "x": 20, "y": 0, "z": 0},
        ]

        speed = te._estimate_speed(trajectory)
        assert abs(speed - 36.0) < 0.1  # 10 m/s * 3.6 = 36 km/h


class TestInference:
    """Test the 4RC inference engine."""

    def test_synthetic_inference(self):
        from app.ai_pipeline.inference import _run_synthetic_inference

        timestamps = [i * 0.5 for i in range(10)]
        metadata = {"target_resolution": 64, "duration_seconds": 5.0}

        results = _run_synthetic_inference(None, timestamps, metadata)

        assert "depth_maps" in results
        assert "point_clouds" in results
        assert "camera_poses" in results
        assert "correspondences" in results
        assert results["synthetic"] is True
        assert results["num_frames"] == 10

    def test_synthetic_correspondences(self):
        from app.ai_pipeline.inference import _generate_synthetic_correspondences

        timestamps = [i * 0.4 for i in range(30)]
        correspondences = _generate_synthetic_correspondences(30, timestamps, 12.0)

        assert len(correspondences) == 4  # 4 tracked objects
        for corr in correspondences:
            assert "object_id" in corr
            assert "tracked_points" in corr
            assert len(corr["tracked_points"]) > 0

    def test_camera_pose_generation(self):
        from app.ai_pipeline.inference import _generate_camera_pose

        pose = _generate_camera_pose(3.0, 12.0)

        assert "position" in pose
        assert "forward" in pose
        assert "timestamp" in pose
        assert len(pose["position"]) == 3
        assert pose["timestamp"] == 3.0
