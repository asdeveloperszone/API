"""
TikTok video resolution service.

Extraction pipeline:
  1. Resolve short-links via HTTP redirect chain
  2. Fetch page HTML with Android User-Agent
  3. Strategy A – parse __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON blob
  4. Strategy B – parse SIGI_STATE JSON blob (older pages)
  5. Strategy C – parse __NEXT_DATA__ JSON blob
  6. Retry up to MAX_RETRIES times with exponential back-off

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Any

import httpx

from app.config import get_settings
from app.models import VideoInfo
from app.utils.cache import video_cache
from app.utils.exceptions import (
    ExtractionFailedException,
    InvalidURLException,
    TikTokBlockedException,
    VideoNotFoundException,
)
from app.utils.logger import get_logger
from app.utils.validators import extract_video_id, is_short_link, sanitize_input, validate_tiktok_url

logger = get_logger(__name__)
settings = get_settings()

# ── Regex patterns ────────────────────────────────────────────────────────────

_UNIVERSAL_DATA_RE = re.compile(
    r'<script[^>]+\bid="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_SIGI_STATE_RE = re.compile(
    r'<script[^>]*>\s*window\[[\'""]SIGI_STATE[\'""]]\s*=\s*(\{.*?\});\s*(?:window\[|</script>)',
    re.DOTALL,
)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+\bid="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)

# ── Public API ────────────────────────────────────────────────────────────────


async def resolve_tiktok_video(url: str) -> VideoInfo:
    """Resolve a TikTok URL to a watermark-free VideoInfo.

    Tries the in-memory cache first to avoid redundant network calls.

    Args:
        url: TikTok video URL (full or short-link).

    Returns:
        Populated VideoInfo instance.

    Raises:
        InvalidURLException: URL is not a valid TikTok URL.
        VideoNotFoundException: Video has been deleted or is private.
        TikTokBlockedException: TikTok is rate-limiting us.
        ExtractionFailedException: All extraction strategies exhausted.
    """
    url = sanitize_input(url)

    if not validate_tiktok_url(url):
        raise InvalidURLException(f"Not a valid TikTok URL: {url!r}")

    # Check cache
    cached = await video_cache.get(url)
    if cached is not None:
        logger.debug("Cache hit for %s", url)
        return cached

    # Resolve short-links first
    final_url = await _resolve_short_link(url) if is_short_link(url) else url
    logger.info("Resolving TikTok URL: %s", final_url)

    info = await _fetch_with_retry(final_url)
    info.original_url = url

    # Store in cache
    await video_cache.set(url, info, ttl=settings.CACHE_TTL_SECONDS)
    if final_url != url:
        await video_cache.set(final_url, info, ttl=settings.CACHE_TTL_SECONDS)

    return info


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _resolve_short_link(url: str) -> str:
    """Follow TikTok short-link redirects and return the canonical URL.

    Args:
        url: Short-link URL (vm.tiktok.com or vt.tiktok.com).

    Returns:
        Final canonical TikTok URL after redirect chain.
    """
    logger.debug("Resolving short link: %s", url)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.TIKTOK_TIMEOUT_SECONDS,
            headers=settings.tiktok_headers,
        ) as client:
            resp = await client.head(url)
            final = str(resp.url)
            logger.debug("Short link resolved to: %s", final)
            return final
    except httpx.TimeoutException:
        logger.warning("Timeout resolving short link %s, using original", url)
        return url
    except Exception as exc:
        logger.warning("Failed to resolve short link %s: %s", url, exc)
        return url


async def _fetch_with_retry(url: str) -> VideoInfo:
    """Fetch and extract video info with exponential back-off retry.

    Args:
        url: Canonical TikTok video URL.

    Returns:
        Populated VideoInfo.

    Raises:
        TikTokBlockedException: HTTP 403/429 on all attempts.
        ExtractionFailedException: Parsing failed on all attempts.
    """
    last_error: Exception = ExtractionFailedException("Unknown error")

    for attempt in range(1, settings.TIKTOK_MAX_RETRIES + 1):
        try:
            html = await _fetch_page(url)
            info = _extract_from_html(html, url)
            return info
        except (TikTokBlockedException, VideoNotFoundException):
            raise
        except Exception as exc:
            last_error = exc
            wait = settings.TIKTOK_RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(
                "Extraction attempt %d/%d failed (%s), retrying in %.1fs",
                attempt,
                settings.TIKTOK_MAX_RETRIES,
                exc,
                wait,
            )
            if attempt < settings.TIKTOK_MAX_RETRIES:
                await asyncio.sleep(wait)

    raise ExtractionFailedException(
        f"All {settings.TIKTOK_MAX_RETRIES} extraction attempts failed",
        detail=str(last_error),
    )


async def _fetch_page(url: str) -> str:
    """Download TikTok page HTML.

    Args:
        url: Canonical TikTok video URL.

    Returns:
        Raw HTML string.

    Raises:
        TikTokBlockedException: HTTP 403 or 429.
        VideoNotFoundException: HTTP 404.
        ExtractionFailedException: Other HTTP errors.
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.TIKTOK_TIMEOUT_SECONDS,
        headers=settings.tiktok_headers,
    ) as client:
        try:
            resp = await client.get(url)
        except httpx.TimeoutException as exc:
            raise ExtractionFailedException(f"Request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ExtractionFailedException(f"Network error: {exc}") from exc

        if resp.status_code == 404:
            raise VideoNotFoundException(
                "Video not found – it may have been deleted or is private."
            )
        if resp.status_code in (403, 429):
            raise TikTokBlockedException(
                f"TikTok returned HTTP {resp.status_code} – we may be rate-limited."
            )
        if resp.status_code != 200:
            raise ExtractionFailedException(
                f"Unexpected HTTP {resp.status_code} from TikTok"
            )

        return resp.text


def _extract_from_html(html: str, original_url: str) -> VideoInfo:
    """Try all extraction strategies in order.

    Args:
        html: Raw TikTok page HTML.
        original_url: The URL that was fetched (for ID fallback).

    Returns:
        Populated VideoInfo.

    Raises:
        ExtractionFailedException: No strategy succeeded.
    """
    strategies = [
        ("UNIVERSAL_DATA", _extract_universal_data),
        ("SIGI_STATE", _extract_sigi_state),
        ("NEXT_DATA", _extract_next_data),
    ]

    for name, strategy in strategies:
        try:
            result = strategy(html)
            if result:
                logger.debug("Extraction succeeded via %s strategy", name)
                return _build_video_info(result, original_url)
        except Exception as exc:
            logger.debug("Strategy %s failed: %s", name, exc)

    raise ExtractionFailedException(
        "Unable to extract video data – TikTok may have changed its page structure."
    )


# ── Extraction strategies ─────────────────────────────────────────────────────


def _extract_universal_data(html: str) -> dict[str, Any] | None:
    """Parse __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON blob.

    Args:
        html: Raw TikTok page HTML.

    Returns:
        Normalised data dict, or None if not present.
    """
    match = _UNIVERSAL_DATA_RE.search(html)
    if not match:
        return None

    raw = json.loads(match.group(1))
    # Navigate to ItemModule or itemInfo.itemStruct
    item = _deep_find(raw, ["__DEFAULT_SCOPE__", "webapp.video-detail", "itemInfo", "itemStruct"])
    if item is None:
        item = _deep_find(raw, ["ItemModule"])
        if isinstance(item, dict):
            # ItemModule is a dict keyed by video ID
            item = next(iter(item.values()), None)
    return item


def _extract_sigi_state(html: str) -> dict[str, Any] | None:
    """Parse SIGI_STATE window variable (older TikTok pages).

    Args:
        html: Raw TikTok page HTML.

    Returns:
        Normalised data dict, or None if not present.
    """
    match = _SIGI_STATE_RE.search(html)
    if not match:
        return None

    raw = json.loads(match.group(1))
    item = _deep_find(raw, ["ItemModule"])
    if isinstance(item, dict):
        item = next(iter(item.values()), None)
    return item


def _extract_next_data(html: str) -> dict[str, Any] | None:
    """Parse __NEXT_DATA__ JSON blob.

    Args:
        html: Raw TikTok page HTML.

    Returns:
        Normalised data dict, or None if not present.
    """
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None

    raw = json.loads(match.group(1))
    item = _deep_find(raw, ["props", "pageProps", "itemInfo", "itemStruct"])
    return item


# ── Data normalisation ────────────────────────────────────────────────────────


def _build_video_info(item: dict[str, Any], original_url: str) -> VideoInfo:
    """Convert a raw TikTok item struct to a VideoInfo model.

    Args:
        item: Raw dict from any extraction strategy.
        original_url: Fallback URL for ID extraction.

    Returns:
        Populated VideoInfo.

    Raises:
        ExtractionFailedException: No playable download URL found.
    """
    video_id = str(item.get("id", "") or extract_video_id(original_url) or "")
    author_info = item.get("author", {}) or {}
    author = (
        author_info.get("uniqueId", "")
        or author_info.get("nickname", "")
        or item.get("authorId", "")
        or ""
    )

    video_block = item.get("video", {}) or {}
    music_block = item.get("music", {}) or {}
    stats_block = item.get("stats", {}) or {}

    # ── Download URL ─────────────────────────────────────────────────────────
    download_url = _pick_download_url(video_block)
    if not download_url:
        raise ExtractionFailedException(
            "No playable URL found in extracted data. "
            "TikTok CDN URLs may be region-locked or expired."
        )

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    cover = (
        video_block.get("cover", "")
        or video_block.get("dynamicCover", "")
        or video_block.get("originCover", "")
        or ""
    )

    # ── Music ─────────────────────────────────────────────────────────────────
    music_title = music_block.get("title", "") or ""
    music_url = music_block.get("playUrl", "") or ""

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_ts = item.get("createTime")
    created_at: datetime | None = None
    if created_ts:
        try:
            created_at = datetime.utcfromtimestamp(int(created_ts))
        except (ValueError, OSError):
            pass

    return VideoInfo(
        video_id=video_id,
        author=author,
        author_id=str(author_info.get("id", "") or ""),
        description=str(item.get("desc", "") or ""),
        duration=int(video_block.get("duration", 0) or 0),
        download_url=download_url,
        thumbnail_url=cover,
        music_title=music_title,
        music_url=music_url,
        play_count=int(stats_block.get("playCount", 0) or 0),
        like_count=int(stats_block.get("diggCount", 0) or 0),
        comment_count=int(stats_block.get("commentCount", 0) or 0),
        share_count=int(stats_block.get("shareCount", 0) or 0),
        created_at=created_at,
        original_url=original_url,
    )


def _pick_download_url(video_block: dict[str, Any]) -> str:
    """Choose the best (watermark-free, highest-quality) playback URL.

    Priority order (highest quality / no watermark first):
      1. bitrateInfo[0].PlayAddr.UrlList[0]
      2. playAddrBytevc1.urlList[0]
      3. playAddr.urlList[0]
      4. downloadAddr.urlList[0]
      5. playUrl (legacy)

    Args:
        video_block: The "video" sub-dict from TikTok item struct.

    Returns:
        Best available URL string, or empty string if none found.
    """
    # Bitrate list – usually HD H.265
    bitrate_info = video_block.get("bitrateInfo") or []
    for entry in bitrate_info:
        url_list = (entry.get("PlayAddr") or {}).get("UrlList") or []
        if url_list and url_list[0]:
            return url_list[0]

    # Direct fields
    for field in ("playAddrBytevc1", "playAddr", "downloadAddr"):
        block = video_block.get(field) or {}
        url_list = block.get("urlList") or block.get("UrlList") or []
        if url_list and url_list[0]:
            return url_list[0]

    # Legacy flat field
    return str(video_block.get("playUrl", "") or "")


def _deep_find(data: Any, keys: list[str]) -> Any:
    """Traverse a nested dict by a list of keys.

    Args:
        data: Nested dict / list to traverse.
        keys: Ordered list of dict keys to follow.

    Returns:
        The value at the end of the key path, or None if any key is missing.
    """
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data
