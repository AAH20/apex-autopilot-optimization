"""Time-To-Live (TTL) cache with per-entry expiration."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from apex_autopilot_optimization.caching.lru import CacheStats


class TTLCache:
    """Fixed-capacity cache where entries expire after a per-entry TTL.

    Combines LRU eviction with time-based expiration.  Expired entries are
    treated as misses and removed from the cache on access.
    """

    def __init__(self, max_size: int = 128):
        if max_size < 0:
            raise ValueError("max_size must be non-negative")
        self._max_size = max_size
        self._cache: OrderedDict[Any, tuple[float, float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def __contains__(self, key: Any) -> bool:
        if key not in self._cache:
            return False
        ts, ttl, _ = self._cache[key]
        if time.monotonic() - ts >= ttl:
            del self._cache[key]
            return False
        return True

    def get(self, key: Any) -> Any | None:
        """Return the cached value, or None if missing or expired."""
        if key not in self._cache:
            self._misses += 1
            return None
        ts, ttl, value = self._cache[key]
        if time.monotonic() - ts >= ttl:
            del self._cache[key]
            self._misses += 1
            return None
        self._hits += 1
        self._cache.move_to_end(key)
        return value

    def put(self, key: Any, value: Any, ttl_seconds: float) -> None:
        """Insert or update a key with the given TTL in seconds."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.monotonic(), ttl_seconds, value)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
            self._evictions += 1

    def invalidate(self, key: Any) -> None:
        """Remove *key* from the cache if present."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Drop all entries and reset every counter."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get_stats(self) -> CacheStats:
        """Return a snapshot of the cache counters."""
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
            size=len(self._cache),
        )
