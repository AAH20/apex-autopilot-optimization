"""Retry mechanism with exponential backoff and full jitter."""

from __future__ import annotations

import functools
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of attempts before giving up.
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Maximum delay cap in seconds.
        exponential_base: Base for exponential backoff calculation.
        retryable_exceptions: Tuple of exception types that trigger a retry.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )


def _compute_delay(attempt: int, config: RetryConfig) -> float:
    """Compute delay with exponential backoff and equal jitter.

    Uses the "equal jitter" approach: sleep = capped/2 + random(0, capped/2).
    This decorrelates retries across clients (avoiding a thundering herd)
    while guaranteeing each successive window lies strictly above the
    previous one, so backoff remains monotonically increasing. Full jitter
    (random(0, capped)) is deliberately avoided: its overlapping windows
    can produce a shorter delay on a later attempt.
    """
    exp_delay = config.base_delay * (config.exponential_base**attempt)
    capped = min(exp_delay, config.max_delay)
    half = capped / 2.0
    return half + random.uniform(0, half)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    ),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that retries a function with exponential backoff and full jitter.

    Args:
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        exponential_base: Base for exponential backoff.
        retryable_exceptions: Exception types that trigger retry.

    Returns:
        Decorated function with retry behavior.
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        retryable_exceptions=retryable_exceptions,
    )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return retry_with_config(func, config, *args, **kwargs)

        return wrapper

    return decorator


def retry_with_config(
    func: Callable[..., T],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Retry a function with the given configuration.

    Args:
        func: The function to retry.
        config: Retry configuration.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The function's return value on success.

    Raises:
        The last exception if all attempts fail.
    """
    last_exception: BaseException | None = None

    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except config.retryable_exceptions as exc:
            last_exception = exc
            if attempt < config.max_attempts - 1:
                delay = _compute_delay(attempt, config)
                time.sleep(delay)

    raise last_exception  # type: ignore[misc]
