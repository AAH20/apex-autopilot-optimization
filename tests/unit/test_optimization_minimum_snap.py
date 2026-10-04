"""Tests for trajectory optimization algorithms."""

from __future__ import annotations

import numpy as np
import pytest

from apex_autopilot_optimization.core.types import (
    PlanningProblem,
    PlanningResult,
    Pose3D,
    StateVector,
    Velocity3D,
    VehicleType,
    Waypoint,
)
from apex_autopilot_optimization.optimization.minimum_snap import (
    MinimumSnapConfig,
    MinimumSnapOptimizer,
)


class TestMinimumSnapConfig:
    """Tests for MinimumSnapConfig."""

    def test_defaults(self) -> None:
        config = MinimumSnapConfig()
        assert config.degree == 5
        assert config.waypoint_count == 10
        assert config.max_iterations == 100
        assert config.convergence_threshold == 1e-6

    def test_custom_values(self) -> None:
        config = MinimumSnapConfig(degree=7, waypoint_count=20, max_iterations=200)
        assert config.degree == 7
        assert config.waypoint_count == 20
        assert config.max_iterations == 200


class TestMinimumSnapOptimizer:
    """Tests for MinimumSnapOptimizer."""

    def _make_problem(
        self,
        start: tuple[float, float, float] = (0, 0, 0),
        goal: tuple[float, float, float] = (10, 10, 0),
    ) -> PlanningProblem:
        return PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(
                pose=Pose3D(x=start[0], y=start[1], z=start[2]),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=goal[0], y=goal[1], z=goal[2])),
            time_horizon_s=10.0,
        )

    def test_optimize_simple_trajectory(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = self._make_problem()
        result = optimizer.optimize(problem)
        assert result.success
        assert result.trajectory is not None
        assert len(result.trajectory.states) > 0

    def test_optimize_produces_smooth_trajectory(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = self._make_problem((0, 0, 0), (5, 5, 0))
        result = optimizer.optimize(problem)
        assert result.success
        traj = result.trajectory
        assert traj is not None
        # Check that trajectory has reasonable number of states
        assert len(traj.states) >= 2

    def test_optimize_respects_time_horizon(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(
                pose=Pose3D(x=0, y=0, z=0),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=5, y=5, z=0)),
            time_horizon_s=5.0,
        )
        result = optimizer.optimize(problem)
        assert result.success
        traj = result.trajectory
        assert traj is not None
        assert traj.duration() <= 5.0 + 0.01

    def test_optimize_start_end_positions(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = self._make_problem((1, 2, 3), (8, 7, 6))
        result = optimizer.optimize(problem)
        assert result.success
        traj = result.trajectory
        assert traj is not None
        start_pos = traj.states[0].pose
        end_pos = traj.states[-1].pose
        assert start_pos.distance_to(Pose3D(1, 2, 3)) < 0.5
        assert end_pos.distance_to(Pose3D(8, 7, 6)) < 0.5

    def test_optimize_returns_cost(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = self._make_problem()
        result = optimizer.optimize(problem)
        assert result.cost >= 0

    def test_optimize_with_waypoints(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(
                pose=Pose3D(x=0, y=0, z=0),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=10, y=0, z=0)),
            waypoints=[
                Waypoint(pose=Pose3D(x=3, y=2, z=0)),
                Waypoint(pose=Pose3D(x=7, y=-2, z=0)),
            ],
        )
        result = optimizer.optimize(problem)
        assert result.success
        assert result.trajectory is not None

    def test_optimize_3d_trajectory(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = self._make_problem((0, 0, 0), (5, 5, 5))
        result = optimizer.optimize(problem)
        assert result.success
        traj = result.trajectory
        assert traj is not None
        end_z = traj.states[-1].pose.z
        assert abs(end_z - 5.0) < 0.5

    def test_optimize_computation_time(self) -> None:
        optimizer = MinimumSnapOptimizer()
        problem = self._make_problem()
        result = optimizer.optimize(problem)
        assert result.computation_time_ms >= 0
