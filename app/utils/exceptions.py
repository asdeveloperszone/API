"""
Custom exception classes for ASDroid TikTok API.

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations


class TikTokAPIException(Exception):
    """Base exception for all TikTok API errors."""

    error_code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.error_code})"


class InvalidURLException(TikTokAPIException):
    """Raised when the provided URL is not a valid TikTok URL."""

    error_code = "INVALID_URL"
    http_status = 400


class VideoNotFoundException(TikTokAPIException):
    """Raised when the video cannot be found or has been removed."""

    error_code = "VIDEO_NOT_FOUND"
    http_status = 404


class TikTokBlockedException(TikTokAPIException):
    """Raised when TikTok blocks or throttles our request."""

    error_code = "TIKTOK_BLOCKED"
    http_status = 503


class RateLimitExceededException(TikTokAPIException):
    """Raised when our own API rate limit is exceeded."""

    error_code = "RATE_LIMITED"
    http_status = 429

    def __init__(self, message: str, *, retry_after: int = 60, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ExtractionFailedException(TikTokAPIException):
    """Raised when all extraction strategies fail."""

    error_code = "EXTRACTION_FAILED"
    http_status = 502


class StreamingException(TikTokAPIException):
    """Raised when video streaming fails mid-transfer."""

    error_code = "STREAM_ERROR"
    http_status = 502
