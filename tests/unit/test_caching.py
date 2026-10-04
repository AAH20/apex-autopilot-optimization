"""Tests for the caching package: LRUCache, TTLCache, memoize, cache_key."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.caching import (
    CacheConfig,
    CacheStats,
    LRUCache,
    TTLCache,
    cache_key,
    memoize,
)


# ---------------------------------------------------------------------------
# CacheConfig
# ---------------------------------------------------------------------------


class TestCacheConfig:
    def test_defaults(self):
        cfg = CacheConfig()
        assert cfg.max_size == 128
        assert cfg.ttl_seconds is None

    def test_custom_values(self):
        cfg = CacheConfig(max_size=10, ttl_seconds=5.0)
        assert cfg.max_size == 10
        assert cfg.ttl_seconds == 5.0

    def test_zero_max_size(self):
        cfg = CacheConfig(max_size=0)
        assert cfg.max_size == 0


# ---------------------------------------------------------------------------
# CacheStats
# ---------------------------------------------------------------------------


class TestCacheStats:
    def test_defaults(self):
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.size == 0

    def test_custom_values(self):
        stats = CacheStats(hits=3, misses=2, evictions=1, size=4)
        assert stats.hits == 3
        assert stats.misses == 2
        assert stats.evictions == 1
        assert stats.size == 4


# ---------------------------------------------------------------------------
# cache_key
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_single_arg(self):
        key = cache_key(42)
        assert key == 42

    def test_multiple_args(self):
        key = cache_key(1, "hello", 3.14)
        assert isinstance(key, tuple)
        assert key == (1, "hello", 3.14)

    def test_deterministic(self):
        assert cache_key(1, 2, 3) == cache_key(1, 2, 3)

    def test_different_args_different_keys(self):
        assert cache_key(1, 2) != cache_key(2, 1)

    def test_no_args(self):
        key = cache_key()
        assert key == ()

    def test_with_none(self):
        key = cache_key(None, "x")
        assert key == (None, "x")

    def test_with_list_converted_to_tuple(self):
        key = cache_key([1, 2, 3])
        assert key == (1, 2, 3)

    def test_with_dict_converted(self):
        key = cache_key({"a": 1})
        assert isinstance(key, tuple)
        assert len(key) == 1


# ---------------------------------------------------------------------------
# LRUCache
# ---------------------------------------------------------------------------


class TestLRUCacheBasic:
    def test_put_and_get(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        assert cache.get("a") == 1

    def test_get_missing_returns_none(self):
        cache = LRUCache(max_size=3)
        assert cache.get("missing") is None

    def test_overwrite_existing_key(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.put("a", 2)
        assert cache.get("a") == 2

    def test_size_tracks_entries(self):
        cache = LRUCache(max_size=5)
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.get_stats().size == 2

    def test_size_after_overwrite_not_doubled(self):
        cache = LRUCache(max_size=5)
        cache.put("a", 1)
        cache.put("a", 2)
        assert cache.get_stats().size == 1


class TestLRUEviction:
    def test_evicts_least_recently_used(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_get_refreshes_recency(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # refresh "a"
        cache.put("c", 3)  # should evict "b" not "a"
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_put_refreshes_recency(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)  # refresh "a"
        cache.put("c", 3)  # should evict "b"
        assert cache.get("a") == 10
        assert cache.get("b") is None

    def test_eviction_count_tracked(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        assert cache.get_stats().evictions == 1

    def test_multiple_evictions(self):
        cache = LRUCache(max_size=1)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        assert cache.get_stats().evictions == 2

    def test_no_eviction_when_within_capacity(self):
        cache = LRUCache(max_size=5)
        for i in range(5):
            cache.put(f"k{i}", i)
        assert cache.get_stats().evictions == 0


class TestLRUStats:
    def test_hit_counted(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.get("a")
        cache.get("a")
        assert cache.get_stats().hits == 2

    def test_miss_counted(self):
        cache = LRUCache(max_size=3)
        cache.get("x")
        cache.get("y")
        assert cache.get_stats().misses == 2

    def test_hit_and_miss_combined(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        cache.get("a")  # hit
        stats = cache.get_stats()
        assert stats.hits == 2
        assert stats.misses == 1

    def test_evicted_key_counts_as_miss(self):
        cache = LRUCache(max_size=1)
        cache.put("a", 1)
        cache.put("b", 2)  # evicts "a"
        cache.get("a")  # miss
        assert cache.get_stats().misses == 1


class TestLRUInvalidate:
    def test_invalidate_removes_key(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.invalidate("a")
        assert cache.get("a") is None

    def test_invalidate_reduces_size(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.invalidate("a")
        assert cache.get_stats().size == 1

    def test_invalidate_missing_key_no_error(self):
        cache = LRUCache(max_size=3)
        cache.invalidate("nonexistent")  # should not raise
        assert cache.get_stats().size == 0

    def test_invalidate_does_not_affect_others(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.invalidate("a")
        assert cache.get("b") == 2


class TestLRUClear:
    def test_clear_removes_all(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_clear_resets_size(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.clear()
        assert cache.get_stats().size == 0

    def test_clear_resets_stats(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.get("a")
        cache.get("b")
        cache.clear()
        stats = cache.get_stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0

    def test_clear_allows_reuse(self):
        cache = LRUCache(max_size=3)
        cache.put("a", 1)
        cache.clear()
        cache.put("b", 2)
        assert cache.get("b") == 2
        assert cache.get_stats().size == 1


# ---------------------------------------------------------------------------
# TTLCache
# ---------------------------------------------------------------------------


class TestTTLCacheBasic:
    def test_put_and_get(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        assert cache.get("a") == 1

    def test_get_missing_returns_none(self):
        cache = TTLCache(max_size=3)
        assert cache.get("missing") is None

    def test_overwrite_existing_key(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        cache.put("a", 2, ttl_seconds=10)
        assert cache.get("a") == 2

    def test_size_tracks_entries(self):
        cache = TTLCache(max_size=5)
        cache.put("a", 1, ttl_seconds=10)
        cache.put("b", 2, ttl_seconds=10)
        assert cache.get_stats().size == 2


class TestTTLExpiration:
    def test_entry_expires_after_ttl(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=0.05)
        time.sleep(0.1)
        assert cache.get("a") is None

    def test_entry_valid_before_ttl(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        assert cache.get("a") == 1

    def test_expired_key_counts_as_miss(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=0.05)
        time.sleep(0.1)
        cache.get("a")
        assert cache.get_stats().misses == 1

    def test_expired_key_not_counted_as_hit(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=0.05)
        time.sleep(0.1)
        cache.get("a")
        assert cache.get_stats().hits == 0

    def test_expired_entry_removed_from_size(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=0.05)
        time.sleep(0.1)
        cache.get("a")  # triggers cleanup
        assert cache.get_stats().size == 0

    def test_different_ttls(self):
        cache = TTLCache(max_size=5)
        cache.put("short", 1, ttl_seconds=0.05)
        cache.put("long", 2, ttl_seconds=10)
        time.sleep(0.1)
        assert cache.get("short") is None
        assert cache.get("long") == 2

    def test_overwrite_resets_ttl(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=0.05)
        time.sleep(0.03)
        cache.put("a", 2, ttl_seconds=10)  # reset TTL
        time.sleep(0.03)
        assert cache.get("a") == 2


class TestTTLStats:
    def test_hit_counted(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        cache.get("a")
        cache.get("a")
        assert cache.get_stats().hits == 2

    def test_miss_counted(self):
        cache = TTLCache(max_size=3)
        cache.get("x")
        cache.get("y")
        assert cache.get_stats().misses == 2

    def test_hit_and_miss_combined(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        cache.get("a")  # hit
        cache.get("b")  # miss
        cache.get("a")  # hit
        stats = cache.get_stats()
        assert stats.hits == 2
        assert stats.misses == 1


class TestTTLInvalidate:
    def test_invalidate_removes_key(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        cache.invalidate("a")
        assert cache.get("a") is None

    def test_invalidate_reduces_size(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        cache.put("b", 2, ttl_seconds=10)
        cache.invalidate("a")
        assert cache.get_stats().size == 1

    def test_invalidate_missing_key_no_error(self):
        cache = TTLCache(max_size=3)
        cache.invalidate("nonexistent")
        assert cache.get_stats().size == 0


class TestTTLClear:
    def test_clear_removes_all(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        cache.put("b", 2, ttl_seconds=10)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_clear_resets_stats(self):
        cache = TTLCache(max_size=3)
        cache.put("a", 1, ttl_seconds=10)
        cache.get("a")
        cache.get("b")
        cache.clear()
        stats = cache.get_stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.size == 0


class TestTTLEviction:
    def test_evicts_least_recently_used_when_full(self):
        cache = TTLCache(max_size=2)
        cache.put("a", 1, ttl_seconds=10)
        cache.put("b", 2, ttl_seconds=10)
        cache.put("c", 3, ttl_seconds=10)  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_eviction_count_tracked(self):
        cache = TTLCache(max_size=2)
        cache.put("a", 1, ttl_seconds=10)
        cache.put("b", 2, ttl_seconds=10)
        cache.put("c", 3, ttl_seconds=10)
        assert cache.get_stats().evictions == 1


# ---------------------------------------------------------------------------
# memoize
# ---------------------------------------------------------------------------


class TestMemoize:
    def test_caches_results(self):
        call_count = 0

        @memoize()
        def expensive(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        assert expensive(5) == 10
        assert expensive(5) == 10
        assert call_count == 1

    def test_different_args_different_results(self):
        call_count = 0

        @memoize()
        def expensive(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        assert expensive(3) == 6
        assert expensive(4) == 8
        assert call_count == 2

    def test_memoize_with_max_size(self):
        call_count = 0

        @memoize(max_size=2)
        def expensive(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        expensive(1)  # call 1
        expensive(2)  # call 2
        expensive(3)  # call 3, evicts 1
        expensive(1)  # call 4 (was evicted)
        assert call_count == 4

    def test_memoize_with_ttl(self):
        call_count = 0

        @memoize(ttl_seconds=0.05)
        def expensive(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        expensive(5)  # call 1
        expensive(5)  # cached
        assert call_count == 1
        time.sleep(0.1)
        expensive(5)  # expired, call 2
        assert call_count == 2

    def test_memoize_preserves_function_metadata(self):
        @memoize()
        def my_func(x):
            """My docstring."""
            return x

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."

    def test_memoize_with_multiple_args(self):
        call_count = 0

        @memoize()
        def add(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert add(1, 2) == 3
        assert add(2, 1) == 3
        assert call_count == 2

    def test_memoize_with_kwargs(self):
        call_count = 0

        @memoize()
        def greet(name, greeting="hello"):
            nonlocal call_count
            call_count += 1
            return f"{greeting} {name}"

        assert greet("world") == "hello world"
        assert greet("world", greeting="hello") == "hello world"
        assert call_count == 1

    def test_memoize_returns_correct_types(self):
        @memoize()
        def compute(x):
            return [x, x * 2]

        result = compute(5)
        assert result == [5, 10]
        assert isinstance(result, list)

    def test_memoize_with_none_return(self):
        call_count = 0

        @memoize()
        def returns_none(x):
            nonlocal call_count
            call_count += 1
            return None

        assert returns_none(1) is None
        assert returns_none(1) is None
        assert call_count == 1

    def test_memoize_no_cache_on_exception(self):
        call_count = 0

        @memoize()
        def fails(x):
            nonlocal call_count
            call_count += 1
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fails(1)
        with pytest.raises(ValueError, match="boom"):
            fails(1)
        assert call_count == 2  # not cached

    def test_memoize_with_max_size_one(self):
        call_count = 0

        @memoize(max_size=1)
        def expensive(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        expensive(1)  # call 1
        expensive(2)  # call 2, evicts 1
        expensive(1)  # call 3 (was evicted)
        assert call_count == 3

    def test_memoize_with_zero_max_size_disables_cache(self):
        call_count = 0

        @memoize(max_size=0)
        def expensive(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        expensive(1)
        expensive(1)
        assert call_count == 2  # no caching with max_size=0
