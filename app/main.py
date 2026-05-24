from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import traceback

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection
from app.core.exceptions import AppException
from app.core.redis import redis_pubsub
from app.core.cache import cache

# Boot-time guardrails: prevent shipping insecure config
if not settings.DEBUG:
    if "*" in settings.CORS_ORIGINS or not settings.CORS_ORIGINS:
        raise RuntimeError(
            "CORS_ORIGINS must be an explicit allow-list in production "
            "(no wildcards, no empty list)."
        )
    known_weak = {
        "your-super-secret-key-here",
        "flame-app-super-secret-key-change-in-production-2024",
        "changeme",
        "secret",
    }
    if (
        settings.JWT_SECRET_KEY.strip().lower() in known_weak
        or len(settings.JWT_SECRET_KEY) < 32
    ):
        raise RuntimeError("JWT_SECRET_KEY is weak. Use at least 32 random bytes.")

# Configure logging
logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

# Reduce noisy third-party loggers
for noisy_logger in [
    "pymongo", "pymongo.topology", "pymongo.connection",
    "pymongo.command", "pymongo.serverSelection",
    "botocore", "boto3", "urllib3", "s3transfer",
    "passlib", "passlib.utils", "passlib.registry",
]:
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

from app.auth.routes import router as auth_router
from app.community.routes import router as community_router
from app.chat.routes import router as chat_router, sticker_router
from app.chat.websocket import router as ws_router
from app.users.routes import router as users_router
from app.billing.routes import router as billing_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Starting up Flame API...")
    await connect_to_mongo()
    logger.info("MongoDB connected")

    # Connect to Redis for WebSocket pub/sub
    from app.chat.websocket import handle_redis_message
    await redis_pubsub.connect()
    redis_pubsub.set_message_handler(handle_redis_message)
    await redis_pubsub.start_listener()

    # Connect to Redis cache (optional - app works without it)
    try:
        await cache.connect()
        if cache.is_connected():
            logger.info("Redis cache connected")
        else:
            logger.warning("Redis cache not available - running without cache")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e} - running without cache")

    yield

    # Shutdown
    logger.info("Shutting down Flame API...")
    await redis_pubsub.disconnect()
    await cache.disconnect()
    await close_mongo_connection()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    max_age=600,
)


# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.detail.get("message") if isinstance(exc.detail, dict) else str(exc.detail),
                "details": exc.details,
            },
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions. Never leak internals in production."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    logger.error(traceback.format_exc())

    if settings.DEBUG:
        body = {
            "code": "SERVER_ERROR",
            "message": str(exc),
            "details": traceback.format_exc(),
        }
    else:
        body = {"code": "SERVER_ERROR", "message": "Internal server error", "details": None}

    return JSONResponse(
        status_code=500,
        content={"success": False, "error": body},
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with component status."""
    from app.core.database import db

    health = {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "components": {}
    }

    # Check MongoDB
    try:
        await db.client.admin.command('ping')
        health["components"]["mongodb"] = {"status": "healthy"}
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["mongodb"] = {"status": "unhealthy", "error": str(e)}

    # Check Redis
    if cache.is_connected():
        try:
            await cache.redis.ping()
            health["components"]["redis"] = {"status": "healthy"}
        except Exception as e:
            health["status"] = "degraded"
            health["components"]["redis"] = {"status": "unhealthy", "error": str(e)}
    else:
        health["components"]["redis"] = {"status": "not_connected", "note": "Running without cache"}

    return health


# Include routers
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_router, prefix=settings.API_V1_PREFIX)
app.include_router(sticker_router, prefix=settings.API_V1_PREFIX)
app.include_router(billing_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }
