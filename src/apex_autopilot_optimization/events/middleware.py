"""Event bus middleware."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from apex_autopilot_optimization.events.types import Event


class Middleware(Protocol):
    """Protocol for event bus middleware."""

    def process(self, event: Event) -> None: ...


class LoggingMiddleware:
    """Middleware that logs events as they pass through."""

    def __init__(self, logger: Callable[[str], None]) -> None:
        self._logger = logger

    def process(self, event: Event) -> None:
        """Log the event."""
        self._logger(
            f"Event: type={event.type} source={event.source} "
            f"priority={event.priority.name}"
        )


class MetricsMiddleware:
    """Middleware that counts events by type."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def process(self, event: Event) -> None:
        """Increment the counter for the event type."""
        self._counts[event.type] = self._counts.get(event.type, 0) + 1

    def get_count(self, event_type: str) -> int:
        """Get the count for a specific event type."""
        return self._counts.get(event_type, 0)
