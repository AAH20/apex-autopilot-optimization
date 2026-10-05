"""Event middleware: ABC and concrete implementations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from apex_autopilot_optimization.events.event import Event


class EventMiddleware(ABC):
    """Abstract base class for event middleware."""

    @abstractmethod
    def process(self, event: Event) -> Event:
        """Process an event and return it (possibly modified)."""
        ...


class LoggingMiddleware(EventMiddleware):
    """Middleware that logs events as they pass through."""

    def __init__(self, logger: Callable[[str], None] | None = None) -> None:
        self._logger = logger or print

    def process(self, event: Event) -> Event:
        """Log the event and return it unchanged."""
        self._logger(
            f"Event: id={event.id} type={event.type} source={event.source} "
            f"priority={event.priority.name}"
        )
        return event


class MetricsMiddleware(EventMiddleware):
    """Middleware that counts events by type."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def process(self, event: Event) -> Event:
        """Increment the counter for the event type."""
        self._counts[event.type] = self._counts.get(event.type, 0) + 1
        return event

    def get_count(self, event_type: str) -> int:
        """Get the count for a specific event type."""
        return self._counts.get(event_type, 0)

    def get_all_counts(self) -> dict[str, int]:
        """Get all event counts."""
        return dict(self._counts)


class ValidationMiddleware(EventMiddleware):
    """Middleware that validates events before processing."""

    def __init__(self) -> None:
        self._errors: list[str] = []

    def process(self, event: Event) -> Event:
        """Validate the event and return it unchanged."""
        self._errors.clear()
        if not event.type:
            raise ValueError("Event type must not be empty")
        if not event.source:
            raise ValueError("Event source must not be empty")
        if event.timestamp <= 0:
            raise ValueError("Event timestamp must be positive")
        return event

    def get_errors(self) -> list[str]:
        """Get validation errors from the last process call."""
        return list(self._errors)
