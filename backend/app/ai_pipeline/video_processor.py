"""
Video Processor — Frame extraction from drone footage using OpenCV.
Handles video loading, frame sampling, resizing, and preprocessing for 4RC inference.
"""
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("pipeline.video_processor")


class VideoProcessor:
    """Extracts and preprocesses frames from drone video footage."""

    def __init__(
        self,
        frame_sample_rate: int = None,
        max_frames: int = None,
        target_resolution: int = None,
    ):
        self.frame_sample_rate = frame_sample_rate or settings.FRAME_SAMPLE_RATE
        self.max_frames = max_frames or settings.MAX_FRAMES
        self.target_resolution = target_resolution or settings.TARGET_RESOLUTION

    def extract_frames(
        self, video_path: str, output_dir: str = None
    ) -> Dict[str, Any]:
        """
        Extract frames from a video file.
        
        Returns:
            Dictionary with:
                - frames: List[np.ndarray] — extracted frames as RGB arrays
                - timestamps: List[float] — timestamp of each frame in seconds
                - metadata: Dict — video metadata (fps, duration, resolution, etc.)
        """
        try:
            import cv2
        except ImportError:
            logger.warning("OpenCV not available — generating synthetic frames")
            return self._generate_synthetic_frames(video_path)

        video_path = str(video_path)
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        # Extract video metadata
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0

        logger.info(
            f"Video loaded: {width}x{height}, {fps:.1f}fps, "
            f"{total_frames} frames, {duration:.1f}s"
        )

        # Calculate which frames to extract
        frame_indices = list(range(0, total_frames, self.frame_sample_rate))
        if len(frame_indices) > self.max_frames:
            # Uniformly sample to stay within max_frames limit
            step = len(frame_indices) / self.max_frames
            frame_indices = [frame_indices[int(i * step)] for i in range(self.max_frames)]

        logger.info(
            f"Extracting {len(frame_indices)} frames "
            f"(sample rate: every {self.frame_sample_rate} frames)"
        )

        frames = []
        timestamps = []
        saved_paths = []

        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue

            # Convert BGR (OpenCV) to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Resize to target resolution while maintaining aspect ratio
            frame_resized = self._resize_frame(frame_rgb)
            frames.append(frame_resized)

            timestamp = idx / fps if fps > 0 else idx
            timestamps.append(timestamp)

            # Optionally save frame to disk
            if output_dir:
                frame_filename = f"frame_{idx:06d}.png"
                frame_path = os.path.join(output_dir, frame_filename)
                cv2.imwrite(frame_path, cv2.cvtColor(frame_resized, cv2.COLOR_RGB2BGR))
                saved_paths.append(frame_path)

        cap.release()

        logger.info(f"Extracted {len(frames)} frames successfully")

        return {
            "frames": frames,
            "timestamps": timestamps,
            "saved_paths": saved_paths,
            "metadata": {
                "original_width": width,
                "original_height": height,
                "fps": fps,
                "total_frames": total_frames,
                "duration_seconds": duration,
                "extracted_count": len(frames),
                "target_resolution": self.target_resolution,
            },
        }

    def _resize_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize a frame to target resolution maintaining aspect ratio."""
        try:
            import cv2
        except ImportError:
            return frame

        h, w = frame.shape[:2]
        target = self.target_resolution

        if max(h, w) <= target:
            return frame

        if w >= h:
            new_w = target
            new_h = int(h * target / w)
        else:
            new_h = target
            new_w = int(w * target / h)

        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def _generate_synthetic_frames(self, video_path: str) -> Dict[str, Any]:
        """
        Generate synthetic frames when OpenCV is not available.
        This allows the pipeline to function without real video processing
        for development and testing purposes.
        """
        logger.info("Generating synthetic frames for development mode")

        num_frames = min(30, self.max_frames)
        frames = []
        timestamps = []

        for i in range(num_frames):
            # Create a synthetic gradient frame
            frame = np.zeros((self.target_resolution, self.target_resolution, 3), dtype=np.uint8)
            
            # Create moving gradient pattern
            t = i / num_frames
            for y in range(self.target_resolution):
                for x in range(0, self.target_resolution, 4):
                    r = int(128 + 127 * np.sin(2 * np.pi * (x / self.target_resolution + t)))
                    g = int(128 + 127 * np.sin(2 * np.pi * (y / self.target_resolution + t * 0.5)))
                    b = int(128 + 127 * np.cos(2 * np.pi * (t)))
                    frame[y, x:x+4] = [r, g, b]

            frames.append(frame)
            timestamps.append(i * 0.4)  # 0.4s between frames = 2.5fps effective

        return {
            "frames": frames,
            "timestamps": timestamps,
            "saved_paths": [],
            "metadata": {
                "original_width": self.target_resolution,
                "original_height": self.target_resolution,
                "fps": 30.0,
                "total_frames": num_frames,
                "duration_seconds": num_frames * 0.4,
                "extracted_count": num_frames,
                "target_resolution": self.target_resolution,
                "synthetic": True,
            },
        }

    def frames_to_tensor(self, frames: List[np.ndarray]):
        """
        Convert extracted frames to a PyTorch tensor for model input.
        Shape: (N, 3, H, W) — batch of N frames, RGB channels, height, width.
        """
        try:
            import torch
        except ImportError:
            logger.warning("PyTorch not available — returning numpy arrays")
            return np.stack(frames)

        # Stack frames: (N, H, W, 3)
        stacked = np.stack(frames).astype(np.float32) / 255.0

        # Transpose to (N, 3, H, W) for PyTorch
        stacked = np.transpose(stacked, (0, 3, 1, 2))

        tensor = torch.from_numpy(stacked)
        logger.info(f"Frame tensor shape: {tensor.shape}, dtype: {tensor.dtype}")
        return tensor
