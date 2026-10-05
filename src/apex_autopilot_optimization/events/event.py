"""Event data structures: Event, EventPriority, EventFilter."""
from __future__ import annotations

import uuid
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
    timestamp: float
    payload: Any = None
    priority: EventPriority = EventPriority.NORMAL
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class EventFilter:
    """Filter criteria for matching events."""

    types: set[str] | None = None
    sources: set[str] | None = None
    min_priority: EventPriority | None = None

    def matches(self, event: Event) -> bool:
        """Check if an event matches this filter."""
        if self.types is not None and event.type not in self.types:
            return False
        if self.sources is not None and event.source not in self.sources:
            return False
        return not (self.min_priority is not None and event.priority > self.min_priority)
