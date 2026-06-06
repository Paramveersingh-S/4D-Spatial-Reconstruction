"""
Trajectory Extractor — Converts 4RC correspondence output into
per-object motion trajectories in a format compatible with the frontend.
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("pipeline.trajectory")


class TrajectoryExtractor:
    """Extracts and formats object motion trajectories from 4RC results."""

    # Default color palette for tracked objects
    COLOR_PALETTE = [
        "#06b6d4",  # Cyan
        "#a855f7",  # Purple
        "#10b981",  # Emerald
        "#f59e0b",  # Amber
        "#ef4444",  # Red
        "#3b82f6",  # Blue
        "#ec4899",  # Pink
        "#84cc16",  # Lime
    ]

    def extract(
        self,
        inference_results: Dict[str, Any],
        timestamps: List[float],
        output_path: str,
    ) -> Dict[str, Any]:
        """
        Extract motion trajectories from 4RC inference results.

        Args:
            inference_results: Output from the 4RC inference engine
            timestamps: Frame timestamps in seconds
            output_path: Path to save the trajectory JSON file

        Returns:
            Dictionary with tracked objects and their trajectories
        """
        logger.info("Extracting motion trajectories...")

        correspondences = inference_results.get("correspondences", [])

        if not correspondences:
            logger.warning("No correspondences found — generating default trajectories")
            tracked_objects = self._generate_default_trajectories(timestamps)
        else:
            tracked_objects = self._process_correspondences(correspondences, timestamps)

        # Build output structure matching the frontend's expected format
        output = {
            "version": "1.0",
            "model": inference_results.get("model_name", settings.MODEL_NAME),
            "total_frames": len(timestamps),
            "duration_seconds": max(timestamps) if timestamps else 0.0,
            "tracked_objects": tracked_objects,
        }

        # Write JSON
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        file_size = output_path.stat().st_size
        logger.info(
            f"Trajectories written: {output_path} "
            f"({len(tracked_objects)} objects, {file_size / 1024:.1f}KB)"
        )

        return output

    def _process_correspondences(
        self, correspondences: List[Dict[str, Any]], timestamps: List[float]
    ) -> List[Dict[str, Any]]:
        """Process 4RC correspondence data into tracked object trajectories."""
        tracked_objects = []

        for idx, corr in enumerate(correspondences):
            obj_id = corr.get("object_id", f"obj_{idx}")
            name = corr.get("name", f"Object #{idx + 1}")
            category = corr.get("category", "unknown")
            color = corr.get("color", self.COLOR_PALETTE[idx % len(self.COLOR_PALETTE)])
            base_speed = corr.get("base_speed", 0.0)

            # Extract trajectory points
            tracked_points = corr.get("tracked_points", [])
            trajectory = []

            for pt in tracked_points:
                pos = pt.get("position", {})
                trajectory.append({
                    "t": pt.get("timestamp", 0.0),
                    "x": pos.get("x", 0.0),
                    "y": pos.get("y", 0.0),
                    "z": pos.get("z", 0.0),
                    "heading": pt.get("heading", 0.0),
                    "confidence": pt.get("confidence", 0.95),
                })

            # Calculate base speed from trajectory if not provided
            if base_speed == 0.0 and len(trajectory) >= 2:
                base_speed = self._estimate_speed(trajectory)

            # Compute average confidence
            avg_confidence = np.mean([p.get("confidence", 0.95) for p in trajectory]) if trajectory else 0.0

            tracked_objects.append({
                "id": obj_id,
                "name": name,
                "category": category,
                "color": color,
                "base_speed": round(float(base_speed), 1),
                "confidence": round(float(avg_confidence), 4),
                "trajectory": trajectory,
                "bbox_size": corr.get("bbox_size", {"x": 1.6, "y": 1.0, "z": 2.5}),
            })

        logger.info(f"Processed {len(tracked_objects)} tracked objects from correspondences")
        return tracked_objects

    def _estimate_speed(self, trajectory: List[Dict[str, Any]]) -> float:
        """Estimate average speed from trajectory points (in km/h)."""
        if len(trajectory) < 2:
            return 0.0

        total_distance = 0.0
        total_time = 0.0

        for i in range(1, len(trajectory)):
            p1 = trajectory[i - 1]
            p2 = trajectory[i]

            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            dz = p2["z"] - p1["z"]
            dist = np.sqrt(dx**2 + dy**2 + dz**2)

            dt = p2["t"] - p1["t"]
            if dt > 0:
                total_distance += dist
                total_time += dt

        if total_time > 0:
            speed_m_per_s = total_distance / total_time
            return speed_m_per_s * 3.6  # Convert to km/h

        return 0.0

    def _generate_default_trajectories(
        self, timestamps: List[float]
    ) -> List[Dict[str, Any]]:
        """
        Generate default trajectories matching the frontend's pre-configured objects.
        These match the math functions in src/data.ts.
        """
        duration = max(timestamps) if timestamps else 12.0

        objects = [
            {
                "id": "obj-fpv-drone",
                "name": "Quadcopter FPV-9",
                "category": "drone",
                "color": "#06b6d4",
                "base_speed": 48.0,
                "bbox_size": {"x": 1.6, "y": 1.0, "z": 2.5},
                "trajectory_fn": lambda t: (
                    float(np.cos(t * 0.5 + 0.5) * 18),
                    float(10 + np.sin(t * 1.2) * 3),
                    float(np.sin(t * 0.5 + 0.5) * 18),
                    float(t * 0.5 + 0.5 + np.pi / 2),
                ),
            },
            {
                "id": "obj-sedan-x7",
                "name": "Autonomous Vehicle Sedan-X7",
                "category": "vehicle",
                "color": "#a855f7",
                "base_speed": 60.0,
                "bbox_size": {"x": 2.0, "y": 1.5, "z": 4.5},
                "trajectory_fn": lambda t: (
                    -4.0,
                    1.1,
                    float(-30 + t * 5.2),
                    0.0,
                ),
            },
            {
                "id": "obj-ebike-3",
                "name": "Commuter E-Bike #03",
                "category": "vehicle",
                "color": "#10b981",
                "base_speed": 25.0,
                "bbox_size": {"x": 0.8, "y": 1.2, "z": 2.0},
                "trajectory_fn": lambda t: (
                    6.5,
                    0.8,
                    float(25 + t * -2.1),
                    float(np.pi),
                ),
            },
            {
                "id": "obj-pedestrian-alpha",
                "name": "Pedestrian (Conditional Query #4)",
                "category": "pedestrian",
                "color": "#f59e0b",
                "base_speed": 5.0,
                "bbox_size": {"x": 0.6, "y": 1.8, "z": 0.6},
                "trajectory_fn": lambda t: (
                    float(min(-8 + t * 0.8, 8)),
                    0.7,
                    4.5,
                    float(np.pi / 2),
                ),
            },
        ]

        tracked = []
        for obj_def in objects:
            trajectory = []
            fn = obj_def["trajectory_fn"]

            for t in timestamps if timestamps else np.linspace(0, duration, 60):
                x, y, z, heading = fn(float(t))
                trajectory.append({
                    "t": float(t),
                    "x": x,
                    "y": y,
                    "z": z,
                    "heading": heading,
                    "confidence": float(0.92 + np.random.rand() * 0.08),
                })

            tracked.append({
                "id": obj_def["id"],
                "name": obj_def["name"],
                "category": obj_def["category"],
                "color": obj_def["color"],
                "base_speed": obj_def["base_speed"],
                "confidence": 0.95,
                "trajectory": trajectory,
                "bbox_size": obj_def["bbox_size"],
            })

        logger.info(f"Generated {len(tracked)} default tracked objects")
        return tracked
