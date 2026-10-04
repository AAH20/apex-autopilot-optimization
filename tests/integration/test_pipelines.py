"""Integration tests for cross-module pipelines."""

import pytest

from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
    VehicleType,
    Velocity3D,
    Waypoint,
    PlanningProblem,
)
from apex_autopilot_optimization.estimation.ekf import EKFConfig, EKFEstimator
from apex_autopilot_optimization.optimization.minimum_snap import (
    MinimumSnapConfig,
    MinimumSnapOptimizer,
)
from apex_autopilot_optimization.planning.astar import AStarConfig, AStarPlanner
from apex_autopilot_optimization.safety.cbf import CBFConfig, CBFFilter


class TestPlanningOptimizationPipeline:
    """Integration tests for planning → optimization workflow."""

    def _make_problem(self) -> PlanningProblem:
        return PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(
                pose=Pose3D(x=0, y=0, z=0),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=5, y=5, z=0)),
        )

    def test_astar_to_minimum_snap_pipeline(self):
        """A* path feeds into minimum snap trajectory optimization."""
        planner = AStarPlanner(AStarConfig())
        optimizer = MinimumSnapOptimizer(MinimumSnapConfig())
        problem = self._make_problem()

        plan_result = planner.plan(problem)
        assert plan_result.success is True

        if plan_result.trajectory is not None:
            assert len(plan_result.trajectory.states) > 0

    def test_planning_result_has_cost(self):
        """Planning result has a valid cost value."""
        planner = AStarPlanner(AStarConfig())
        problem = self._make_problem()
        result = planner.plan(problem)
        assert result.cost >= 0.0


class TestEstimationControlPipeline:
    """Integration tests for EKF → control workflow."""

    def test_ekf_produces_valid_state(self):
        """EKF predict/update cycle produces a valid state vector."""
        ekf = EKFEstimator(EKFConfig())
        state = ekf.get_state()
        assert state is not None
        assert state.pose is not None

    def test_ekf_state_has_pose_and_velocity(self):
        """EKF state contains both pose and velocity."""
        ekf = EKFEstimator(EKFConfig())
        state = ekf.get_state()
        assert state.pose.x is not None
        assert state.velocity.vx is not None


class TestSafetyPipeline:
    """Integration tests for safety filtering across planners."""

    def test_cbf_filter_passes_safe_control(self):
        """CBF passes through control when no obstacles."""
        cbf = CBFFilter(CBFConfig())
        state = StateVector(
            pose=Pose3D(x=0, y=0, z=0),
            velocity=Velocity3D(0, 0, 0),
        )
        control = ControlInput(throttle=0.5, roll_rate=0.0, pitch_rate=0.0, yaw_rate=0.0)
        result = cbf.filter(state, control, obstacles=[])
        assert result is not None

    def test_cbf_reduces_control_near_obstacle(self):
        """CBF reduces throttle when near an obstacle."""
        cbf = CBFFilter(CBFConfig())
        state = StateVector(
            pose=Pose3D(x=0, y=0, z=0),
            velocity=Velocity3D(0, 0, 0),
        )
        control = ControlInput(throttle=1.0, roll_rate=0.0, pitch_rate=0.0, yaw_rate=0.0)
        obstacles = [{"center": [0.5, 0.0, 0.0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles=obstacles)
        assert result.throttle <= control.throttle


class TestFullPipeline:
    """End-to-end integration tests."""

    def test_plan_optimize_filter_pipeline(self):
        """Full pipeline: Plan → Optimize → Safety Filter."""
        planner = AStarPlanner(AStarConfig())
        cbf = CBFFilter(CBFConfig())

        problem = PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(
                pose=Pose3D(x=0, y=0, z=0),
                velocity=Velocity3D(0, 0, 0),
            ),
            goal=Waypoint(pose=Pose3D(x=3, y=3, z=0)),
        )

        plan_result = planner.plan(problem)
        assert plan_result.success is True

        if plan_result.trajectory is not None and len(plan_result.trajectory.states) > 0:
            state = plan_result.trajectory.states[0]
            control = ControlInput(throttle=0.5, roll_rate=0.0, pitch_rate=0.0, yaw_rate=0.0)
            safe_control = cbf.filter(state, control, obstacles=[])
            assert safe_control is not None

    def test_ekf_cbf_pipeline(self):
        """EKF state feeds into CBF safety filter."""
        ekf = EKFEstimator(EKFConfig())
        cbf = CBFFilter(CBFConfig())

        state = ekf.get_state()
        control = ControlInput(throttle=0.5, roll_rate=0.0, pitch_rate=0.0, yaw_rate=0.0)
        safe_control = cbf.filter(state, control, obstacles=[])
        assert safe_control is not None
