"""Pydantic schemas for structured API inputs.

These models provide declarative validation for the main input types
accepted by the optimization pipeline: planning problems, planning results,
and configuration dictionaries.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlanningProblemInput(BaseModel):
    """Input schema for a path/trajectory planning problem."""

    vehicle_type: Literal[
        "uav_fixed_wing",
        "uav_multirotor",
        "uav_vtol",
        "ground_vehicle_ackermann",
        "ground_vehicle_differential_drive",
        "ground_vehicle_omni",
    ]
    start: dict[str, float] = Field(min_length=1)
    goal: dict[str, float] = Field(min_length=1)
    waypoints: list[dict[str, float]] = Field(default_factory=list)
    obstacles: list[dict] = Field(default_factory=list)
    time_horizon_s: float = Field(default=60.0, gt=0)
    resolution_m: float = Field(default=1.0, gt=0)


class PlanningResultInput(BaseModel):
    """Input schema for the result of a planning operation."""

    success: bool
    computation_time_ms: float = Field(default=0.0, ge=0)
    iterations: int = Field(default=0, ge=0)
    cost: float = Field(default=0.0, ge=0)
    message: str = Field(default="", max_length=1000)
    metadata: dict = Field(default_factory=dict)


class ConfigInput(BaseModel):
    """Input schema for pipeline configuration."""

    scale: Literal["startup", "smb", "mid_market", "enterprise", "large"] = "startup"
    planner: Literal["astar", "rrt", "prm", "hybrid_astar"] = "astar"
    optimizer: Literal["minimum_snap"] = "minimum_snap"
    estimator: Literal["ekf"] = "ekf"
    safety_filter: Literal["cbf", "none"] = "none"
    controller: Literal["mpc", "none"] = "none"
    max_iterations: int = Field(default=10000, gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
