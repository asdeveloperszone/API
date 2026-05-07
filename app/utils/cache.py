"""
Simple async-safe in-memory TTL cache.

Uses a dict of (value, expiry_timestamp) pairs.
No external dependencies — Redis can be swapped in later.

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TypeVar

T = TypeVar("T")

_SENTINEL = object()


class TTLCache:
    """Thread/coroutine-safe in-memory cache with per-entry TTL.

    Example::

        cache = TTLCache(default_ttl=300)
        await cache.set("my_key", {"data": 123})
        val = await cache.get("my_key")   # {"data": 123}
    """

    def __init__(self, default_ttl: int = 300) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a cached value.

        Args:
            key: Cache key.
            default: Value to return when key is missing or expired.

        Returns:
            Cached value, or *default*.
        """
        async with self._lock:
            entry = self._store.get(key, _SENTINEL)
            if entry is _SENTINEL:
                return default
            value, expiry = entry  # type: ignore[misc]
            if time.monotonic() > expiry:
                del self._store[key]
                return default
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key.
            value: Value to store (must be picklable if you later swap Redis).
            ttl: Time-to-live in seconds; uses *default_ttl* when omitted.
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expiry = time.monotonic() + effective_ttl
        async with self._lock:
            self._store[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        """Remove a single entry from the cache.

        Args:
            key: Cache key to delete.
        """
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Remove all entries from the cache."""
        async with self._lock:
            self._store.clear()

    async def size(self) -> int:
        """Return the number of *live* (non-expired) entries.

        Returns:
            Count of unexpired cache entries.
        """
        now = time.monotonic()
        async with self._lock:
            return sum(1 for _, (_, exp) in self._store.items() if now <= exp)

    async def purge_expired(self) -> int:
        """Remove all expired entries and return the count removed.

        Returns:
            Number of stale entries that were purged.
        """
        now = time.monotonic()
        async with self._lock:
            stale = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in stale:
                del self._store[k]
            return len(stale)


# Module-level singleton used by services
video_cache: TTLCache = TTLCache(default_ttl=300)
