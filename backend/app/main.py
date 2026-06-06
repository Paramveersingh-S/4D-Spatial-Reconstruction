"""
The Impossible Drone Camera — FastAPI Backend
Main application entry point with CORS, lifespan management, and error handling.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from .core.config import settings
from .core.logging import setup_logging, get_logger
from .services import firebase_client
from .api import routes

# Initialize logging first
setup_logging()
logger = get_logger("main")


# ──────────────────────────────────────────────
# Lifespan Events
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # ── Startup ──
    logger.info("=" * 60)
    logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 60)

    # Initialize Firebase
    firebase_ok = firebase_client.initialize_firebase()
    if firebase_ok:
        logger.info("Firebase: Connected")
    else:
        logger.info("Firebase: Not connected — using local storage mode")

    # Log configuration
    logger.info(f"Device: {settings.MODEL_DEVICE}")
    logger.info(f"Model: {settings.MODEL_NAME}")
    logger.info(f"Local storage: {settings.USE_LOCAL_STORAGE}")
    logger.info(f"CORS origins: {settings.cors_origins_list}")
    logger.info(f"Max upload: {settings.MAX_UPLOAD_SIZE_MB}MB")
    logger.info("")
    logger.info("Server ready — accepting requests")
    logger.info("=" * 60)

    yield

    # ── Shutdown ──
    logger.info("Shutting down 4RC backend...")


# ──────────────────────────────────────────────
# Application Factory
# ──────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Backend API for The Impossible Drone Camera — "
        "4D spatial reconstruction via the 4RC model. "
        "Upload drone footage, run 4RC inference, and retrieve "
        "dense 4D point clouds and motion trajectories."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response


# ──────────────────────────────────────────────
# Exception Handlers
# ──────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "detail": str(exc.detail) if hasattr(exc, "detail") else "Resource not found"},
    )


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

# Include API router
app.include_router(routes.router, prefix="/api/v1")


# Root endpoint
@app.get("/", tags=["System"])
async def root():
    """Root health check endpoint."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs": "/docs",
        "firebase": "connected" if firebase_client.is_firebase_connected() else "local_mode",
    }
