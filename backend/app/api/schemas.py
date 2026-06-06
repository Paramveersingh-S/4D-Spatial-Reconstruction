"""
Pydantic schemas for API request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class JobStatus(str, Enum):
    """Processing job status states."""
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTING_FRAMES = "extracting_frames"
    EXTRACTING_FLOW = "extracting_flow"
    RECONSTRUCTING_4D = "reconstructing_4d"
    GENERATING_POINT_CLOUD = "generating_point_cloud"
    EXTRACTING_TRAJECTORIES = "extracting_trajectories"
    COMPILING_ASSETS = "compiling_assets"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ObjectCategory(str, Enum):
    """Tracked object categories."""
    DRONE = "drone"
    VEHICLE = "vehicle"
    PEDESTRIAN = "pedestrian"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


# ──────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────

class VideoProcessRequest(BaseModel):
    """Request to trigger video processing."""
    video_id: str = Field(..., description="Unique identifier for the uploaded video")
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional processing parameters",
    )


class ProcessingOptions(BaseModel):
    """Optional parameters for customizing the 4RC pipeline."""
    frame_sample_rate: int = Field(default=5, ge=1, le=30, description="Extract every Nth frame")
    max_frames: int = Field(default=100, ge=10, le=500, description="Max frames to process")
    point_density: float = Field(default=0.5, ge=0.1, le=1.0, description="Point cloud density")
    target_resolution: int = Field(default=512, ge=256, le=1024, description="Frame resize target")


# ──────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str
    model_loaded: bool
    firebase_connected: bool
    gpu_available: bool
    device: str


class VideoUploadResponse(BaseModel):
    """Response after successful video upload."""
    video_id: str
    filename: str
    size_bytes: int
    storage_path: str
    status: JobStatus = JobStatus.UPLOADED
    message: str = "Video uploaded successfully. Ready for processing."


class ProcessingTriggerResponse(BaseModel):
    """Response after triggering processing."""
    video_id: str
    status: JobStatus = JobStatus.PROCESSING
    message: str
    estimated_time_seconds: Optional[int] = None


class JobStatusResponse(BaseModel):
    """Current status of a processing job."""
    video_id: str
    status: JobStatus
    progress: float = Field(default=0.0, ge=0.0, le=100.0, description="Progress percentage")
    current_step: Optional[str] = None
    steps_completed: int = 0
    total_steps: int = 6
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class Vec3(BaseModel):
    """3D vector."""
    x: float
    y: float
    z: float


class TrajectoryPoint(BaseModel):
    """A single point in an object's trajectory."""
    t: float = Field(..., description="Timestamp in seconds")
    position: Vec3
    heading: float = Field(..., description="Heading angle in radians")


class TrackedObjectResult(BaseModel):
    """A tracked object extracted from the reconstruction."""
    id: str
    name: str
    category: ObjectCategory
    color: str
    base_speed: float = Field(..., description="Estimated speed in km/h")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    trajectory: List[TrajectoryPoint]
    bbox_size: Optional[Vec3] = None


class PointCloudMetadata(BaseModel):
    """Metadata about the generated point cloud."""
    num_points: int
    format: str = "ply"
    file_size_bytes: int
    bounds_min: Vec3
    bounds_max: Vec3
    has_colors: bool = True
    has_normals: bool = False


class ProcessingResultResponse(BaseModel):
    """Full results of a completed processing job."""
    video_id: str
    status: JobStatus = JobStatus.COMPLETED
    point_cloud_url: str
    point_cloud_metadata: PointCloudMetadata
    trajectory_url: str
    tracked_objects: List[TrackedObjectResult]
    total_frames_processed: int
    processing_time_seconds: float
    model_version: str


class JobListItem(BaseModel):
    """Summary of a job for list views."""
    video_id: str
    filename: str
    status: JobStatus
    progress: float = 0.0
    created_at: Optional[str] = None
    tracked_objects_count: int = 0


class JobListResponse(BaseModel):
    """Response for listing all jobs."""
    jobs: List[JobListItem]
    total_count: int


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    video_id: Optional[str] = None
