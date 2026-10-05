"""Result types for chaos engineering fault injection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChaosResult:
    """Result of a fault injection operation.

    Attributes:
        fault_type: The type of fault that was injected.
        target: The target module or component.
        start_time: Unix timestamp when the fault was injected.
        end_time: Unix timestamp when the fault was removed (None if still active).
        params: Parameters specific to the fault type.
        status: Current status of the fault ("active", "completed", "failed").
    """

    fault_type: str
    target: str
    start_time: float
    end_time: float | None = None
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "active"

    def duration(self) -> float | None:
        """Return the duration of the fault in seconds, or None if still active."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    def is_active(self) -> bool:
        """Return True if the fault is still active."""
        return self.status == "active"
