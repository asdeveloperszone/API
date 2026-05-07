"""
ASDroid TikTok API – FastAPI application entry point.

Initialises middleware, exception handlers, lifespan events, and routes.

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import get_settings
from app.routers.download import router as download_router
from app.utils.cache import video_cache
from app.utils.exceptions import (
    ExtractionFailedException,
    InvalidURLException,
    RateLimitExceededException,
    StreamingException,
    TikTokAPIException,
    TikTokBlockedException,
    VideoNotFoundException,
)
from app.utils.logger import configure_logging, get_logger, request_id_var

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["1000/hour"])

# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown logic for the FastAPI application.

    Starts a background task to periodically purge expired cache entries.
    """
    logger.info(
        "🚀 ASDroid TikTok API v%s starting — built by M.ASIM 🥰❤️👑",
        settings.API_VERSION,
    )

    # Background cache janitor
    async def _cache_janitor() -> None:
        while True:
            await asyncio.sleep(120)  # every 2 minutes
            purged = await video_cache.purge_expired()
            if purged:
                logger.debug("Cache janitor purged %d expired entries", purged)

    task = asyncio.create_task(_cache_janitor())
    logger.info("Cache janitor started")

    yield  # ← application runs here

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("ASDroid TikTok API shutdown complete")


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Attach limiter to app state (required by SlowAPI)
app.state.limiter = limiter

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with timing and inject a request ID into context."""
    import uuid

    rid = uuid.uuid4().hex[:12]
    request_id_var.set(rid)

    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000

    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = rid
    return response


# ── Exception handlers ────────────────────────────────────────────────────────

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _error_response(message: str, code: str, http_status: int) -> JSONResponse:
    """Build a consistent error JSON response.

    Args:
        message: Human-readable error message.
        code: Machine-readable error code string.
        http_status: HTTP status code to use.

    Returns:
        JSONResponse with structured error payload.
    """
    return JSONResponse(
        status_code=http_status,
        content={
            "success": False,
            "error": message,
            "code": code,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )


@app.exception_handler(InvalidURLException)
async def invalid_url_handler(request: Request, exc: InvalidURLException) -> JSONResponse:
    logger.warning("Invalid URL: %s", exc.message)
    return _error_response(exc.message, exc.error_code, exc.http_status)


@app.exception_handler(VideoNotFoundException)
async def video_not_found_handler(request: Request, exc: VideoNotFoundException) -> JSONResponse:
    logger.warning("Video not found: %s", exc.message)
    return _error_response(exc.message, exc.error_code, exc.http_status)


@app.exception_handler(TikTokBlockedException)
async def tiktok_blocked_handler(request: Request, exc: TikTokBlockedException) -> JSONResponse:
    logger.error("TikTok blocked request: %s", exc.message)
    return _error_response(exc.message, exc.error_code, exc.http_status)


@app.exception_handler(ExtractionFailedException)
async def extraction_failed_handler(
    request: Request, exc: ExtractionFailedException
) -> JSONResponse:
    logger.error("Extraction failed: %s | detail: %s", exc.message, exc.detail)
    return _error_response(exc.message, exc.error_code, exc.http_status)


@app.exception_handler(StreamingException)
async def streaming_error_handler(request: Request, exc: StreamingException) -> JSONResponse:
    logger.error("Streaming error: %s", exc.message)
    return _error_response(exc.message, exc.error_code, exc.http_status)


@app.exception_handler(RateLimitExceededException)
async def our_rate_limit_handler(
    request: Request, exc: RateLimitExceededException
) -> JSONResponse:
    logger.warning("Rate limit hit: %s", exc.message)
    resp = _error_response(exc.message, exc.error_code, exc.http_status)
    resp.headers["Retry-After"] = str(exc.retry_after)
    return resp


@app.exception_handler(TikTokAPIException)
async def generic_tiktok_exception_handler(
    request: Request, exc: TikTokAPIException
) -> JSONResponse:
    logger.error("TikTok API error [%s]: %s", exc.error_code, exc.message)
    return _error_response(exc.message, exc.error_code, exc.http_status)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _error_response(
        "An internal server error occurred.",
        "INTERNAL_ERROR",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(download_router)


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root() -> JSONResponse:
    """Root endpoint – redirects to API docs."""
    return JSONResponse(
        content={
            "message": "ASDroid TikTok API 🥰❤️👑",
            "docs": "/docs",
            "health": "/api/v1/health",
            "version": settings.API_VERSION,
            "author": "M.ASIM — Pakistan",
        }
    )
