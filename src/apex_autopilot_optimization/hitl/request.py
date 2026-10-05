"""Approval request dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApprovalRequest:
    """A request for human approval of an autopilot action.

    Attributes:
        id: Unique request identifier.
        action: The action being requested (e.g. ``"arm_motors"``).
        requester: Who/what submitted the request.
        context: Arbitrary context data for the approver.
        priority: Priority level (e.g. ``"low"``, ``"medium"``, ``"high"``).
        created_at: Unix timestamp of creation.
        expires_at: Unix timestamp after which the request expires, or None
            for no expiry.
    """

    id: str
    action: str
    requester: str
    context: dict[str, Any] = field(default_factory=dict)
    priority: str = "medium"
    created_at: float = 0.0
    expires_at: float | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ApprovalRequest):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
