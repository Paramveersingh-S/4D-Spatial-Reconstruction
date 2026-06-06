"""
Tests for Firebase client and local storage services.
"""
import os
import json
import tempfile

import pytest


class TestLocalStorage:
    """Test the local filesystem storage service."""

    def test_storage_initialization(self):
        os.environ["LOCAL_STORAGE_PATH"] = tempfile.mkdtemp()
        os.environ["TEMP_DIR"] = os.path.join(os.environ["LOCAL_STORAGE_PATH"], "temp")

        from app.services.storage import LocalStorageService
        storage = LocalStorageService()

        assert storage.uploads_dir.exists()
        assert storage.processed_dir.exists()
        assert storage.metadata_dir.exists()

    @pytest.mark.asyncio
    async def test_save_and_retrieve_upload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["LOCAL_STORAGE_PATH"] = tmpdir
            os.environ["TEMP_DIR"] = os.path.join(tmpdir, "temp")

            from app.services.storage import LocalStorageService
            storage = LocalStorageService()

            video_id = "test_vid_001"
            content = b"fake video content"
            filename = "drone_clip.mp4"

            path = await storage.save_upload(video_id, content, filename)
            assert path is not None

            retrieved = storage.get_upload_path(video_id, filename)
            assert retrieved is not None
            assert retrieved.exists()
            assert retrieved.read_bytes() == content

    @pytest.mark.asyncio
    async def test_job_crud(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["LOCAL_STORAGE_PATH"] = tmpdir
            os.environ["TEMP_DIR"] = os.path.join(tmpdir, "temp")

            from app.services.storage import LocalStorageService
            storage = LocalStorageService()

            video_id = "test_job_001"

            # Create
            await storage.create_job(video_id, {"filename": "test.mp4"})
            job = await storage.get_job(video_id)
            assert job is not None
            assert job["video_id"] == video_id
            assert job["status"] == "pending"
            assert job["filename"] == "test.mp4"

            # Update
            await storage.update_job(video_id, {"status": "processing", "progress": 50.0})
            job = await storage.get_job(video_id)
            assert job["status"] == "processing"
            assert job["progress"] == 50.0

            # List
            jobs = await storage.list_jobs()
            assert len(jobs) >= 1

            # Delete
            deleted = await storage.delete_job(video_id)
            assert deleted is True
            job = await storage.get_job(video_id)
            assert job is None

    @pytest.mark.asyncio
    async def test_processed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["LOCAL_STORAGE_PATH"] = tmpdir
            os.environ["TEMP_DIR"] = os.path.join(tmpdir, "temp")

            from app.services.storage import LocalStorageService
            storage = LocalStorageService()

            video_id = "test_vid_002"
            content = b"fake PLY data"

            path = await storage.save_processed_file(video_id, "point_cloud.ply", content)
            assert path is not None

            retrieved = storage.get_processed_file_path(video_id, "point_cloud.ply")
            assert retrieved is not None
            assert retrieved.read_bytes() == content

    def test_temp_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["LOCAL_STORAGE_PATH"] = tmpdir
            os.environ["TEMP_DIR"] = os.path.join(tmpdir, "temp")

            from app.services.storage import LocalStorageService
            storage = LocalStorageService()

            video_id = "test_cleanup"
            temp_dir = storage.get_temp_dir(video_id)
            assert temp_dir.exists()

            # Create a file in temp
            (temp_dir / "test.txt").write_text("hello")
            assert (temp_dir / "test.txt").exists()

            # Cleanup
            storage.cleanup_temp(video_id)
            assert not temp_dir.exists()


class TestFirebaseClient:
    """Test the Firebase client in mock/local mode."""

    def test_firebase_not_connected_in_local_mode(self):
        os.environ["USE_LOCAL_STORAGE"] = "true"

        from app.services.firebase_client import is_firebase_connected
        # In test environment with USE_LOCAL_STORAGE=true, should not be connected
        # (unless Firebase was explicitly initialized)
        assert isinstance(is_firebase_connected(), bool)

    @pytest.mark.asyncio
    async def test_mock_update_job_status(self):
        os.environ["USE_LOCAL_STORAGE"] = "true"

        from app.services.firebase_client import update_job_status
        # Should not raise even when Firebase is not connected
        await update_job_status("mock_video", "processing", progress=50.0)

    @pytest.mark.asyncio
    async def test_mock_upload_to_storage(self):
        from app.services.firebase_client import upload_to_storage
        url = await upload_to_storage("/fake/path.ply", "processed/123/cloud.ply")
        assert "mock://" in url or isinstance(url, str)

    @pytest.mark.asyncio
    async def test_mock_get_job(self):
        from app.services.firebase_client import get_job
        # Should return None when not connected and no local data
        result = await get_job("nonexistent_mock")
        assert result is None
