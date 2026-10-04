"""Fallback chain and degradation manager patterns."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


class FallbackChain:
    """Chain of fallback functions tried in order until one succeeds.

    Each function is called in sequence. If one raises an exception,
    the next is tried. If all fail, the last exception is raised.
    """

    def __init__(self) -> None:
        self._functions: list[Callable[..., Any]] = []

    def add(self, func: Callable[..., Any]) -> None:
        """Add a function to the fallback chain.

        Args:
            func: The function to add.
        """
        self._functions.append(func)

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the fallback chain.

        Tries each function in order until one succeeds.

        Args:
            *args: Positional arguments for the functions.
            **kwargs: Keyword arguments for the functions.

        Returns:
            The first successful function's return value.

        Raises:
            RuntimeError: If the chain is empty.
            The last exception if all functions fail.
        """
        if not self._functions:
            raise RuntimeError("FallbackChain is empty")

        last_exception: BaseException | None = None

        for func in self._functions:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exception = exc

        raise last_exception  # type: ignore[misc]


class DegradationManager:
    """Manages capability degradation tiers based on system health.

    Tiers (from most to least capable):
        FULL: All features available.
        REDUCED: Non-essential features disabled.
        CACHED: Serving cached/stale data.
        STATIC: Serving static fallback data.
        EMERGENCY: Minimal safe-mode operation only.
    """

    FULL = "FULL"
    REDUCED = "REDUCED"
    CACHED = "CACHED"
    STATIC = "STATIC"
    EMERGENCY = "EMERGENCY"

    def __init__(self) -> None:
        self._healthy = True
        self._cache_available = False
        self._static_available = True
        self._cache_staleness = 0.0

    def set_health(self, healthy: bool) -> None:
        """Set system health status.

        Args:
            healthy: True if system is healthy, False otherwise.
        """
        self._healthy = healthy

    def set_cache_available(self, available: bool) -> None:
        """Set cache availability.

        Args:
            available: True if cache is available, False otherwise.
        """
        self._cache_available = available

    def set_static_available(self, available: bool) -> None:
        """Set static fallback availability.

        Args:
            available: True if static fallback is available, False otherwise.
        """
        self._static_available = available

    def set_cache_staleness(self, staleness: float) -> None:
        """Set cache staleness ratio (0.0 = fresh, 1.0 = completely stale).

        Args:
            staleness: Staleness ratio between 0.0 and 1.0.
        """
        self._cache_staleness = max(0.0, min(1.0, staleness))

    def get_tier(self) -> str:
        """Determine the current capability tier.

        Returns:
            One of FULL, REDUCED, CACHED, STATIC, EMERGENCY.
        """
        if self._healthy:
            return self.FULL

        if self._cache_available and self._cache_staleness < 0.9:
            return self.CACHED

        if self._static_available:
            return self.STATIC

        return self.EMERGENCY
