"""Memoization decorators and cache-key helpers."""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

from apex_autopilot_optimization.caching.lru import LRUCache
from apex_autopilot_optimization.caching.ttl import TTLCache


def _make_hashable(obj: Any) -> Any:
    if isinstance(obj, list):
        return tuple(_make_hashable(v) for v in obj)
    if isinstance(obj, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in obj.items()))
    return obj


def cache_key(*args: Any) -> Any:
    """Build a hashable cache key from positional arguments.

    A single argument is returned as-is (so ``cache_key(42)`` returns ``42``).
    Multiple arguments are returned as a tuple.  Lists are converted to tuples
    and dicts to tuples of items so the result is always hashable.
    """
    if len(args) == 1:
        return _make_hashable(args[0])
    return tuple(_make_hashable(a) for a in args)


def memoize(
    func: Callable[..., Any] | None = None,
    *,
    max_size: int = 128,
    ttl_seconds: float | None = None,
) -> Any:
    """Memoize a function using an LRU or TTL cache.

    Can be used bare (``@memoize()``) or with keyword arguments
    (``@memoize(max_size=2, ttl_seconds=0.05)``).  ``max_size=0`` disables
    caching entirely.  Exceptions are never cached.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if max_size == 0:
            return fn

        if ttl_seconds is not None:
            cache: Any = TTLCache(max_size=max_size)
        else:
            cache = LRUCache(max_size=max_size)

        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            key = cache_key(*bound.args, *sorted(bound.kwargs.items()))
            if key in cache:
                return cache.get(key)
            value = fn(*args, **kwargs)
            if ttl_seconds is not None:
                cache.put(key, value, ttl_seconds=ttl_seconds)
            else:
                cache.put(key, value)
            return value

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
