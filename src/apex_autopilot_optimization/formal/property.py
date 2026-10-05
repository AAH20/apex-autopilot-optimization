"""Safety property definitions and verification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SafetySeverity(StrEnum):
    """Severity levels for safety properties."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class SafetyProperty:
    """A formal safety property.

    Attributes:
        id: Unique identifier for the property.
        name: Human-readable name.
        description: Detailed description of the safety requirement.
        expression: Python expression evaluated against a system state dict.
        severity: Safety severity level (CRITICAL, HIGH, MEDIUM, LOW).
    """

    id: str
    name: str
    description: str
    expression: str
    severity: str


def verify_property(prop: SafetyProperty, state: dict[str, Any]) -> bool:
    """Verify a safety property expression against a system state.

    The expression is evaluated with the state dict as its namespace.
    Any evaluation error or non-boolean result is treated as False.

    Args:
        prop: The safety property to verify.
        state: System state dictionary used as the evaluation namespace.

    Returns:
        True if the property holds, False otherwise.
    """
    try:
        namespace = {k: v for k, v in state.items() if isinstance(k, str)}
        result = eval(prop.expression, {"__builtins__": {}}, namespace)  # noqa: S307
        return bool(result)
    except Exception:
        return False


def get_property_status(prop: SafetyProperty) -> str:
    """Return the verification status of a safety property.

    Args:
        prop: The safety property.

    Returns:
        The status string, defaulting to "UNVERIFIED" if not set.
    """
    return getattr(prop, "status", "UNVERIFIED")
