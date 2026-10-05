"""Tamper-evident audit trail using hash chaining."""
from __future__ import annotations

import hashlib
import json

from apex_autopilot_optimization.audit.logger import AuditEvent


class AuditTrail:
    """Tamper-evident audit trail using hash chaining.

    Each event's hash includes the previous event's hash, creating
    a chain where any modification to historical events invalidates
    all subsequent hashes.
    """

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
        """Verify the hash chain has not been tampered with.

        Returns:
            True if the chain is intact, False if any event was modified.
        """
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
