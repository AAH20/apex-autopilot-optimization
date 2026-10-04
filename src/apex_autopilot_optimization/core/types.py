"""Core domain types for UAV/UAS and ground vehicle autopilot optimization.

This module defines the foundational data structures used across the entire
framework: vehicle state representations, planning problems, optimization
constraints, and complexity classifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np
from numpy.typing import NDArray


class VehicleType(Enum):
    """Supported vehicle categories."""

    UAV_FIXED_WING = auto()
    UAV_MULTIROTOR = auto()
    UAV_VTOL = auto()
    GROUND_VEHICLE_ACKERMANN = auto()
    GROUND_VEHICLE_DIFFERENTIAL_DRIVE = auto()
    GROUND_VEHICLE_OMNI = auto()


class ComplexityClass(Enum):
    """Computational complexity classification."""

    P = "polynomial"
    NP_HARD = "NP-hard"
    NP_COMPLETE = "NP-complete"
    EXPTIME = "exponential"
    PSPACE = "PSPACE"
    APPROXIMATION = "approximation"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Pose3D:
    """3D pose with position and orientation."""

    x: float
    y: float
    z: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    def position(self) -> NDArray[np.float64]:
        """Return position as numpy array."""
        return np.array([self.x, self.y, self.z], dtype=np.float64)

    def distance_to(self, other: Pose3D) -> float:
        """Euclidean distance to another pose."""
        return float(np.linalg.norm(self.position() - other.position()))


@dataclass(frozen=True, slots=True)
class Velocity3D:
    """3D velocity vector."""

    vx: float
    vy: float
    vz: float
    vroll: float = 0.0
    vpitch: float = 0.0
    vyaw: float = 0.0

    def magnitude(self) -> float:
        """Return velocity magnitude."""
        return float(np.sqrt(self.vx**2 + self.vy**2 + self.vz**2))


@dataclass(frozen=True, slots=True)
class StateVector:
    """Complete vehicle state vector."""

    pose: Pose3D
    velocity: Velocity3D
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_array(self) -> NDArray[np.float64]:
        """Flatten state to numpy array."""
        return np.array(
            [
                self.pose.x,
                self.pose.y,
                self.pose.z,
                self.pose.roll,
                self.pose.pitch,
                self.pose.yaw,
                self.velocity.vx,
                self.velocity.vy,
                self.velocity.vz,
                self.velocity.vroll,
                self.velocity.vpitch,
                self.velocity.vyaw,
            ],
            dtype=np.float64,
        )


@dataclass(frozen=True, slots=True)
class ControlInput:
    """Control input for vehicle actuation."""

    throttle: float = 0.0
    roll_rate: float = 0.0
    pitch_rate: float = 0.0
    yaw_rate: float = 0.0
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class Waypoint:
    """Navigation waypoint with timing and tolerance."""

    pose: Pose3D
    speed: float = 0.0
    arrival_time: float | None = None
    tolerance_m: float = 1.0
    hold_time_s: float = 0.0


@dataclass(frozen=True, slots=True)
class Trajectory:
    """Time-parameterized trajectory."""

    states: list[StateVector]
    controls: list[ControlInput]
    timestamps: NDArray[np.float64]
    vehicle_type: VehicleType

    def duration(self) -> float:
        """Total trajectory duration in seconds."""
        if len(self.timestamps) < 2:
            return 0.0
        return float(self.timestamps[-1] - self.timestamps[0])

    def length(self) -> float:
        """Total path length in meters."""
        if len(self.states) < 2:
            return 0.0
        total = 0.0
        for i in range(1, len(self.states)):
            total += self.states[i].pose.distance_to(self.states[i - 1].pose)
        return total


@dataclass(frozen=True, slots=True)
class OptimizationConstraint:
    """Constraint for trajectory/path optimization."""

    name: str
    constraint_type: str  # "inequality", "equality", "bound"
    lower_bound: float | None = None
    upper_bound: float | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OptimizationObjective:
    """Objective function for optimization."""

    name: str
    weight: float = 1.0
    minimize: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanningProblem:
    """Complete planning problem specification."""

    vehicle_type: VehicleType
    start: StateVector
    goal: Waypoint
    waypoints: list[Waypoint] = field(default_factory=list)
    obstacles: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[OptimizationConstraint] = field(default_factory=list)
    objectives: list[OptimizationObjective] = field(default_factory=list)
    time_horizon_s: float = 60.0
    resolution_m: float = 1.0


@dataclass(frozen=True, slots=True)
class PlanningResult:
    """Result of a planning operation."""

    success: bool
    trajectory: Trajectory | None = None
    computation_time_ms: float = 0.0
    iterations: int = 0
    cost: float = 0.0
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BottleneckReport:
    """Identified bottleneck with severity and classification."""

    description: str
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "computational", "memory", "latency", "scalability", "accuracy"
    complexity: ComplexityClass = ComplexityClass.UNKNOWN
    source: str = ""
    url: str = ""
