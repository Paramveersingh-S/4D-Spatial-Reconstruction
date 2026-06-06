"""
Core configuration module using Pydantic BaseSettings.
All configuration is driven by environment variables with sensible defaults.
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Application ---
    APP_NAME: str = "The Impossible Drone Camera - 4RC API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated CORS origins",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # --- Firebase / Google Cloud ---
    GOOGLE_CLOUD_PROJECT: str = Field(
        default="impossible-camera-dev",
        description="GCP project ID",
    )
    FIREBASE_CREDENTIALS_PATH: str = Field(
        default="firebase-adminsdk.json",
        description="Path to Firebase Admin SDK credentials JSON",
    )
    FIREBASE_STORAGE_BUCKET: str = Field(
        default="impossible-camera-dev.appspot.com",
        description="Firebase Storage bucket name",
    )

    # --- Storage ---
    USE_LOCAL_STORAGE: bool = Field(
        default=True,
        description="Use local filesystem instead of Firebase Storage (for dev)",
    )
    LOCAL_STORAGE_PATH: str = Field(
        default="./storage",
        description="Local storage directory when USE_LOCAL_STORAGE is True",
    )
    TEMP_DIR: str = Field(
        default="./temp",
        description="Temporary directory for processing files",
    )

    # --- Upload ---
    MAX_UPLOAD_SIZE_MB: int = Field(
        default=50,
        description="Maximum video upload size in megabytes",
    )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # --- AI / Model ---
    MODEL_NAME: str = Field(
        default="Luo-Yihang/4RC",
        description="Hugging Face model identifier for 4RC",
    )
    MODEL_DEVICE: str = Field(
        default="cpu",
        description="PyTorch device for model inference (cuda or cpu)",
    )
    MODEL_CACHE_DIR: str = Field(
        default="./.model_cache",
        description="Directory to cache downloaded model weights",
    )
    FRAME_SAMPLE_RATE: int = Field(
        default=5,
        description="Extract every Nth frame from video for inference",
    )
    MAX_FRAMES: int = Field(
        default=100,
        description="Maximum number of frames to process per video",
    )
    POINT_CLOUD_DENSITY: float = Field(
        default=0.5,
        description="Point cloud density factor (0.1 = sparse, 1.0 = dense)",
    )
    TARGET_RESOLUTION: int = Field(
        default=512,
        description="Resize video frames to this resolution for inference",
    )

    # --- Firebase Emulator (for local dev) ---
    USE_FIREBASE_EMULATOR: bool = Field(
        default=False,
        description="Use Firebase emulator for local development",
    )
    FIRESTORE_EMULATOR_HOST: str = Field(
        default="localhost:8080",
        description="Firestore emulator host",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
