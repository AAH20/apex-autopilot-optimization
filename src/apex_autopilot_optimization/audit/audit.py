"""Audit logging module."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class AuditLevel(Enum):
    """Audit severity levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, AuditLevel):
            return NotImplemented
        order = [
            AuditLevel.DEBUG,
            AuditLevel.INFO,
            AuditLevel.WARNING,
            AuditLevel.ERROR,
            AuditLevel.CRITICAL,
        ]
        return order.index(self) < order.index(other)


class AuditEvent:
    """A single audit event."""

    def __init__(
        self,
        id: str,
        timestamp: float,
        level: AuditLevel,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        details: dict[str, Any] | None = None,
        trace_id: str = "",
    ) -> None:
        self.id = id
        self.timestamp = timestamp
        self.level = level
        self.actor = actor
        self.action = action
        self.resource = resource
        self.outcome = outcome
        self._details: dict[str, Any] = details if details is not None else {}
        self.trace_id = trace_id

    @property
    def details(self) -> dict[str, Any]:
        return self._details

    @details.setter
    def details(self, value: dict[str, Any]) -> None:
        self._details = value


@dataclass
class AuditConfig:
    """Configuration for audit logging."""

    enabled: bool = True
    persistent: bool = False
    storage_path: str = ""
    max_events: int = 10000
    retention_days: int = 90
    tamper_evident: bool = True


class AuditLogger:
    """In-memory audit event logger."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        """Store an audit event."""
        self._events.append(event)

    def get_event_count(self) -> int:
        """Return the number of stored events."""
        return len(self._events)

    def get_events(self) -> list[AuditEvent]:
        """Return all stored events."""
        return list(self._events)

    def get_events_by_actor(self, actor: str) -> list[AuditEvent]:
        """Return events filtered by actor."""
        return [e for e in self._events if e.actor == actor]

    def get_events_by_resource(self, resource: str) -> list[AuditEvent]:
        """Return events filtered by resource."""
        return [e for e in self._events if e.resource == resource]

    def get_events_by_level(self, level: AuditLevel) -> list[AuditEvent]:
        """Return events filtered by level."""
        return [e for e in self._events if e.level == level]

    def get_events_by_time_range(self, start: float, end: float) -> list[AuditEvent]:
        """Return events within [start, end] inclusive."""
        return [e for e in self._events if start <= e.timestamp <= end]

    def export_events(self, fmt: str) -> str:
        """Export events as JSON or CSV."""
        if fmt == "json":
            data = [
                {
                    "id": e.id,
                    "timestamp": e.timestamp,
                    "level": e.level.value,
                    "actor": e.actor,
                    "action": e.action,
                    "resource": e.resource,
                    "outcome": e.outcome,
                    "details": e.details,
                    "trace_id": e.trace_id,
                }
                for e in self._events
            ]
            return json.dumps(data)
        elif fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [
                    "id",
                    "timestamp",
                    "level",
                    "actor",
                    "action",
                    "resource",
                    "outcome",
                    "details",
                    "trace_id",
                ]
            )
            for e in self._events:
                writer.writerow(
                    [
                        e.id,
                        e.timestamp,
                        e.level.value,
                        e.actor,
                        e.action,
                        e.resource,
                        e.outcome,
                        json.dumps(e.details),
                        e.trace_id,
                    ]
                )
            return buf.getvalue()
        else:
            raise ValueError(f"Unsupported export format: {fmt}")

    def clear_events(self) -> None:
        """Remove all stored events."""
        self._events.clear()


class AuditTrail:
    """Tamper-evident audit trail using hash chaining."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._hashes: list[str] = []

    def _compute_hash(self, event: AuditEvent, prev_hash: str) -> str:
        """Compute chained hash for an event."""
        payload = json.dumps(
            {
                "id": event.id,
                "timestamp": event.timestamp,
                "level": event.level.value,
                "actor": event.actor,
                "action": event.action,
                "resource": event.resource,
                "outcome": event.outcome,
                "details": event.details,
                "trace_id": event.trace_id,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def append(self, event: AuditEvent) -> None:
        """Append an event to the trail."""
        prev_hash = self._hashes[-1] if self._hashes else ""
        h = self._compute_hash(event, prev_hash)
        self._events.append(event)
        self._hashes.append(h)

    def get_trail_size(self) -> int:
        """Return the number of events in the trail."""
        return len(self._events)

    def get_trail(self, resource: str) -> list[AuditEvent]:
        """Return events for a given resource."""
        return [e for e in self._events if e.resource == resource]

    def get_trail_by_actor(self, actor: str) -> list[AuditEvent]:
        """Return events for a given actor."""
        return [e for e in self._events if e.actor == actor]

    def verify_integrity(self) -> bool:
        """Verify the hash chain has not been tampered with."""
        prev_hash = ""
        for i, event in enumerate(self._events):
            expected = self._compute_hash(event, prev_hash)
            if expected != self._hashes[i]:
                return False
            prev_hash = expected
        return True

    def get_chain_hash(self) -> str:
        """Return the latest chain hash."""
        if not self._hashes:
            return ""
        return self._hashes[-1]
