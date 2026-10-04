"""Safety properties and safety cases."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class SafetySeverity(str, Enum):
    """Severity levels for safety properties."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class SafetyProperty:
    """A formal safety property."""

    id: str
    name: str
    description: str
    expression: str
    severity: str


def verify_property(prop: SafetyProperty, state: Dict[str, Any]) -> bool:
    """Verify a safety property expression against a system state.

    The expression is evaluated with the state dict as its namespace.
    Any evaluation error or non-boolean result is treated as False.
    """
    try:
        namespace = {k: v for k, v in state.items() if isinstance(k, str)}
        result = eval(prop.expression, {"__builtins__": {}}, namespace)  # noqa: S307
        return bool(result)
    except Exception:
        return False


def get_property_status(prop: SafetyProperty) -> str:
    """Return the verification status of a safety property."""
    return getattr(prop, "status", "UNVERIFIED")


@dataclass
class SafetyCase:
    """A safety case containing multiple safety properties."""

    id: str
    title: str
    properties: List[SafetyProperty] = field(default_factory=list)
    status: str = "DRAFT"
    created_at: float = 0.0

    def add_property(self, prop: SafetyProperty) -> None:
        """Add a safety property to the case."""
        self.properties.append(prop)

    def remove_property(self, prop: SafetyProperty) -> None:
        """Remove a safety property from the case."""
        self.properties.remove(prop)

    def verify_all(self, state: Dict[str, Any]) -> Dict[str, bool]:
        """Verify all properties against a state; returns id -> result."""
        return {prop.id: verify_property(prop, state) for prop in self.properties}

    def get_case_status(self) -> str:
        """Return the status of the safety case."""
        return self.status

    def get_failure_count(self, state: Dict[str, Any]) -> int:
        """Count how many properties fail against the given state."""
        return sum(1 for result in self.verify_all(state).values() if not result)
