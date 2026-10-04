"""Tests for A* path planning algorithm."""

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
from apex_autopilot_optimization.planning.astar import AStarPlanner, AStarConfig


class TestAStarConfig:
    """Tests for AStarConfig dataclass."""

    def test_defaults(self) -> None:
        config = AStarConfig()
        assert config.resolution_m == 1.0
        assert config.max_iterations == 10000
        assert config.diagonal_movement is True
        assert config.heuristic_weight == 1.0

    def test_custom_values(self) -> None:
        config = AStarConfig(resolution_m=0.5, max_iterations=500, diagonal_movement=False)
        assert config.resolution_m == 0.5
        assert config.max_iterations == 500
        assert config.diagonal_movement is False


class TestAStarPlanner:
    """Tests for AStarPlanner."""

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

    def test_plan_simple_straight_line(self) -> None:
        planner = AStarPlanner()
        problem = self._make_problem((0, 0, 0), (3, 0, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None
        assert len(result.trajectory.states) > 0

    def test_plan_diagonal(self) -> None:
        planner = AStarPlanner()
        problem = self._make_problem((0, 0, 0), (3, 3, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None

    def test_plan_with_obstacles(self) -> None:
        planner = AStarPlanner()
        problem = self._make_problem((0, 0, 0), (5, 0, 0))
        problem.obstacles.append({"type": "sphere", "center": [2.5, 0, 0], "radius": 1.0})
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None

    def test_plan_same_start_goal(self) -> None:
        planner = AStarPlanner()
        problem = self._make_problem((1, 1, 0), (1, 1, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None
        assert len(result.trajectory.states) == 1

    def test_plan_returns_cost(self) -> None:
        planner = AStarPlanner()
        problem = self._make_problem((0, 0, 0), (3, 4, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.cost > 0

    def test_plan_returns_computation_time(self) -> None:
        planner = AStarPlanner()
        problem = self._make_problem((0, 0, 0), (3, 3, 0))
        result = planner.plan(problem)
        assert result.computation_time_ms >= 0

    def test_plan_with_2d_grid(self) -> None:
        planner = AStarPlanner(config=AStarConfig(resolution_m=1.0))
        problem = self._make_problem((0, 0, 0), (10, 10, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.iterations > 0

    def test_plan_no_diagonal(self) -> None:
        planner = AStarPlanner(config=AStarConfig(diagonal_movement=False))
        problem = self._make_problem((0, 0, 0), (3, 3, 0))
        result = planner.plan(problem)
        assert result.success

    def test_plan_3d(self) -> None:
        planner = AStarPlanner()
        problem = self._make_problem((0, 0, 0), (3, 3, 3))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None
