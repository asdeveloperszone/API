"""
Video streaming proxy service.

Pipes TikTok CDN bytes directly to the client with no server-side storage.
Supports HTTP Range requests for partial downloads / seek support.

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

import re
from typing import AsyncIterator

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.utils.exceptions import StreamingException
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Bytes range header regex
_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


async def stream_video(download_url: str, request: Request) -> StreamingResponse:
    """Stream a TikTok video from CDN to the HTTP client.

    Forwards Range headers so partial downloads and in-app seek work correctly.
    No bytes are written to disk.

    Args:
        download_url: Direct TikTok CDN URL obtained from the resolver.
        request: Incoming FastAPI request (used to read Range header).

    Returns:
        StreamingResponse that pipes CDN bytes to the client.

    Raises:
        StreamingException: CDN is unreachable or returns an error status.
    """
    range_header = request.headers.get("range", "")
    req_headers = _build_request_headers(range_header)

    # We open the client outside the generator so errors surface before
    # we commit to a streaming response.
    try:
        client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0),
            headers=settings.tiktok_headers,
        )
        cdn_resp = await client.send(
            client.build_request("GET", download_url, headers=req_headers),
            stream=True,
        )
    except httpx.RequestError as exc:
        raise StreamingException(f"CDN request failed: {exc}") from exc

    if cdn_resp.status_code not in (200, 206):
        await cdn_resp.aclose()
        await client.aclose()
        raise StreamingException(
            f"CDN returned unexpected status {cdn_resp.status_code}"
        )

    # Build response headers for the client
    resp_headers = _build_response_headers(cdn_resp, range_header)
    http_status = 206 if range_header and cdn_resp.status_code == 206 else 200

    return StreamingResponse(
        content=_iter_chunks(cdn_resp, client),
        status_code=http_status,
        headers=resp_headers,
        media_type="video/mp4",
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_request_headers(range_header: str) -> dict[str, str]:
    """Build headers to forward to the TikTok CDN.

    Args:
        range_header: Client's Range header value (may be empty).

    Returns:
        Headers dict for the upstream request.
    """
    headers: dict[str, str] = {
        "Referer": "https://www.tiktok.com/",
        "Origin": "https://www.tiktok.com",
    }
    if range_header:
        headers["Range"] = range_header
    return headers


def _build_response_headers(
    cdn_resp: httpx.Response, range_header: str
) -> dict[str, str]:
    """Extract useful headers from the CDN response to forward to the client.

    Args:
        cdn_resp: Upstream HTTP response (streaming, not yet consumed).
        range_header: Original client Range header.

    Returns:
        Dict of headers to include in the StreamingResponse.
    """
    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "Content-Disposition": 'attachment; filename="tiktok_video.mp4"',
    }

    for h in ("Content-Length", "Content-Range", "Content-Type", "ETag"):
        val = cdn_resp.headers.get(h)
        if val:
            headers[h] = val

    # Ensure Content-Type is always set
    headers.setdefault("Content-Type", "video/mp4")

    return headers


async def _iter_chunks(
    response: httpx.Response, client: httpx.AsyncClient
) -> AsyncIterator[bytes]:
    """Async generator that yields chunks and cleans up when done.

    Args:
        response: Open streaming httpx response.
        client: httpx.AsyncClient to close after streaming completes.

    Yields:
        Raw bytes chunks from the CDN response.
    """
    try:
        async for chunk in response.aiter_bytes(chunk_size=settings.STREAM_CHUNK_SIZE_BYTES):
            if chunk:
                yield chunk
    except httpx.ReadError as exc:
        logger.warning("Stream read error (client may have disconnected): %s", exc)
    except Exception as exc:
        logger.error("Unexpected streaming error: %s", exc)
        raise
    finally:
        await response.aclose()
        await client.aclose()
        logger.debug("Streaming connection closed")
