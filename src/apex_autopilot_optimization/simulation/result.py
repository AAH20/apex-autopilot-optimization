"""Simulation result dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Result of a simulation mission execution.

    Attributes:
        success: Whether the mission completed successfully.
        trajectory: List of state samples collected during the mission.
        metrics: Dictionary of computed mission metrics.
        duration_seconds: Wall-clock duration of the mission.
        message: Human-readable status message.
    """

    success: bool = False
    trajectory: list[Any] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    message: str = ""
