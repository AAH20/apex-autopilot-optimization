"""Event bus system for inter-module communication."""

from __future__ import annotations

from collections.abc import Callable

from apex_autopilot_optimization.events.bus import EventBus
from apex_autopilot_optimization.events.event import Event, EventFilter, EventPriority
from apex_autopilot_optimization.events.middleware import (
    EventMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
    ValidationMiddleware,
)

__all__ = [
    "Event",
    "EventBus",
    "EventFilter",
    "EventMiddleware",
    "EventPriority",
    "LoggingMiddleware",
    "MetricsMiddleware",
    "ValidationMiddleware",
    "publish",
    "subscribe",
]


def subscribe(bus: EventBus, event_type: str, handler: Callable[[Event], None]) -> None:
    """Convenience function to subscribe a handler to a bus."""
    bus.subscribe(event_type, handler)


def publish(bus: EventBus, event: Event) -> None:
    """Convenience function to publish an event to a bus."""
    bus.publish(event)
