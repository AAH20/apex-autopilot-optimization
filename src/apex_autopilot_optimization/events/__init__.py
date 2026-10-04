"""Event bus system for inter-module communication."""
from apex_autopilot_optimization.events.bus import EventBus
from apex_autopilot_optimization.events.handlers import EventHandler, HandlerRegistry
from apex_autopilot_optimization.events.middleware import LoggingMiddleware, MetricsMiddleware
from apex_autopilot_optimization.events.types import Event, EventEnvelope, EventPriority

__all__ = [
    "Event",
    "EventBus",
    "EventEnvelope",
    "EventPriority",
    "EventHandler",
    "HandlerRegistry",
    "LoggingMiddleware",
    "MetricsMiddleware",
]
