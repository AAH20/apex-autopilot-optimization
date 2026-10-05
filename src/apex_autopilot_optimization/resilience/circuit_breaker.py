"""Circuit breaker pattern implementation."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before transitioning to HALF_OPEN.
        half_open_max_calls: Max calls allowed in HALF_OPEN state.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3


class CircuitBreaker:
    """Circuit breaker with CLOSED/OPEN/HALF_OPEN state machine.

    The circuit breaker wraps a callable and prevents cascading failures
    by short-circuiting calls when the failure threshold is reached.

    States:
        CLOSED: Normal operation, calls pass through.
        OPEN: Failure threshold reached, calls are rejected immediately.
        HALF_OPEN: Recovery timeout elapsed, limited calls allowed to test.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = threading.Lock()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute the wrapped function through the circuit breaker.

        Args:
            func: The function to call.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The function's return value on success.

        Raises:
            RuntimeError: If the circuit is OPEN or HALF_OPEN limit reached.
            Any exception raised by the function itself.
        """
        with self._lock:
            if self._state == self.OPEN:
                if self._should_attempt_reset():
                    self._state = self.HALF_OPEN
                    self._half_open_calls = 0
                else:
                    raise RuntimeError("Circuit breaker is OPEN")

            if self._state == self.HALF_OPEN:
                if self._half_open_calls >= self._config.half_open_max_calls:
                    raise RuntimeError("Circuit breaker HALF_OPEN limit reached")
                self._half_open_calls += 1

        # Execute outside the lock
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def get_state(self) -> str:
        """Return the current circuit breaker state.

        Returns:
            "CLOSED", "OPEN", or "HALF_OPEN".
        """
        with self._lock:
            if self._state == self.OPEN and self._should_attempt_reset():
                self._state = self.HALF_OPEN
                self._half_open_calls = 0
            return self._state

    def get_metrics(self) -> dict[str, Any]:
        """Return circuit breaker metrics.

        Returns:
            Dictionary with failure_count, success_count, and state.
        """
        with self._lock:
            return {
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "state": self._state,
            }

    def _should_attempt_reset(self) -> bool:
        """Check if recovery timeout has elapsed."""
        if self._last_failure_time is None:
            return True
        return (time.monotonic() - self._last_failure_time) >= self._config.recovery_timeout

    def _on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            self._failure_count = 0
            self._success_count += 1
            if self._state == self.HALF_OPEN:
                self._state = self.CLOSED
                self._half_open_calls = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._half_open_calls = 0
            elif self._failure_count >= self._config.failure_threshold:
                self._state = self.OPEN
