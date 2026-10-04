"""Tests for PRM (Probabilistic Roadmap) path planning algorithm."""

from __future__ import annotations

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
from apex_autopilot_optimization.planning.prm import PRMConfig, PRMPlanner


class TestPRMConfig:
    """Tests for PRMConfig."""

    def test_defaults(self) -> None:
        config = PRMConfig()
        assert config.num_samples == 100
        assert config.nearest_neighbors == 5
        assert config.max_iterations == 10

    def test_custom_values(self) -> None:
        config = PRMConfig(num_samples=200, nearest_neighbors=10, max_iterations=20)
        assert config.num_samples == 200
        assert config.nearest_neighbors == 10
        assert config.max_iterations == 20


class TestPRMPlanner:
    """Tests for PRMPlanner."""

    def _make_problem(
        self,
        start: tuple[float, float, float] = (0, 0, 0),
        goal: tuple[float, float, float] = (5, 5, 0),
    ) -> PlanningProblem:
        return PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(
                pose=Pose3D(x=start[0], y=start[1], z=start[2]),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=goal[0], y=goal[1], z=goal[2])),
        )

    def test_plan_simple_path(self) -> None:
        planner = PRMPlanner()
        problem = self._make_problem((0, 0, 0), (5, 5, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None
        assert len(result.trajectory.states) > 0

    def test_plan_with_obstacles(self) -> None:
        planner = PRMPlanner()
        problem = PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(
                pose=Pose3D(x=0, y=0, z=0),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=5, y=0, z=0)),
            obstacles=[{"type": "sphere", "center": [2.5, 0, 0], "radius": 1.0}],
        )
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None

    def test_plan_same_start_goal(self) -> None:
        planner = PRMPlanner()
        problem = self._make_problem((1, 1, 0), (1, 1, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None
        assert len(result.trajectory.states) == 1

    def test_plan_returns_cost(self) -> None:
        planner = PRMPlanner()
        problem = self._make_problem((0, 0, 0), (3, 4, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.cost > 0

    def test_plan_returns_computation_time(self) -> None:
        planner = PRMPlanner()
        problem = self._make_problem((0, 0, 0), (3, 3, 0))
        result = planner.plan(problem)
        assert result.computation_time_ms >= 0

    def test_plan_3d(self) -> None:
        planner = PRMPlanner()
        problem = self._make_problem((0, 0, 0), (3, 3, 3))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None

    def test_plan_with_custom_config(self) -> None:
        planner = PRMPlanner(config=PRMConfig(num_samples=200, nearest_neighbors=10))
        problem = self._make_problem((0, 0, 0), (10, 10, 0))
        result = planner.plan(problem)
        assert result.success

    def test_plan_long_distance(self) -> None:
        planner = PRMPlanner(config=PRMConfig(num_samples=200, nearest_neighbors=10))
        problem = self._make_problem((0, 0, 0), (20, 20, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None

    def test_plan_iterations_limited(self) -> None:
        planner = PRMPlanner(config=PRMConfig(num_samples=20, max_iterations=5))
        problem = self._make_problem((0, 0, 0), (50, 50, 0))
        result = planner.plan(problem)
        # With limited samples, planner should still complete
        assert result.iterations > 0
