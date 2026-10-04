"""Rate limiting: token bucket algorithm and rate limiter."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        requests_per_second: Sustained request rate allowed.
        burst_size: Maximum burst capacity (bucket size).
        window_seconds: Time window for rate calculation.
    """

    requests_per_second: int = 10
    burst_size: int = 20
    window_seconds: float = 1.0


class TokenBucket:
    """Token bucket for rate limiting.

    Tokens are consumed on each request and refilled at a constant rate.
    Thread-safe.
    """

    def __init__(self, capacity: float, refill_rate: float) -> None:
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def consume(self, tokens: float) -> bool:
        """Attempt to consume tokens. Returns True if successful."""
        if tokens < 0:
            return False
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def get_tokens(self) -> float:
        """Return current available tokens."""
        with self._lock:
            self._refill()
            return self._tokens

    def refill(self) -> None:
        """Manually add refill_rate tokens (capped at capacity)."""
        with self._lock:
            self._tokens = min(self._capacity, self._tokens + self._refill_rate)


class RateLimiter:
    """Key-based rate limiter using token buckets.

    Each key gets its own token bucket. Thread-safe.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig()
        self._buckets: dict[str, TokenBucket] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                capacity=float(self._config.burst_size),
                refill_rate=self._config.requests_per_second
                / self._config.window_seconds,
            )
            self._stats[key] = {"allowed": 0, "denied": 0}
        return self._buckets[key]

    def is_allowed(self, key: str) -> bool:
        """Check if a request for the given key is allowed."""
        with self._lock:
            bucket = self._get_bucket(key)
            if bucket.consume(1):
                self._stats[key]["allowed"] += 1
                return True
            self._stats[key]["denied"] += 1
            return False

    def get_remaining(self, key: str) -> int:
        """Return remaining tokens for the given key."""
        with self._lock:
            if key not in self._buckets:
                return self._config.burst_size
            return int(self._buckets[key].get_tokens())

    def reset(self, key: str) -> None:
        """Reset rate limit state for the given key."""
        with self._lock:
            self._buckets.pop(key, None)
            self._stats.pop(key, None)

    def get_stats(self, key: str) -> dict[str, int]:
        """Return stats for the given key."""
        with self._lock:
            if key not in self._stats:
                return {
                    "allowed": 0,
                    "denied": 0,
                    "remaining": self._config.burst_size,
                }
            stats = dict(self._stats[key])
            stats["remaining"] = self.get_remaining(key)
            return stats
