"""Fault type definitions and schedules for chaos engineering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class FaultType(Enum):
    """Types of faults that can be injected into the system."""

    NETWORK_DELAY = auto()
    NETWORK_DROP = auto()
    CPU_SPIKE = auto()
    MEMORY_PRESSURE = auto()
    SENSOR_NOISE = auto()
    SENSOR_DROPOUT = auto()
    ACTUATOR_FAILURE = auto()
    COMMUNICATION_ERROR = auto()
    CLOCK_DRIFT = auto()
    PACKET_LOSS = auto()


class Severity(Enum):
    """Fault severity (higher = more dangerous, mirroring veto ordering)."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class FaultSpec:
    """A single fault injection entry.

    Attributes:
        fault_type: Kind of fault to inject.
        target: Dotted name of the component/method the fault applies to.
        params: Fault-type-specific parameters (delay_ms, noise_std, ...).
        duration_sec: How long the fault stays active (None = until removed).
        start_after_sec: Delay before the fault becomes eligible for injection.
        repeat: Whether the fault may be re-injected after removal.
        severity: Severity of the fault.
        enabled: Whether this spec is eligible for injection.
    """

    fault_type: FaultType
    target: str
    params: dict[str, Any] = field(default_factory=dict)
    duration_sec: float | None = None
    start_after_sec: float = 0.0
    repeat: bool = False
    severity: Severity = Severity.MEDIUM
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.duration_sec is not None and self.duration_sec < 0:
            raise ValueError(f"duration_sec must be >= 0, got {self.duration_sec}")
        if self.start_after_sec < 0:
            raise ValueError(f"start_after_sec must be >= 0, got {self.start_after_sec}")


@dataclass
class FaultSchedule:
    """Ordered schedule of faults to inject during an experiment."""

    faults: list[FaultSpec] = field(default_factory=list)

    def add(self, fault: FaultSpec) -> None:
        """Append a fault spec to the schedule."""
        self.faults.append(fault)

    def due_at(self, now_sec: float) -> list[FaultSpec]:
        """Return enabled faults whose start time has arrived at ``now_sec``."""
        return [f for f in self.faults if f.enabled and f.start_after_sec <= now_sec]

    def __iter__(self):
        return iter(self.faults)
