"""Tests for the traffic package: RateLimiter, LoadBalancer, ServiceRegistry."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.traffic import (
    CircuitBreakerConfig,
    LeastConnectionsStrategy,
    LoadBalancer,
    RandomStrategy,
    RateLimiter,
    RateLimitConfig,
    RoundRobinStrategy,
    ServiceRegistry,
    TokenBucket,
)


# ---------------------------------------------------------------------------
# RateLimitConfig
# ---------------------------------------------------------------------------


class TestRateLimitConfig:
    def test_defaults(self) -> None:
        cfg = RateLimitConfig()
        assert cfg.requests_per_second == 10
        assert cfg.burst_size == 20
        assert cfg.window_seconds == 1.0

    def test_custom_values(self) -> None:
        cfg = RateLimitConfig(requests_per_second=100, burst_size=50, window_seconds=2.5)
        assert cfg.requests_per_second == 100
        assert cfg.burst_size == 50
        assert cfg.window_seconds == 2.5


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_consume_within_capacity(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(5) is True
        assert bucket.get_tokens() == pytest.approx(5.0)

    def test_consume_exceeds_capacity(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(15) is False
        assert bucket.get_tokens() == pytest.approx(10.0)

    def test_consume_exact_capacity(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(10) is True
        assert bucket.get_tokens() == pytest.approx(0.0)

    def test_refill(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        bucket.consume(8)
        assert bucket.get_tokens() == pytest.approx(2.0)
        bucket.refill()
        assert bucket.get_tokens() == pytest.approx(4.0)

    def test_refill_capped_at_capacity(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=100.0)
        bucket.consume(2)
        bucket.refill()
        assert bucket.get_tokens() == pytest.approx(10.0)

    def test_consume_zero_tokens(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(0) is True

    def test_consume_negative_tokens_rejected(self) -> None:
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(-1) is False


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_allow_within_limit(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=10, burst_size=5))
        assert limiter.is_allowed("client1") is True

    def test_deny_over_burst(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=1, burst_size=3))
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client1") is False

    def test_isolated_keys(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=1, burst_size=1))
        assert limiter.is_allowed("client1") is True
        assert limiter.is_allowed("client2") is True
        assert limiter.is_allowed("client1") is False

    def test_get_remaining(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=10, burst_size=5))
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")
        remaining = limiter.get_remaining("client1")
        assert remaining == 3

    def test_get_remaining_unknown_key(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=10, burst_size=5))
        assert limiter.get_remaining("unknown") == 5

    def test_reset(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=1, burst_size=2))
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")
        assert limiter.get_remaining("client1") == 0
        limiter.reset("client1")
        assert limiter.get_remaining("client1") == 2

    def test_get_stats(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=10, burst_size=5))
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")
        stats = limiter.get_stats("client1")
        assert stats["allowed"] == 2
        assert stats["denied"] == 0
        assert stats["remaining"] == 3

    def test_get_stats_with_denials(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=1, burst_size=1))
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")
        stats = limiter.get_stats("client1")
        assert stats["allowed"] == 1
        assert stats["denied"] == 1

    def test_get_stats_unknown_key(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=10, burst_size=5))
        stats = limiter.get_stats("unknown")
        assert stats["allowed"] == 0
        assert stats["denied"] == 0
        assert stats["remaining"] == 5

    def test_token_refill_over_time(self) -> None:
        limiter = RateLimiter(RateLimitConfig(requests_per_second=100, burst_size=2))
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")
        assert limiter.is_allowed("client1") is False
        time.sleep(0.05)
        assert limiter.is_allowed("client1") is True


# ---------------------------------------------------------------------------
# LoadBalancer
# ---------------------------------------------------------------------------


class TestLoadBalancerAddRemove:
    def test_add_backend(self) -> None:
        lb = LoadBalancer()
        lb.add_backend("http://a:8080")
        assert "http://a:8080" in lb.get_all_backends()

    def test_add_multiple_backends(self) -> None:
        lb = LoadBalancer()
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        assert len(lb.get_all_backends()) == 2

    def test_add_duplicate_backend_ignored(self) -> None:
        lb = LoadBalancer()
        lb.add_backend("http://a:8080")
        lb.add_backend("http://a:8080")
        assert len(lb.get_all_backends()) == 1

    def test_remove_backend(self) -> None:
        lb = LoadBalancer()
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        lb.remove_backend("http://a:8080")
        assert lb.get_all_backends() == ["http://b:8080"]

    def test_remove_nonexistent_backend(self) -> None:
        lb = LoadBalancer()
        lb.add_backend("http://a:8080")
        lb.remove_backend("http://ghost:9999")
        assert lb.get_all_backends() == ["http://a:8080"]

    def test_get_backend_empty_raises(self) -> None:
        lb = LoadBalancer()
        with pytest.raises(RuntimeError, match="No backends"):
            lb.get_backend()

    def test_get_healthy_backends(self) -> None:
        lb = LoadBalancer()
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        lb.set_backend_health("http://a:8080", False)
        healthy = lb.get_healthy_backends()
        assert healthy == ["http://b:8080"]


class TestRoundRobinStrategy:
    def test_cycles_through_backends(self) -> None:
        lb = LoadBalancer(strategy=RoundRobinStrategy())
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        lb.add_backend("http://c:8080")
        results = [lb.get_backend() for _ in range(6)]
        assert results == [
            "http://a:8080",
            "http://b:8080",
            "http://c:8080",
            "http://a:8080",
            "http://b:8080",
            "http://c:8080",
        ]

    def test_skips_unhealthy(self) -> None:
        lb = LoadBalancer(strategy=RoundRobinStrategy())
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        lb.set_backend_health("http://a:8080", False)
        for _ in range(4):
            assert lb.get_backend() == "http://b:8080"


class TestLeastConnectionsStrategy:
    def test_selects_least_loaded(self) -> None:
        lb = LoadBalancer(strategy=LeastConnectionsStrategy())
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        lb.increment_connections("http://a:8080")
        lb.increment_connections("http://a:8080")
        lb.increment_connections("http://b:8080")
        assert lb.get_backend() == "http://b:8080"

    def test_releases_connection(self) -> None:
        lb = LoadBalancer(strategy=LeastConnectionsStrategy())
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        lb.increment_connections("http://a:8080")
        lb.release_connection("http://a:8080")
        assert lb.get_backend() == "http://a:8080"


class TestRandomStrategy:
    def test_returns_registered_backend(self) -> None:
        lb = LoadBalancer(strategy=RandomStrategy())
        lb.add_backend("http://a:8080")
        lb.add_backend("http://b:8080")
        for _ in range(20):
            assert lb.get_backend() in {"http://a:8080", "http://b:8080"}

    def test_random_single_backend(self) -> None:
        lb = LoadBalancer(strategy=RandomStrategy())
        lb.add_backend("http://only:8080")
        for _ in range(5):
            assert lb.get_backend() == "http://only:8080"


# ---------------------------------------------------------------------------
# ServiceRegistry
# ---------------------------------------------------------------------------


class TestServiceRegistry:
    def test_register_and_discover(self) -> None:
        registry = ServiceRegistry()
        registry.register("auth", "http://auth1:9000")
        assert registry.discover("auth") == "http://auth1:9000"

    def test_register_multiple_instances(self) -> None:
        registry = ServiceRegistry()
        registry.register("auth", "http://auth1:9000")
        registry.register("auth", "http://auth2:9000")
        instance = registry.discover("auth")
        assert instance in {"http://auth1:9000", "http://auth2:9000"}

    def test_deregister(self) -> None:
        registry = ServiceRegistry()
        registry.register("auth", "http://auth1:9000")
        registry.deregister("auth", "http://auth1:9000")
        assert registry.discover("auth") is None

    def test_deregister_one_of_many(self) -> None:
        registry = ServiceRegistry()
        registry.register("auth", "http://auth1:9000")
        registry.register("auth", "http://auth2:9000")
        registry.deregister("auth", "http://auth1:9000")
        assert registry.discover("auth") == "http://auth2:9000"

    def test_discover_unknown_service(self) -> None:
        registry = ServiceRegistry()
        assert registry.discover("nope") is None

    def test_list_services(self) -> None:
        registry = ServiceRegistry()
        registry.register("auth", "http://auth1:9000")
        registry.register("billing", "http://billing1:9000")
        services = registry.list_services()
        assert set(services) == {"auth", "billing"}

    def test_list_services_empty(self) -> None:
        registry = ServiceRegistry()
        assert registry.list_services() == []

    def test_health_check_healthy(self) -> None:
        registry = ServiceRegistry()
        registry.register("auth", "http://auth1:9000")
        assert registry.health_check("auth") is True

    def test_health_check_unhealthy(self) -> None:
        registry = ServiceRegistry()
        registry.register("auth", "http://auth1:9000")
        registry.set_health("auth", "http://auth1:9000", False)
        assert registry.health_check("auth") is False

    def test_health_check_unknown_service(self) -> None:
        registry = ServiceRegistry()
        assert registry.health_check("ghost") is False


# ---------------------------------------------------------------------------
# CircuitBreakerConfig
# ---------------------------------------------------------------------------


class TestCircuitBreakerConfig:
    def test_defaults(self) -> None:
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.recovery_timeout == 30.0
        assert cfg.half_open_max_calls == 3

    def test_custom_values(self) -> None:
        cfg = CircuitBreakerConfig(
            failure_threshold=10, recovery_timeout=60.0, half_open_max_calls=5
        )
        assert cfg.failure_threshold == 10
        assert cfg.recovery_timeout == 60.0
        assert cfg.half_open_max_calls == 5
