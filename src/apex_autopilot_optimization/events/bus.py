"""Event bus implementation."""
from __future__ import annotations

from apex_autopilot_optimization.events.handlers import EventHandler
from apex_autopilot_optimization.events.middleware import Middleware
from apex_autopilot_optimization.events.types import Event


class EventBus:
    """Synchronous event bus for publish/subscribe communication."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._middleware: list[Middleware] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
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

    def get_subscribers(self, event_type: str) -> list[EventHandler]:
        """Get all subscribers for an event type."""
        return list(self._subscribers.get(event_type, []))

    def clear(self) -> None:
        """Remove all subscribers."""
        self._subscribers.clear()

    def add_middleware(self, middleware: Middleware) -> None:
        """Add middleware to the processing chain."""
        self._middleware.append(middleware)
