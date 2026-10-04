"""Event store implementation."""
from __future__ import annotations

from typing import Any


class EventStore:
    """In-memory event store with replay support."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._next_position = 1

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        """Append an event, assigning a monotonic position."""
        event["position"] = self._next_position
        self._next_position += 1
        self._events.append(event)
        return event

    def get_events(self, aggregate_id: str) -> list[dict[str, Any]]:
        """Get all events for an aggregate."""
        return [e for e in self._events if e.get("aggregate_id") == aggregate_id]

    def get_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get all events of a specific type."""
        return [e for e in self._events if e.get("type") == event_type]

    def get_all_events(self) -> list[dict[str, Any]]:
        """Get all events."""
        return list(self._events)

    def replay_events(self, from_position: int) -> list[dict[str, Any]]:
        """Replay events from a given position (inclusive)."""
        return [e for e in self._events if e["position"] >= from_position]

    def get_event_count(self) -> int:
        """Get the total number of events."""
        return len(self._events)
