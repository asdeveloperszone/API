"""
API route handlers for ASDroid TikTok API.

Endpoints:
  GET  /api/v1/health   – Health check
  GET  /api/v1/info     – API metadata & rate-limit status
  POST /api/v1/resolve  – Resolve TikTok URL → video info + download URL
  GET  /api/v1/download – Stream video to client

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import Settings, get_settings
from app.models import (
    APIResponse,
    DownloadRequest,
    HealthResponse,
    InfoResponse,
    RateLimitInfo,
    VideoInfo,
)
from app.services.resolver import resolve_tiktok_video
from app.services.streamer import stream_video
from app.utils.cache import video_cache
from app.utils.exceptions import InvalidURLException
from app.utils.logger import get_logger
from app.utils.validators import sanitize_input, validate_tiktok_url

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["TikTok Downloader"])

# Module-level limiter (shared with app.main)
limiter = Limiter(key_func=get_remote_address)

# App start time for uptime calculation
_START_TIME: float = time.monotonic()


# ── Health ────────────────────────────────────────────────────────────────────


@router.get(
    "/health",
    response_model=APIResponse,
    summary="Health check",
    description="Returns API health status and uptime.",
)
@limiter.limit("60/minute")
async def health_check(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> APIResponse:
    """Return API health status.

    Args:
        request: FastAPI request (needed by SlowAPI limiter).
        settings: Injected application settings.

    Returns:
        APIResponse wrapping a HealthResponse payload.
    """
    cache_size = await video_cache.size()
    uptime = time.monotonic() - _START_TIME

    health = HealthResponse(
        status="ok",
        version=settings.API_VERSION,
        uptime_seconds=round(uptime, 2),
        rate_limits=RateLimitInfo(
            limit_per_minute=settings.RATE_LIMIT_PER_MINUTE,
            limit_per_hour=settings.RATE_LIMIT_PER_HOUR,
        ),
        cache_size=cache_size,
    )
    logger.debug("Health check requested, uptime=%.1fs", uptime)
    return APIResponse(data=health.model_dump())


# ── Info ──────────────────────────────────────────────────────────────────────


@router.get(
    "/info",
    response_model=APIResponse,
    summary="API information",
    description="Returns API version, author, and rate-limit configuration.",
)
@limiter.limit("60/minute")
async def api_info(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> APIResponse:
    """Return API metadata and available endpoints.

    Args:
        request: FastAPI request (needed by SlowAPI limiter).
        settings: Injected application settings.

    Returns:
        APIResponse wrapping an InfoResponse payload.
    """
    uptime = time.monotonic() - _START_TIME
    info = InfoResponse(
        api_name=settings.API_TITLE,
        version=settings.API_VERSION,
        author="M.ASIM 🥰❤️👑 — Pakistan",
        description=settings.API_DESCRIPTION,
        uptime_seconds=round(uptime, 2),
        endpoints=[
            {"method": "GET",  "path": "/api/v1/health",   "description": "Health check"},
            {"method": "GET",  "path": "/api/v1/info",     "description": "API metadata"},
            {"method": "POST", "path": "/api/v1/resolve",  "description": "Resolve TikTok URL"},
            {"method": "GET",  "path": "/api/v1/download", "description": "Stream video file"},
        ],
        rate_limits=RateLimitInfo(
            limit_per_minute=settings.RATE_LIMIT_PER_MINUTE,
            limit_per_hour=settings.RATE_LIMIT_PER_HOUR,
        ),
    )
    return APIResponse(data=info.model_dump())


# ── Resolve ───────────────────────────────────────────────────────────────────


@router.post(
    "/resolve",
    response_model=APIResponse,
    summary="Resolve TikTok URL",
    description=(
        "Accepts a TikTok video URL and returns video metadata "
        "including a direct watermark-free download URL."
    ),
)
@limiter.limit("30/minute;1000/hour")
async def resolve_video(
    payload: DownloadRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> APIResponse:
    """Resolve a TikTok URL to video metadata + download URL.

    Args:
        payload: Request body containing the TikTok URL and optional quality.
        request: FastAPI request (needed by SlowAPI limiter).
        settings: Injected application settings.

    Returns:
        APIResponse wrapping a VideoInfo payload.
    """
    raw_url = sanitize_input(payload.url)

    if not validate_tiktok_url(raw_url):
        raise InvalidURLException(
            f"The provided URL is not a recognised TikTok video URL: {raw_url!r}"
        )

    logger.info("Resolve request from %s for URL: %s", get_remote_address(request), raw_url)
    video_info: VideoInfo = await resolve_tiktok_video(raw_url)

    logger.info(
        "Resolved video_id=%s author=@%s duration=%ds",
        video_info.video_id,
        video_info.author,
        video_info.duration,
    )
    return APIResponse(data=video_info.model_dump())


# ── Download / Stream ─────────────────────────────────────────────────────────


@router.get(
    "/download",
    summary="Stream video file",
    description=(
        "Streams the TikTok video directly to the client. "
        "Pass the TikTok URL as a query parameter. "
        "No file is stored on the server."
    ),
    response_class=StreamingResponse,
)
@limiter.limit("20/minute;500/hour")
async def download_video(
    request: Request,
    url: str = Query(..., description="URL-encoded TikTok video URL"),
    quality: str = Query(default="hd", description="Video quality: hd or sd"),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Proxy-stream a TikTok video to the HTTP client.

    The TikTok URL is first resolved (with cache), then the CDN stream is
    piped directly to the response with no disk I/O.

    Args:
        request: FastAPI request (range headers + SlowAPI).
        url: URL-encoded TikTok video URL.
        quality: "hd" or "sd" quality preference.
        settings: Injected application settings.

    Returns:
        StreamingResponse with video/mp4 content.
    """
    decoded_url = unquote(url.strip())
    clean_url = sanitize_input(decoded_url)

    if not validate_tiktok_url(clean_url):
        raise InvalidURLException(
            f"Invalid TikTok URL provided to /download: {clean_url!r}"
        )

    logger.info(
        "Stream request from %s for URL: %s (quality=%s)",
        get_remote_address(request),
        clean_url,
        quality,
    )

    video_info: VideoInfo = await resolve_tiktok_video(clean_url)
    return await stream_video(video_info.download_url, request)
