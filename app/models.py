"""
Pydantic models for request/response validation.

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, HttpUrl


# ── Request Models ────────────────────────────────────────────────────────────

class DownloadRequest(BaseModel):
    """Payload for POST /api/v1/resolve."""

    url: str = Field(
        ...,
        description="Full TikTok video URL (tiktok.com or vm.tiktok.com)",
        examples=["https://www.tiktok.com/@user/video/1234567890123456789"],
    )
    quality: Literal["hd", "sd"] = Field(
        default="hd",
        description="Preferred video quality",
    )

    @field_validator("url")
    @classmethod
    def url_must_not_be_blank(cls, v: str) -> str:
        """Ensure URL is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("URL must not be blank")
        return v.strip()


# ── Data Models ───────────────────────────────────────────────────────────────

class VideoInfo(BaseModel):
    """Resolved TikTok video metadata."""

    video_id: str = Field(..., description="TikTok video ID")
    author: str = Field(..., description="Creator username")
    author_id: str = Field(default="", description="Creator unique ID")
    description: str = Field(default="", description="Video caption/description")
    duration: int = Field(default=0, description="Video duration in seconds")
    download_url: str = Field(..., description="Direct watermark-free video URL")
    thumbnail_url: str = Field(default="", description="Video thumbnail URL")
    music_title: str = Field(default="", description="Background music title")
    music_url: str = Field(default="", description="Background music URL")
    play_count: int = Field(default=0, description="Number of plays")
    like_count: int = Field(default=0, description="Number of likes")
    comment_count: int = Field(default=0, description="Number of comments")
    share_count: int = Field(default=0, description="Number of shares")
    created_at: datetime | None = Field(default=None, description="Video creation time")
    original_url: str = Field(default="", description="Original TikTok URL")


# ── Response Models ───────────────────────────────────────────────────────────

class APIResponse(BaseModel):
    """Generic success response wrapper."""

    success: Literal[True] = True
    data: Any = Field(..., description="Response payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Structured error response."""

    success: Literal[False] = False
    error: str = Field(..., description="Human-readable error message")
    code: str = Field(..., description="Machine-readable error code")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RateLimitInfo(BaseModel):
    """Rate limit status info."""

    limit_per_minute: int
    limit_per_hour: int
    remaining_minute: int | None = None
    remaining_hour: int | None = None


class HealthResponse(BaseModel):
    """Response for GET /api/v1/health."""

    status: Literal["ok", "degraded", "down"] = "ok"
    version: str
    uptime_seconds: float
    rate_limits: RateLimitInfo
    cache_size: int = 0


class InfoResponse(BaseModel):
    """Response for GET /api/v1/info."""

    api_name: str
    version: str
    author: str
    description: str
    uptime_seconds: float
    endpoints: list[dict[str, str]]
    rate_limits: RateLimitInfo
