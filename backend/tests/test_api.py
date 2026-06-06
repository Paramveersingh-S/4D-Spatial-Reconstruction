"""
API endpoint tests for the 4RC backend.
Tests upload, processing trigger, status, results, and job management.
"""
import io
import pytest


class TestRootEndpoint:
    """Test the root health check endpoint."""

    def test_root_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "version" in data

    def test_root_has_docs_link(self, client):
        response = client.get("/")
        data = response.json()
        assert data["docs"] == "/docs"


class TestHealthEndpoint:
    """Test the detailed health check endpoint."""

    def test_health_returns_200(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "device" in data
        assert isinstance(data["gpu_available"], bool)


class TestVideoUpload:
    """Test the video upload endpoint."""

    def test_upload_valid_mp4(self, client, sample_video_bytes):
        response = client.post(
            "/api/v1/upload",
            files={"file": ("test_clip.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "video_id" in data
        assert data["filename"] == "test_clip.mp4"
        assert data["status"] == "uploaded"
        assert data["size_bytes"] > 0

    def test_upload_returns_unique_ids(self, client, sample_video_bytes):
        r1 = client.post(
            "/api/v1/upload",
            files={"file": ("clip1.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        r2 = client.post(
            "/api/v1/upload",
            files={"file": ("clip2.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        assert r1.json()["video_id"] != r2.json()["video_id"]

    def test_upload_rejects_invalid_type(self, client):
        response = client.post(
            "/api/v1/upload",
            files={"file": ("document.pdf", io.BytesIO(b"fake pdf"), "application/pdf")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_upload_rejects_invalid_extension(self, client):
        response = client.post(
            "/api/v1/upload",
            files={"file": ("video.txt", io.BytesIO(b"fake"), "video/mp4")},
        )
        assert response.status_code == 400
        assert "Invalid file extension" in response.json()["detail"]

    def test_upload_rejects_empty_file(self, client):
        response = client.post(
            "/api/v1/upload",
            files={"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")},
        )
        assert response.status_code == 400
        assert "Empty file" in response.json()["detail"]


class TestJobStatus:
    """Test the job status endpoint."""

    def test_status_after_upload(self, client, sample_video_bytes):
        # Upload first
        upload_response = client.post(
            "/api/v1/upload",
            files={"file": ("clip.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        video_id = upload_response.json()["video_id"]

        # Check status
        status_response = client.get(f"/api/v1/status/{video_id}")
        assert status_response.status_code == 200
        data = status_response.json()
        assert data["video_id"] == video_id
        assert data["status"] in ["pending", "uploaded"]

    def test_status_not_found(self, client):
        response = client.get("/api/v1/status/nonexistent_video")
        assert response.status_code == 404


class TestProcessing:
    """Test the processing trigger endpoint."""

    def test_trigger_processing(self, client, sample_video_bytes):
        # Upload
        upload_resp = client.post(
            "/api/v1/upload",
            files={"file": ("clip.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        video_id = upload_resp.json()["video_id"]

        # Trigger processing
        process_resp = client.post(f"/api/v1/process/{video_id}")
        assert process_resp.status_code == 200
        data = process_resp.json()
        assert data["status"] == "processing"
        assert data["video_id"] == video_id

    def test_process_nonexistent_video(self, client):
        response = client.post("/api/v1/process/nonexistent")
        assert response.status_code == 404


class TestJobManagement:
    """Test job listing and deletion."""

    def test_list_jobs(self, client, sample_video_bytes):
        # Upload a video
        client.post(
            "/api/v1/upload",
            files={"file": ("clip.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )

        # List jobs
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total_count" in data
        assert data["total_count"] >= 1

    def test_delete_job(self, client, sample_video_bytes):
        # Upload
        upload_resp = client.post(
            "/api/v1/upload",
            files={"file": ("clip.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        video_id = upload_resp.json()["video_id"]

        # Delete
        delete_resp = client.delete(f"/api/v1/jobs/{video_id}")
        assert delete_resp.status_code == 200

        # Verify deleted
        status_resp = client.get(f"/api/v1/status/{video_id}")
        assert status_resp.status_code == 404

    def test_delete_nonexistent(self, client):
        response = client.delete("/api/v1/jobs/nonexistent")
        assert response.status_code == 404


class TestResults:
    """Test the results endpoint."""

    def test_results_not_completed(self, client, sample_video_bytes):
        # Upload (but don't process)
        upload_resp = client.post(
            "/api/v1/upload",
            files={"file": ("clip.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        video_id = upload_resp.json()["video_id"]

        # Try to get results
        response = client.get(f"/api/v1/results/{video_id}")
        assert response.status_code == 400
        assert "not completed" in response.json()["detail"]

    def test_results_not_found(self, client):
        response = client.get("/api/v1/results/nonexistent")
        assert response.status_code == 404
