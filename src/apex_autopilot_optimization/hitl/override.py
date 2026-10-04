"""Human override dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HumanOverride:
    """A human operator's override of an autopilot decision.

    Attributes:
        id: Unique override identifier.
        original_decision: The autopilot's original decision.
        override_decision: The human's replacement decision.
        operator: Who issued the override.
        reason: Why the override was issued.
        timestamp: Unix timestamp of the override.
    """

    id: str
    original_decision: str
    override_decision: str
    operator: str
    reason: str
    timestamp: float

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HumanOverride):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
