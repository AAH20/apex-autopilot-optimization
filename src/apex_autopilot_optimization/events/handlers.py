"""Event handler protocol and registry."""
from __future__ import annotations

from typing import Protocol

from apex_autopilot_optimization.events.types import Event


class EventHandler(Protocol):
    """Protocol for event handler callables."""

    def __call__(self, event: Event) -> None: ...


class HandlerRegistry:
    """Registry mapping event types to their handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unregister(self, event_type: str, handler: EventHandler) -> None:
        """Remove a handler from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h is not handler]

    def get_handlers(self, event_type: str) -> list[EventHandler]:
        """Get all handlers for an event type."""
        return list(self._handlers.get(event_type, []))
