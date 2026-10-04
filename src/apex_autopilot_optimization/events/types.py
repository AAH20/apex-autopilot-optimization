"""Event types and data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class EventPriority(IntEnum):
    """Priority levels for events. Lower value = higher priority."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Event:
    """Represents a single event in the system."""

    type: str
    source: str
    payload: Any
    timestamp: float
    priority: EventPriority = EventPriority.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EventEnvelope:
    """Wraps an event with tracing information."""

    event: Event
    trace_id: str
    timestamp: float
