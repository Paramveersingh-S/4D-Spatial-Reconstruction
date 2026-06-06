"""
Point Cloud Generator — Converts 4RC inference output (depth maps, camera poses)
into dense 3D point clouds in PLY format for Three.js rendering.
"""
import struct
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("pipeline.point_cloud")


class PointCloudGenerator:
    """Generates PLY point cloud files from 4RC inference results."""

    def __init__(self, density_factor: float = None):
        self.density_factor = density_factor or settings.POINT_CLOUD_DENSITY

    def generate(
        self,
        inference_results: Dict[str, Any],
        timestamps: List[float],
        output_path: str,
    ) -> Dict[str, Any]:
        """
        Generate a PLY point cloud from 4RC inference results.

        Args:
            inference_results: Output from the 4RC inference engine
            timestamps: Frame timestamps
            output_path: Path to save the PLY file

        Returns:
            Metadata about the generated point cloud
        """
        logger.info("Generating point cloud from inference results...")

        # Collect all 3D points from inference
        all_points = []
        all_colors = []

        point_clouds = inference_results.get("point_clouds", [])
        depth_maps = inference_results.get("depth_maps", [])
        camera_poses = inference_results.get("camera_poses", [])

        if point_clouds:
            # Use direct point cloud output
            for i, pc in enumerate(point_clouds):
                points = np.array(pc, dtype=np.float32)
                if points.ndim == 1:
                    continue
                if points.ndim == 2 and points.shape[1] >= 3:
                    # Transform points by camera pose if available
                    if i < len(camera_poses):
                        pose = camera_poses[i]
                        pos = np.array(pose.get("position", [0, 0, 0]))
                        points[:, :3] += pos  # Shift by camera position

                    all_points.append(points[:, :3])

                    # Generate colors based on depth (height-based coloring)
                    colors = self._generate_colors(points[:, :3], i / max(len(point_clouds), 1))
                    all_colors.append(colors)

        elif depth_maps:
            # Fall back to generating points from depth maps
            for i, depth in enumerate(depth_maps):
                depth_arr = np.array(depth, dtype=np.float32)
                if depth_arr.ndim < 2:
                    continue

                points, colors = self._depth_map_to_colored_points(
                    depth_arr,
                    camera_poses[i] if i < len(camera_poses) else None,
                    i / max(len(depth_maps), 1),
                )
                all_points.append(points)
                all_colors.append(colors)

        if not all_points:
            # Generate a default environment point cloud
            logger.warning("No valid point data — generating default environment")
            points, colors = self._generate_default_environment()
            all_points.append(points)
            all_colors.append(colors)

        # Concatenate all points
        combined_points = np.concatenate(all_points, axis=0)
        combined_colors = np.concatenate(all_colors, axis=0)

        # Apply density subsampling
        num_target = int(len(combined_points) * self.density_factor)
        num_target = max(num_target, 1000)  # Minimum 1000 points
        num_target = min(num_target, 500000)  # Maximum 500K points

        if len(combined_points) > num_target:
            indices = np.random.choice(len(combined_points), num_target, replace=False)
            combined_points = combined_points[indices]
            combined_colors = combined_colors[indices]

        logger.info(f"Point cloud: {len(combined_points)} points after density filtering")

        # Compute bounds
        bounds_min = combined_points.min(axis=0)
        bounds_max = combined_points.max(axis=0)

        # Write PLY file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_ply(str(output_path), combined_points, combined_colors)

        file_size = output_path.stat().st_size

        metadata = {
            "num_points": len(combined_points),
            "format": "ply",
            "file_size_bytes": file_size,
            "bounds_min": {
                "x": float(bounds_min[0]),
                "y": float(bounds_min[1]),
                "z": float(bounds_min[2]),
            },
            "bounds_max": {
                "x": float(bounds_max[0]),
                "y": float(bounds_max[1]),
                "z": float(bounds_max[2]),
            },
            "has_colors": True,
            "has_normals": False,
            "density_factor": self.density_factor,
        }

        logger.info(
            f"PLY written: {output_path} ({file_size / 1024:.1f}KB, "
            f"{len(combined_points)} points)"
        )
        return metadata

    def _generate_colors(self, points: np.ndarray, time_factor: float) -> np.ndarray:
        """Generate colors for points based on position and temporal factor."""
        num_points = len(points)
        colors = np.zeros((num_points, 3), dtype=np.uint8)

        # Height-based coloring with cyberpunk palette
        heights = points[:, 1]
        h_min, h_max = heights.min(), heights.max()
        h_range = max(h_max - h_min, 1.0)
        h_norm = (heights - h_min) / h_range

        for i in range(num_points):
            h = h_norm[i]
            # Gradient: dark blue → cyan → purple at top
            if h < 0.3:
                # Ground: dark gray/blue
                colors[i] = [30 + int(h * 100), 30 + int(h * 60), 50 + int(h * 80)]
            elif h < 0.6:
                # Mid-level: cyan tint
                t = (h - 0.3) / 0.3
                colors[i] = [20 + int(t * 30), 80 + int(t * 100), 120 + int(t * 80)]
            else:
                # Upper: purple/magenta
                t = (h - 0.6) / 0.4
                colors[i] = [100 + int(t * 68), 50 + int(t * 35), 150 + int(t * 97)]

        return colors

    def _depth_map_to_colored_points(
        self,
        depth: np.ndarray,
        camera_pose: Optional[Dict],
        time_factor: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Convert a depth map to 3D points with colors."""
        h, w = depth.shape
        focal = max(h, w) * 0.8

        u, v = np.meshgrid(np.arange(w), np.arange(h))
        u = (u.astype(np.float32) - w / 2)
        v = (v.astype(np.float32) - h / 2)

        z = depth
        x = u * z / focal
        y = v * z / focal

        points = np.stack([x.flatten(), y.flatten(), z.flatten()], axis=-1)

        # Apply camera pose transform
        if camera_pose and "position" in camera_pose:
            pos = np.array(camera_pose["position"], dtype=np.float32)
            points += pos

        colors = self._generate_colors(points, time_factor)
        return points, colors

    def _generate_default_environment(self) -> Tuple[np.ndarray, np.ndarray]:
        """Generate a default urban environment point cloud."""
        points_list = []
        colors_list = []

        # Ground plane
        for x in np.arange(-20, 20, 0.8):
            for z in np.arange(-40, 40, 0.8):
                y = 0.0 + np.random.randn() * 0.05
                is_road = abs(x) < 5
                points_list.append([x, y, z])

                if is_road:
                    if abs(x) < 0.2 and int(z) % 6 == 0:
                        colors_list.append([200, 200, 200])  # Road stripe
                    else:
                        colors_list.append([55, 65, 81])  # Road
                elif abs(x) < 9:
                    colors_list.append([75, 85, 99])  # Sidewalk
                else:
                    colors_list.append([31, 41, 55])  # Landscape

        # Buildings
        for side_x in [-12, 12]:
            for z in np.arange(-30, 30, 3):
                height = 12 + np.sin(z * 0.3) * 4
                for y in np.arange(0.5, height, 1.2):
                    for offset in np.arange(-2, 2.5, 1.0):
                        pt = [
                            side_x + offset + np.random.randn() * 0.15,
                            y + np.random.randn() * 0.1,
                            z + np.random.randn() * 0.15,
                        ]
                        points_list.append(pt)
                        if side_x < 0:
                            colors_list.append([30, 41, 59])
                        else:
                            colors_list.append([17, 24, 39])

        # Atmospheric particles
        for _ in range(500):
            pt = [
                np.random.randn() * 20,
                8 + np.random.rand() * 12,
                np.random.randn() * 30,
            ]
            points_list.append(pt)
            colors_list.append([6, 130, 160])  # Cyan atmospheric

        return np.array(points_list, dtype=np.float32), np.array(colors_list, dtype=np.uint8)

    def _write_ply(
        self, filepath: str, points: np.ndarray, colors: np.ndarray
    ) -> None:
        """Write a PLY file with vertices and colors (binary little-endian)."""
        num_points = len(points)

        header = (
            "ply\n"
            "format binary_little_endian 1.0\n"
            f"element vertex {num_points}\n"
            "property float x\n"
            "property float y\n"
            "property float z\n"
            "property uchar red\n"
            "property uchar green\n"
            "property uchar blue\n"
            "end_header\n"
        )

        with open(filepath, "wb") as f:
            f.write(header.encode("ascii"))
            for i in range(num_points):
                f.write(struct.pack(
                    "<fffBBB",
                    points[i, 0], points[i, 1], points[i, 2],
                    colors[i, 0], colors[i, 1], colors[i, 2],
                ))
