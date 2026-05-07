"""
Configuration module for ASDroid TikTok API.
All settings are loaded from environment variables with sensible defaults.

Author: M.ASIM 🥰❤️👑
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Metadata ──────────────────────────────────────────────────────────
    API_VERSION: str = "2.0.0"
    API_TITLE: str = "ASDroid TikTok API"
    API_DESCRIPTION: str = (
        "Production-ready TikTok Video Downloader API "
        "built by M.ASIM 🥰❤️👑 from Pakistan"
    )
    DEBUG_MODE: bool = False

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_HOUR: int = 1000

    # ── Caching ───────────────────────────────────────────────────────────────
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    # ── TikTok Request Config ─────────────────────────────────────────────────
    TIKTOK_USER_AGENT: str = (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    )
    TIKTOK_TIMEOUT_SECONDS: int = 20
    TIKTOK_MAX_RETRIES: int = 3
    TIKTOK_RETRY_BACKOFF: float = 1.5  # seconds multiplier

    # ── Streaming ─────────────────────────────────────────────────────────────
    STREAM_CHUNK_SIZE_BYTES: int = 1_048_576  # 1 MB
    MAX_VIDEO_SIZE_MB: int = 500

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "OPTIONS"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    @property
    def tiktok_headers(self) -> dict[str, str]:
        """Returns headers to use for TikTok requests."""
        return {
            "User-Agent": self.TIKTOK_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }

    @property
    def rate_limit_string_per_minute(self) -> str:
        """SlowAPI rate limit string for per-minute limiting."""
        return f"{self.RATE_LIMIT_PER_MINUTE}/minute"

    @property
    def rate_limit_string_per_hour(self) -> str:
        """SlowAPI rate limit string for per-hour limiting."""
        return f"{self.RATE_LIMIT_PER_HOUR}/hour"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance (singleton)."""
    return Settings()
