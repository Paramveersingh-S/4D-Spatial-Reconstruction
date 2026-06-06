"""
Local filesystem storage service.
Fallback when Firebase Storage is not configured (for local development).
Manages raw uploads, processed outputs, and temporary files.
"""
import os
import shutil
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("storage")


class LocalStorageService:
    """Manages file operations on the local filesystem."""

    def __init__(self):
        self.base_path = Path(settings.LOCAL_STORAGE_PATH).resolve()
        self.temp_path = Path(settings.TEMP_DIR).resolve()
        self.uploads_dir = self.base_path / "uploads"
        self.processed_dir = self.base_path / "processed"
        self.metadata_dir = self.base_path / "metadata"

        # Ensure directories exist
        for d in [self.uploads_dir, self.processed_dir, self.metadata_dir, self.temp_path]:
            d.mkdir(parents=True, exist_ok=True)

        logger.info(f"Local storage initialized at: {self.base_path}")

    # ── Video Upload ──────────────────────────────────────────

    async def save_upload(self, video_id: str, file_content: bytes, filename: str) -> str:
        """Save an uploaded video file and return the storage path."""
        video_dir = self.uploads_dir / video_id
        video_dir.mkdir(parents=True, exist_ok=True)

        file_path = video_dir / filename
        file_path.write_bytes(file_content)

        storage_path = str(file_path.relative_to(self.base_path))
        logger.info(f"Saved upload: {video_id}/{filename} ({len(file_content)} bytes)")
        return storage_path

    def get_upload_path(self, video_id: str, filename: str) -> Optional[Path]:
        """Get the absolute path to an uploaded video file."""
        file_path = self.uploads_dir / video_id / filename
        if file_path.exists():
            return file_path
        # Try to find any video file in the upload dir
        video_dir = self.uploads_dir / video_id
        if video_dir.exists():
            for f in video_dir.iterdir():
                if f.suffix.lower() in [".mp4", ".mov", ".avi", ".mkv"]:
                    return f
        return None

    # ── Processed Assets ──────────────────────────────────────

    def get_processed_dir(self, video_id: str) -> Path:
        """Get the directory for processed outputs."""
        d = self.processed_dir / video_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def save_processed_file(self, video_id: str, filename: str, content: bytes) -> str:
        """Save a processed output file (PLY, JSON, etc.)."""
        output_dir = self.get_processed_dir(video_id)
        file_path = output_dir / filename
        file_path.write_bytes(content)

        storage_path = str(file_path.relative_to(self.base_path))
        logger.info(f"Saved processed file: {storage_path} ({len(content)} bytes)")
        return storage_path

    def get_processed_file_path(self, video_id: str, filename: str) -> Optional[Path]:
        """Get absolute path to a processed file."""
        file_path = self.processed_dir / video_id / filename
        return file_path if file_path.exists() else None

    def get_processed_file_url(self, video_id: str, filename: str) -> str:
        """Get a URL-like path for accessing the processed file via API."""
        return f"/api/v1/files/{video_id}/{filename}"

    # ── Temp Files ────────────────────────────────────────────

    def get_temp_dir(self, video_id: str) -> Path:
        """Get a temporary directory for processing a specific video."""
        d = self.temp_path / video_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cleanup_temp(self, video_id: str) -> None:
        """Remove temporary files for a specific video."""
        temp_dir = self.temp_path / video_id
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp files for: {video_id}")

    # ── Job Metadata (Firestore replacement for local dev) ────

    def _get_job_file(self, video_id: str) -> Path:
        return self.metadata_dir / f"{video_id}.json"

    async def create_job(self, video_id: str, metadata: Dict[str, Any]) -> None:
        """Create a new job metadata document."""
        job_data = {
            "video_id": video_id,
            "status": "pending",
            "progress": 0.0,
            "current_step": None,
            "steps_completed": 0,
            "total_steps": 6,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error_message": None,
            **metadata,
        }
        self._get_job_file(video_id).write_text(json.dumps(job_data, indent=2))
        logger.info(f"Created job: {video_id}")

    async def update_job(self, video_id: str, updates: Dict[str, Any]) -> None:
        """Update a job metadata document."""
        job_file = self._get_job_file(video_id)
        if job_file.exists():
            job_data = json.loads(job_file.read_text())
        else:
            job_data = {"video_id": video_id}

        job_data.update(updates)
        job_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        job_file.write_text(json.dumps(job_data, indent=2))
        logger.debug(f"Updated job {video_id}: {list(updates.keys())}")

    async def get_job(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get a job metadata document."""
        job_file = self._get_job_file(video_id)
        if not job_file.exists():
            return None
        return json.loads(job_file.read_text())

    async def list_jobs(self) -> list:
        """List all job metadata documents."""
        jobs = []
        for f in self.metadata_dir.glob("*.json"):
            try:
                jobs.append(json.loads(f.read_text()))
            except Exception:
                continue
        # Sort by creation time, newest first
        jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return jobs

    async def delete_job(self, video_id: str) -> bool:
        """Delete a job and all its associated files."""
        deleted = False

        # Remove metadata
        job_file = self._get_job_file(video_id)
        if job_file.exists():
            job_file.unlink()
            deleted = True

        # Remove uploads
        upload_dir = self.uploads_dir / video_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
            deleted = True

        # Remove processed files
        processed_dir = self.processed_dir / video_id
        if processed_dir.exists():
            shutil.rmtree(processed_dir)
            deleted = True

        # Remove temp
        self.cleanup_temp(video_id)

        if deleted:
            logger.info(f"Deleted job and all associated files: {video_id}")
        return deleted


# Singleton instance
local_storage = LocalStorageService()
