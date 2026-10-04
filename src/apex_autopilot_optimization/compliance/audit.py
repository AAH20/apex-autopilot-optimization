"""Audit trail for compliance event logging."""

import csv
import io
import json
import time
from typing import Any


class AuditTrail:
    """In-memory audit trail for compliance event logging."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def log_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Log a compliance event with type, details, and timestamp."""
        self._events.append(
            {
                "event_type": event_type,
                "details": details,
                "timestamp": time.time(),
            }
        )

    def get_events(self, event_type: str) -> list[dict[str, Any]]:
        """Get all events of a specific type."""
        return [e for e in self._events if e["event_type"] == event_type]

    def get_events_by_time(self, start: float, end: float) -> list[dict[str, Any]]:
        """Get events within a time range [start, end]."""
        return [e for e in self._events if start <= e["timestamp"] <= end]

    def get_events_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """Get all events for a specific user."""
        return [e for e in self._events if e["details"].get("user_id") == user_id]

    def export_events(self, format: str) -> str:
        """Export all events in the specified format (json or csv)."""
        if format == "json":
            return json.dumps(self._events, indent=2)
        elif format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["event_type", "details", "timestamp"])
            for event in self._events:
                writer.writerow(
                    [
                        event["event_type"],
                        json.dumps(event["details"]),
                        event["timestamp"],
                    ]
                )
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def get_event_count(self) -> int:
        """Get the total number of logged events."""
        return len(self._events)

    def clear_events(self) -> None:
        """Remove all logged events."""
        self._events.clear()
