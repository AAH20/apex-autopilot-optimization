"""Safety case management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apex_autopilot_optimization.formal.property import (
    SafetyProperty,
    verify_property,
)


@dataclass
class SafetyCase:
    """A safety case containing multiple safety properties.

    Attributes:
        id: Unique identifier for the safety case.
        title: Human-readable title.
        properties: List of safety properties in this case.
        status: Current status of the safety case (e.g., DRAFT, VERIFIED).
        created_at: Timestamp of creation.
    """

    id: str
    title: str
    properties: list[SafetyProperty] = field(default_factory=list)
    status: str = "DRAFT"
    created_at: float = 0.0

    def add_property(self, prop: SafetyProperty) -> None:
        """Add a safety property to the case."""
        self.properties.append(prop)

    def remove_property(self, prop: SafetyProperty) -> None:
        """Remove a safety property from the case."""
        self.properties.remove(prop)

    def verify_all(self, state: dict[str, Any]) -> dict[str, bool]:
        """Verify all properties against a state; returns id -> result."""
        return {prop.id: verify_property(prop, state) for prop in self.properties}

    def get_case_status(self) -> str:
        """Return the status of the safety case."""
        return self.status

    def get_failure_count(self, state: dict[str, Any]) -> int:
        """Count how many properties fail against the given state."""
        return sum(1 for result in self.verify_all(state).values() if not result)
