"""Caching utilities for apex-autopilot-optimization.

Provides LRU and TTL caches plus a memoize decorator so that expensive
planner, optimizer, and estimator calls can be reused across invocations.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_autopilot_optimization.caching.decorators import cache_key, memoize
from apex_autopilot_optimization.caching.lru import CacheStats, LRUCache
from apex_autopilot_optimization.caching.ttl import TTLCache

__all__ = [
    "CacheConfig",
    "CacheStats",
    "LRUCache",
    "TTLCache",
    "cache_key",
    "memoize",
]


@dataclass
class CacheConfig:
    """Configuration for cache behavior."""

    max_size: int = 128
    ttl_seconds: float | None = None
