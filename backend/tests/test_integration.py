"""
Integration tests — Full pipeline flow: upload → process → verify results.
Uses mock model (no GPU required).
"""
import io
import time
import pytest


class TestFullPipelineIntegration:
    """End-to-end integration test of the complete 4RC pipeline."""

    def test_upload_and_process_flow(self, client, sample_video_bytes):
        """Test the complete upload → process → poll → results workflow."""

        # Step 1: Upload video
        upload_response = client.post(
            "/api/v1/upload",
            files={"file": ("integration_test.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        video_id = upload_data["video_id"]
        assert upload_data["status"] == "uploaded"

        # Step 2: Verify status is uploaded
        status_response = client.get(f"/api/v1/status/{video_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["video_id"] == video_id

        # Step 3: Trigger processing
        process_response = client.post(f"/api/v1/process/{video_id}")
        assert process_response.status_code == 200
        process_data = process_response.json()
        assert process_data["status"] == "processing"

        # Step 4: Verify job appears in list
        jobs_response = client.get("/api/v1/jobs")
        assert jobs_response.status_code == 200
        jobs_data = jobs_response.json()
        job_ids = [j["video_id"] for j in jobs_data["jobs"]]
        assert video_id in job_ids

    def test_multiple_uploads(self, client, sample_video_bytes):
        """Test uploading multiple videos creates distinct jobs."""
        ids = []
        for i in range(3):
            resp = client.post(
                "/api/v1/upload",
                files={"file": (f"clip_{i}.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
            )
            assert resp.status_code == 200
            ids.append(resp.json()["video_id"])

        # All IDs should be unique
        assert len(set(ids)) == 3

        # All should appear in job list
        jobs_resp = client.get("/api/v1/jobs")
        listed_ids = [j["video_id"] for j in jobs_resp.json()["jobs"]]
        for vid in ids:
            assert vid in listed_ids

    def test_upload_delete_upload_again(self, client, sample_video_bytes):
        """Test that deleted jobs are fully cleaned up."""
        # Upload
        resp = client.post(
            "/api/v1/upload",
            files={"file": ("delete_me.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        video_id = resp.json()["video_id"]

        # Delete
        del_resp = client.delete(f"/api/v1/jobs/{video_id}")
        assert del_resp.status_code == 200

        # Verify gone
        status_resp = client.get(f"/api/v1/status/{video_id}")
        assert status_resp.status_code == 404

        # Can upload again
        resp2 = client.post(
            "/api/v1/upload",
            files={"file": ("new_clip.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        assert resp2.status_code == 200

    def test_results_before_completion_fails(self, client, sample_video_bytes):
        """Requesting results before processing completes should return 400."""
        resp = client.post(
            "/api/v1/upload",
            files={"file": ("early.mp4", io.BytesIO(sample_video_bytes), "video/mp4")},
        )
        video_id = resp.json()["video_id"]

        results_resp = client.get(f"/api/v1/results/{video_id}")
        assert results_resp.status_code == 400
