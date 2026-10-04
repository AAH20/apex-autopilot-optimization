"""Core domain types for the autopilot optimization framework."""
from apex_autopilot_optimization.core.types import (
    VehicleType,
    Pose3D,
    Velocity3D,
    StateVector,
    ControlInput,
    Waypoint,
    Trajectory,
    OptimizationConstraint,
    OptimizationObjective,
    PlanningProblem,
    PlanningResult,
    ComplexityClass,
    BottleneckReport,
)

__all__ = [
    "VehicleType",
    "Pose3D",
    "Velocity3D",
    "StateVector",
    "ControlInput",
    "Waypoint",
    "Trajectory",
    "OptimizationConstraint",
    "OptimizationObjective",
    "PlanningProblem",
    "PlanningResult",
    "ComplexityClass",
    "BottleneckReport",
]
