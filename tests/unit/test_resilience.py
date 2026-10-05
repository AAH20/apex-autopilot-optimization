"""Tests for resilience patterns: retry, circuit breaker, fallback, degradation."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    DegradationManager,
    FallbackChain,
    RetryConfig,
    retry,
    retry_with_config,
)

# ---------------------------------------------------------------------------
# Retry tests
# ---------------------------------------------------------------------------


class TestRetrySucceedsAfterTransientFailures:
    """Retry decorator succeeds when transient failures resolve."""

    def test_succeeds_after_one_failure(self) -> None:
        call_count = 0

        @retry(max_attempts=3, base_delay=0.001)
        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert call_count == 2

    def test_succeeds_after_multiple_failures(self) -> None:
        call_count = 0

        @retry(max_attempts=5, base_delay=0.001)
        def very_flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise TimeoutError("transient")
            return "ok"

        result = very_flaky()
        assert result == "ok"
        assert call_count == 4

    def test_succeeds_first_try(self) -> None:
        call_count = 0

        @retry(max_attempts=3, base_delay=0.001)
        def stable() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = stable()
        assert result == "ok"
        assert call_count == 1


class TestRetryGivesUpAfterMaxAttempts:
    """Retry decorator gives up after exhausting all attempts."""

    def test_raises_after_max_attempts(self) -> None:
        call_count = 0

        @retry(max_attempts=3, base_delay=0.001)
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("persistent")

        with pytest.raises(ConnectionError, match="persistent"):
            always_fails()
        assert call_count == 3

    def test_raises_non_retryable_immediately(self) -> None:
        call_count = 0

        @retry(max_attempts=5, base_delay=0.001, retryable_exceptions=(ConnectionError,))
        def raises_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            raises_value_error()
        assert call_count == 1

    def test_custom_retryable_exceptions(self) -> None:
        call_count = 0

        @retry(max_attempts=3, base_delay=0.001, retryable_exceptions=(TimeoutError,))
        def raises_timeout() -> str:
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError, match="timeout"):
            raises_timeout()
        assert call_count == 3


class TestRetryExponentialBackoff:
    """Retry decorator uses exponential backoff with jitter."""

    def test_delay_increases_exponentially(self) -> None:
        delays: list[float] = []
        call_count = 0

        @retry(max_attempts=4, base_delay=0.01, max_delay=1.0, exponential_base=2.0)
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            delays.append(time.perf_counter())
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            always_fails()

        assert call_count == 4
        # Check that delays between calls increase (with jitter tolerance)
        gap1 = delays[1] - delays[0]
        gap2 = delays[2] - delays[1]
        gap3 = delays[3] - delays[2]
        # With exponential backoff base=2, each gap should be larger
        assert gap2 > gap1 * 0.5  # jitter allows some variance
        assert gap3 > gap2 * 0.5

    def test_max_delay_caps_backoff(self) -> None:
        delays: list[float] = []
        call_count = 0

        @retry(max_attempts=5, base_delay=0.01, max_delay=0.02, exponential_base=10.0)
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            delays.append(time.perf_counter())
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            always_fails()

        assert call_count == 5
        # All gaps should be <= max_delay + small tolerance
        for i in range(1, len(delays)):
            gap = delays[i] - delays[i - 1]
            assert gap <= 0.05  # max_delay=0.02 + tolerance


class TestRetryWithConfig:
    """retry_with_config function works with explicit config."""

    def test_retry_with_config_succeeds(self) -> None:
        call_count = 0

        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        config = RetryConfig(max_attempts=5, base_delay=0.001)
        result = retry_with_config(flaky, config)
        assert result == "ok"
        assert call_count == 3

    def test_retry_with_config_gives_up(self) -> None:
        call_count = 0

        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        config = RetryConfig(max_attempts=2, base_delay=0.001)
        with pytest.raises(ConnectionError):
            retry_with_config(always_fails, config)
        assert call_count == 2


# ---------------------------------------------------------------------------
# Circuit Breaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreakerOpensAfterThreshold:
    """Circuit breaker opens after failure threshold is reached."""

    def test_opens_after_failure_threshold(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=0.1)
        cb = CircuitBreaker(config)

        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        assert cb.get_state() == "OPEN"

    def test_stays_closed_below_threshold(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=0.1)
        cb = CircuitBreaker(config)

        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        assert cb.get_state() == "CLOSED"

    def test_success_resets_failure_count(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=0.1)
        cb = CircuitBreaker(config)

        # 2 failures
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        # 1 success resets
        cb.call(lambda: "ok")

        # 2 more failures - should not open yet
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        assert cb.get_state() == "CLOSED"


class TestCircuitBreakerRecoversAfterTimeout:
    """Circuit breaker transitions to HALF_OPEN after recovery timeout."""

    def test_transitions_to_half_open_after_timeout(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05)
        cb = CircuitBreaker(config)

        # Open the breaker
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        assert cb.get_state() == "OPEN"

        # Wait for recovery timeout
        time.sleep(0.08)

        # Next call should transition to HALF_OPEN
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.get_state() == "CLOSED"

    def test_half_open_failure_reopens(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05)
        cb = CircuitBreaker(config)

        # Open the breaker
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        assert cb.get_state() == "OPEN"

        # Wait for recovery timeout
        time.sleep(0.08)

        # Call fails in HALF_OPEN -> back to OPEN
        with pytest.raises(ConnectionError):
            cb.call(lambda: (_ for _ in ()).throw(ConnectionError("still failing")))

        assert cb.get_state() == "OPEN"


class TestCircuitBreakerHalfOpen:
    """Circuit breaker HALF_OPEN state behavior."""

    def test_half_open_allows_limited_calls(self) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout=0.05, half_open_max_calls=2
        )
        cb = CircuitBreaker(config)

        # Open the breaker
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        time.sleep(0.08)

        # First call in HALF_OPEN succeeds -> CLOSED
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.get_state() == "CLOSED"

    def test_half_open_blocks_after_max_calls(self) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout=0.05, half_open_max_calls=1
        )
        cb = CircuitBreaker(config)

        # Open the breaker
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        time.sleep(0.08)

        # First call in HALF_OPEN succeeds -> CLOSED
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.get_state() == "CLOSED"


class TestCircuitBreakerMetrics:
    """Circuit breaker metrics tracking."""

    def test_get_metrics_returns_counts(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=0.1)
        cb = CircuitBreaker(config)

        # 1 failure
        with pytest.raises(ConnectionError):
            cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        metrics = cb.get_metrics()
        assert metrics["failure_count"] == 1
        assert metrics["success_count"] == 0
        assert metrics["state"] == "CLOSED"

        # 1 success resets failure count
        cb.call(lambda: "ok")

        metrics = cb.get_metrics()
        assert metrics["failure_count"] == 0
        assert metrics["success_count"] == 1
        assert metrics["state"] == "CLOSED"

    def test_metrics_track_state_transitions(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05)
        cb = CircuitBreaker(config)

        # Open the breaker
        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))

        metrics = cb.get_metrics()
        assert metrics["state"] == "OPEN"
        assert metrics["failure_count"] == 2


# ---------------------------------------------------------------------------
# Fallback Chain tests
# ---------------------------------------------------------------------------


class TestFallbackChain:
    """FallbackChain tries alternatives in order until one succeeds."""

    def test_first_succeeds(self) -> None:
        chain = FallbackChain()
        chain.add(lambda: "primary")
        chain.add(lambda: "secondary")

        result = chain.execute()
        assert result == "primary"

    def test_fallback_on_failure(self) -> None:
        chain = FallbackChain()
        chain.add(lambda: (_ for _ in ()).throw(ConnectionError("fail")))
        chain.add(lambda: "secondary")

        result = chain.execute()
        assert result == "secondary"

    def test_all_fail_raises(self) -> None:
        chain = FallbackChain()
        chain.add(lambda: (_ for _ in ()).throw(ConnectionError("fail1")))
        chain.add(lambda: (_ for _ in ()).throw(TimeoutError("fail2")))

        with pytest.raises(TimeoutError, match="fail2"):
            chain.execute()

    def test_empty_chain_raises(self) -> None:
        chain = FallbackChain()
        with pytest.raises(RuntimeError, match="empty"):
            chain.execute()

    def test_multiple_fallbacks(self) -> None:
        chain = FallbackChain()
        chain.add(lambda: (_ for _ in ()).throw(ConnectionError("fail1")))
        chain.add(lambda: (_ for _ in ()).throw(TimeoutError("fail2")))
        chain.add(lambda: (_ for _ in ()).throw(ValueError("fail3")))
        chain.add(lambda: "tertiary")

        result = chain.execute()
        assert result == "tertiary"


# ---------------------------------------------------------------------------
# Degradation Manager tests
# ---------------------------------------------------------------------------


class TestDegradationManager:
    """DegradationManager selects capability tiers."""

    def test_full_tier_when_healthy(self) -> None:
        dm = DegradationManager()
        dm.set_health(True)
        assert dm.get_tier() == "FULL"

    def test_reduced_tier_when_degraded(self) -> None:
        dm = DegradationManager()
        dm.set_health(False)
        # Fresh cache *and* static fallback both available: only non-essential
        # features are shed, so no capability is lost yet -> REDUCED.
        dm.set_cache_available(True)
        dm.set_static_available(True)
        assert dm.get_tier() == "REDUCED"

    def test_cached_tier_when_stale(self) -> None:
        dm = DegradationManager()
        dm.set_health(False)
        dm.set_cache_available(True)
        dm.set_static_available(False)
        assert dm.get_tier() == "CACHED"

    def test_static_tier_when_no_cache(self) -> None:
        dm = DegradationManager()
        dm.set_health(False)
        dm.set_cache_available(False)
        assert dm.get_tier() == "STATIC"

    def test_emergency_tier_when_critical(self) -> None:
        dm = DegradationManager()
        dm.set_health(False)
        dm.set_cache_available(False)
        dm.set_static_available(False)
        assert dm.get_tier() == "EMERGENCY"

    def test_tier_selection_with_custom_thresholds(self) -> None:
        dm = DegradationManager()
        dm.set_health(False)
        dm.set_cache_available(True)
        # Even with cache, if health is bad enough, go to STATIC
        dm.set_cache_staleness(0.99)  # very stale
        assert dm.get_tier() == "STATIC"

    def test_recovery_upgrades_tier(self) -> None:
        dm = DegradationManager()
        dm.set_health(False)
        dm.set_cache_available(False)
        dm.set_static_available(False)
        assert dm.get_tier() == "EMERGENCY"

        dm.set_health(True)
        assert dm.get_tier() == "FULL"

    def test_degradation_ladder_is_monotonic(self) -> None:
        """Each capability removed must move strictly down the ladder."""
        dm = DegradationManager()

        # Healthy -> FULL
        assert dm.get_tier() == "FULL"

        # Unhealthy, cache + static intact -> REDUCED
        dm.set_health(False)
        dm.set_cache_available(True)
        dm.set_static_available(True)
        assert dm.get_tier() == "REDUCED"

        # Lose static -> CACHED
        dm.set_static_available(False)
        assert dm.get_tier() == "CACHED"

        # Lose (stale) cache -> STATIC
        dm.set_cache_staleness(0.95)
        dm.set_static_available(True)
        assert dm.get_tier() == "STATIC"

        # Lose static too -> EMERGENCY
        dm.set_static_available(False)
        assert dm.get_tier() == "EMERGENCY"
