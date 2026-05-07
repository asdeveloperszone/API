"""
Input validation and sanitization utilities.

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

# Allowed TikTok hostnames
_TIKTOK_DOMAINS: frozenset[str] = frozenset(
    {
        "tiktok.com",
        "www.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
        "m.tiktok.com",
    }
)

# Regex: full TikTok video URL with numeric video ID
_FULL_VIDEO_RE = re.compile(
    r"https?://(www\.)?tiktok\.com/@[\w.\-]+/video/(\d+)",
    re.IGNORECASE,
)

# Regex: short-link formats
_SHORT_LINK_RE = re.compile(
    r"https?://(vm|vt)\.tiktok\.com/[\w\-]+",
    re.IGNORECASE,
)

# Regex: extract video ID from path segments
_VIDEO_ID_RE = re.compile(r"/video/(\d{10,30})")


def is_valid_domain(url: str) -> bool:
    """Return True if *url* belongs to a known TikTok domain.

    Args:
        url: Raw URL string to inspect.

    Returns:
        True when the hostname is in the allow-list, False otherwise.
    """
    try:
        parsed = urlparse(url)
        return parsed.hostname in _TIKTOK_DOMAINS
    except Exception:
        return False


def validate_tiktok_url(url: str) -> bool:
    """Return True if *url* is a valid, safe TikTok URL.

    Checks domain allow-list AND URL structure to prevent SSRF.

    Args:
        url: Candidate TikTok URL.

    Returns:
        True for valid TikTok URLs, False for everything else.
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False

    if not is_valid_domain(url):
        return False

    return bool(_FULL_VIDEO_RE.match(url) or _SHORT_LINK_RE.match(url))


def extract_video_id(url: str) -> str | None:
    """Extract the numeric TikTok video ID from a URL.

    Args:
        url: Full TikTok URL (short-links return None – need resolution first).

    Returns:
        Video ID string or None if not found.
    """
    match = _VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def sanitize_input(url: str) -> str:
    """Strip whitespace and remove any fragment/credential components.

    Args:
        url: Raw URL from user input.

    Returns:
        Cleaned URL string safe for downstream processing.
    """
    url = url.strip()
    try:
        parsed = urlparse(url)
        # Drop username, password, and fragment; preserve everything else
        cleaned = urlunparse(
            (
                parsed.scheme,
                parsed.netloc.split("@")[-1],  # remove user:pass@
                parsed.path,
                parsed.params,
                parsed.query,
                "",  # drop fragment
            )
        )
        return cleaned
    except Exception:
        return url


def is_short_link(url: str) -> bool:
    """Return True if the URL is a TikTok short-link that needs resolving.

    Args:
        url: TikTok URL to test.

    Returns:
        True for vm.tiktok.com / vt.tiktok.com short-links.
    """
    try:
        parsed = urlparse(url)
        return parsed.hostname in {"vm.tiktok.com", "vt.tiktok.com"}
    except Exception:
        return False
