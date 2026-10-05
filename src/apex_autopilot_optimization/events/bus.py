"""Event bus implementation."""

from __future__ import annotations

from collections.abc import Callable

from apex_autopilot_optimization.events.event import Event, EventFilter
from apex_autopilot_optimization.events.middleware import EventMiddleware


class EventBus:
    """Synchronous event bus for publish/subscribe communication."""

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._middleware: list[EventMiddleware] = []
        self._event_count: int = 0
        self._history: list[Event] = []
        self._max_history: int = max_history

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribed handlers."""
        for mw in self._middleware:
            mw.process(event)
        for handler in self._subscribers.get(event.type, []):
            handler(event)
        self._event_count += 1
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    def get_handlers(self, event_type: str) -> list[Callable[[Event], None]]:
        """Get all handlers for an event type."""
        return list(self._subscribers.get(event_type, []))

    def clear_handlers(self) -> None:
        """Remove all handlers."""
        self._subscribers.clear()

    def get_event_count(self) -> int:
        """Get the total number of events published."""
        return self._event_count

    def get_event_history(self, limit: int | None = None) -> list[Event]:
        """Get the event history, optionally limited to the most recent N events."""
        if limit is None:
            return list(self._history)
        return list(self._history[-limit:])

    def add_middleware(self, middleware: EventMiddleware) -> None:
        """Add middleware to the processing chain."""
        self._middleware.append(middleware)

    def remove_middleware(self, middleware: EventMiddleware) -> None:
        """Remove middleware from the processing chain."""
        self._middleware = [mw for mw in self._middleware if mw is not middleware]

    def get_middleware(self) -> list[EventMiddleware]:
        """Get all registered middleware."""
        return list(self._middleware)

    def clear_history(self) -> None:
        """Clear the event history."""
        self._history.clear()

    def get_filtered_history(self, event_filter: EventFilter) -> list[Event]:
        """Get history events matching the given filter."""
        return [e for e in self._history if event_filter.matches(e)]
