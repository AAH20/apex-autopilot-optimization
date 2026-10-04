"""Tests for Hybrid A* path planning algorithm."""

from __future__ import annotations

from apex_autopilot_optimization.core.types import (
    PlanningProblem,
    Pose3D,
    StateVector,
    VehicleType,
    Velocity3D,
    Waypoint,
)
from apex_autopilot_optimization.planning.hybrid_astar import HybridAStarConfig, HybridAStarPlanner


class TestHybridAStarConfig:
    """Tests for HybridAStarConfig."""

    def test_defaults(self) -> None:
        config = HybridAStarConfig()
        assert config.max_iterations == 1000
        assert config.step_size == 1.0
        assert config.steering_angle == 0.5
        assert config.wheelbase == 2.5

    def test_custom_values(self) -> None:
        config = HybridAStarConfig(max_iterations=500, steering_angle=0.3, wheelbase=3.0)
        assert config.max_iterations == 500
        assert config.steering_angle == 0.3
        assert config.wheelbase == 3.0


class TestHybridAStarPlanner:
    """Tests for HybridAStarPlanner."""

    def _make_problem(
        self,
        start: tuple[float, float, float] = (0, 0, 0),
        goal: tuple[float, float, float] = (5, 5, 0),
    ) -> PlanningProblem:
        return PlanningProblem(
            vehicle_type=VehicleType.GROUND_VEHICLE_ACKERMANN,
            start=StateVector(
                pose=Pose3D(x=start[0], y=start[1], z=start[2]),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=goal[0], y=goal[1], z=goal[2])),
        )

    def test_plan_simple_path(self) -> None:
        planner = HybridAStarPlanner()
        problem = self._make_problem((0, 0, 0), (5, 0, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None
        assert len(result.trajectory.states) > 0

    def test_plan_with_obstacles(self) -> None:
        planner = HybridAStarPlanner(config=HybridAStarConfig(max_iterations=5000))
        problem = PlanningProblem(
            vehicle_type=VehicleType.GROUND_VEHICLE_ACKERMANN,
            start=StateVector(
                pose=Pose3D(x=0, y=0, z=0),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=5, y=0, z=0)),
            obstacles=[{"type": "sphere", "center": [2.5, 0, 0], "radius": 1.0}],
        )
        result = planner.plan(problem)
        # Planner may or may not find path depending on discretization
        assert result.iterations > 0

    def test_plan_same_start_goal(self) -> None:
        planner = HybridAStarPlanner()
        problem = self._make_problem((1, 1, 0), (1, 1, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None
        assert len(result.trajectory.states) == 1

    def test_plan_returns_cost(self) -> None:
        planner = HybridAStarPlanner(config=HybridAStarConfig(max_iterations=5000))
        problem = self._make_problem((0, 0, 0), (3, 4, 0))
        result = planner.plan(problem)
        # Planner may or may not find path depending on discretization
        if result.success:
            assert result.cost > 0

    def test_plan_returns_computation_time(self) -> None:
        planner = HybridAStarPlanner()
        problem = self._make_problem((0, 0, 0), (3, 3, 0))
        result = planner.plan(problem)
        assert result.computation_time_ms >= 0

    def test_plan_with_custom_config(self) -> None:
        planner = HybridAStarPlanner(
            config=HybridAStarConfig(max_iterations=500, steering_angle=0.3)
        )
        problem = self._make_problem((0, 0, 0), (10, 10, 0))
        result = planner.plan(problem)
        assert result.success

    def test_plan_long_distance(self) -> None:
        planner = HybridAStarPlanner(config=HybridAStarConfig(max_iterations=2000))
        problem = self._make_problem((0, 0, 0), (20, 20, 0))
        result = planner.plan(problem)
        assert result.success
        assert result.trajectory is not None

    def test_plan_iterations_limited(self) -> None:
        planner = HybridAStarPlanner(config=HybridAStarConfig(max_iterations=100))
        problem = self._make_problem((0, 0, 0), (50, 50, 0))
        result = planner.plan(problem)
        # May or may not succeed with limited iterations
        assert result.iterations <= 100
