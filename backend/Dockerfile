# ──────────────────────────────────────────────
# Multi-stage Dockerfile for 4RC Backend
# ──────────────────────────────────────────────

# Stage 1: Python base with system dependencies
FROM python:3.11-slim as base

# System deps for OpenCV, ffmpeg, and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# ──────────────────────────────────────────────
# Stage 2: Install Python dependencies
# ──────────────────────────────────────────────
FROM base as deps

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ──────────────────────────────────────────────
# Stage 3: Application
# ──────────────────────────────────────────────
FROM deps as app

# Copy application code
COPY ./app ./app

# Create directories for storage
RUN mkdir -p /app/storage /app/temp /app/.model_cache && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment defaults
ENV HOST=0.0.0.0
ENV PORT=8000
ENV LOG_LEVEL=INFO
ENV USE_LOCAL_STORAGE=true
ENV LOCAL_STORAGE_PATH=/app/storage
ENV TEMP_DIR=/app/temp
ENV MODEL_CACHE_DIR=/app/.model_cache
ENV MODEL_DEVICE=cpu

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
