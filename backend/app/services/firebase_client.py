"""
Firebase Admin SDK client wrapper.
Provides Firebase Storage and Firestore operations.
Falls back gracefully to local storage when credentials are not available.
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("firebase")

# Firebase state
_firebase_initialized = False
_db = None
_bucket = None


def initialize_firebase() -> bool:
    """
    Initialize Firebase Admin SDK.
    Returns True if successfully initialized, False if running in mock/local mode.
    """
    global _firebase_initialized, _db, _bucket

    if _firebase_initialized:
        return True

    if settings.USE_LOCAL_STORAGE:
        logger.info("Firebase disabled — using local storage mode")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, storage

        cred_path = Path(settings.FIREBASE_CREDENTIALS_PATH)
        if not cred_path.exists():
            logger.warning(
                f"Firebase credentials not found at: {cred_path}. "
                "Running in local storage mode."
            )
            return False

        cred = credentials.Certificate(str(cred_path))
        firebase_admin.initialize_app(cred, {
            "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
        })

        _db = firestore.client()
        _bucket = storage.bucket()
        _firebase_initialized = True

        logger.info(
            f"Firebase initialized — Project: {settings.GOOGLE_CLOUD_PROJECT}, "
            f"Bucket: {settings.FIREBASE_STORAGE_BUCKET}"
        )
        return True

    except ImportError:
        logger.warning("firebase-admin not installed. Running in local storage mode.")
        return False
    except Exception as e:
        logger.warning(f"Firebase initialization failed: {e}. Running in local storage mode.")
        return False


def is_firebase_connected() -> bool:
    """Check if Firebase is connected and operational."""
    return _firebase_initialized and _db is not None


# ──────────────────────────────────────────────
# Firestore Operations
# ──────────────────────────────────────────────

JOBS_COLLECTION = "reconstruction_jobs"


async def create_job(video_id: str, metadata: Dict[str, Any]) -> None:
    """Create a new reconstruction job document in Firestore."""
    if not is_firebase_connected():
        logger.debug(f"[Mock Firestore] CREATE job: {video_id}")
        return

    doc_ref = _db.collection(JOBS_COLLECTION).document(video_id)
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
    doc_ref.set(job_data)
    logger.info(f"Firestore: Created job {video_id}")


async def update_job_status(
    video_id: str,
    status: str,
    progress: float = 0.0,
    current_step: Optional[str] = None,
    steps_completed: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Update a job's status in Firestore."""
    if not is_firebase_connected():
        logger.debug(f"[Mock Firestore] UPDATE {video_id} -> {status} ({progress:.1f}%)")
        return

    doc_ref = _db.collection(JOBS_COLLECTION).document(video_id)
    payload = {
        "status": status,
        "progress": progress,
        "current_step": current_step,
        "steps_completed": steps_completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        payload.update(metadata)

    doc_ref.set(payload, merge=True)
    logger.info(f"Firestore: Updated {video_id} -> {status}")


async def get_job(video_id: str) -> Optional[Dict[str, Any]]:
    """Get a job document from Firestore."""
    if not is_firebase_connected():
        logger.debug(f"[Mock Firestore] GET job: {video_id}")
        return None

    doc_ref = _db.collection(JOBS_COLLECTION).document(video_id)
    doc = doc_ref.get()
    return doc.to_dict() if doc.exists else None


async def list_jobs() -> List[Dict[str, Any]]:
    """List all job documents from Firestore."""
    if not is_firebase_connected():
        logger.debug("[Mock Firestore] LIST jobs")
        return []

    docs = _db.collection(JOBS_COLLECTION).order_by(
        "created_at", direction="DESCENDING"
    ).stream()
    return [doc.to_dict() for doc in docs]


async def delete_job(video_id: str) -> bool:
    """Delete a job document from Firestore."""
    if not is_firebase_connected():
        logger.debug(f"[Mock Firestore] DELETE job: {video_id}")
        return True

    doc_ref = _db.collection(JOBS_COLLECTION).document(video_id)
    doc_ref.delete()
    logger.info(f"Firestore: Deleted job {video_id}")
    return True


# ──────────────────────────────────────────────
# Firebase Storage Operations
# ──────────────────────────────────────────────

async def upload_to_storage(local_path: str, destination_blob: str) -> str:
    """Upload a file to Firebase Storage and return the public URL."""
    if not is_firebase_connected():
        logger.debug(f"[Mock Storage] UPLOAD {local_path} -> {destination_blob}")
        return f"mock://storage/{destination_blob}"

    blob = _bucket.blob(destination_blob)
    blob.upload_from_filename(local_path)
    blob.make_public()
    url = blob.public_url
    logger.info(f"Storage: Uploaded {destination_blob} ({url})")
    return url


async def download_from_storage(source_blob: str, local_path: str) -> str:
    """Download a file from Firebase Storage to local filesystem."""
    if not is_firebase_connected():
        logger.debug(f"[Mock Storage] DOWNLOAD {source_blob} -> {local_path}")
        return local_path

    blob = _bucket.blob(source_blob)
    blob.download_to_filename(local_path)
    logger.info(f"Storage: Downloaded {source_blob}")
    return local_path


async def delete_from_storage(blob_name: str) -> bool:
    """Delete a file from Firebase Storage."""
    if not is_firebase_connected():
        logger.debug(f"[Mock Storage] DELETE {blob_name}")
        return True

    blob = _bucket.blob(blob_name)
    blob.delete()
    logger.info(f"Storage: Deleted {blob_name}")
    return True
