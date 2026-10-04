"""Least Recently Used (LRU) cache with O(1) operations."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheStats:
    """Cache hit/miss/eviction counters and current entry count."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0


class LRUCache:
    """Fixed-capacity LRU cache.

    The least-recently-used entry is evicted when the cache is full and a
    new key is inserted.  Both ``get`` and ``put`` refresh recency.
    """

    def __init__(self, max_size: int = 128):
        if max_size < 0:
            raise ValueError("max_size must be non-negative")
        self._max_size = max_size
        self._cache: OrderedDict[Any, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def __contains__(self, key: Any) -> bool:
        return key in self._cache

    def get(self, key: Any) -> Any | None:
        """Return the cached value, or None on a miss."""
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._misses += 1
        return None

    def get_or_default(self, key: Any, default: Any = None) -> Any:
        """Return the cached value, or *default* on a miss."""
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._misses += 1
        return default

    def put(self, key: Any, value: Any) -> None:
        """Insert or update a key, evicting the LRU entry if over capacity."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
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
