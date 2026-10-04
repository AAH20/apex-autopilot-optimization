"""Tests for core domain types."""

from __future__ import annotations

import numpy as np
import pytest

from apex_autopilot_optimization.core.types import (
    BottleneckReport,
    ComplexityClass,
    PlanningProblem,
    PlanningResult,
    Pose3D,
    StateVector,
    Trajectory,
    VehicleType,
    Velocity3D,
    Waypoint,
)


class TestPose3D:
    """Tests for Pose3D dataclass."""

    def test_position_returns_numpy_array(self) -> None:
        pose = Pose3D(x=1.0, y=2.0, z=3.0)
        pos = pose.position()
        assert isinstance(pos, np.ndarray)
        np.testing.assert_array_equal(pos, np.array([1.0, 2.0, 3.0]))

    def test_distance_to_zero_for_same_pose(self) -> None:
        pose = Pose3D(x=1.0, y=2.0, z=3.0)
        assert pose.distance_to(pose) == pytest.approx(0.0)

    def test_distance_to_correct_euclidean(self) -> None:
        p1 = Pose3D(x=0.0, y=0.0, z=0.0)
        p2 = Pose3D(x=3.0, y=4.0, z=0.0)
        assert p1.distance_to(p2) == pytest.approx(5.0)

    def test_distance_to_3d(self) -> None:
        p1 = Pose3D(x=0.0, y=0.0, z=0.0)
        p2 = Pose3D(x=1.0, y=1.0, z=1.0)
        assert p1.distance_to(p2) == pytest.approx(np.sqrt(3.0))

    def test_default_orientation_is_zero(self) -> None:
        pose = Pose3D(x=0.0, y=0.0, z=0.0)
        assert pose.roll == 0.0
        assert pose.pitch == 0.0
        assert pose.yaw == 0.0


class TestVelocity3D:
    """Tests for Velocity3D dataclass."""

    def test_magnitude_zero(self) -> None:
        vel = Velocity3D(vx=0.0, vy=0.0, vz=0.0)
        assert vel.magnitude() == pytest.approx(0.0)

    def test_magnitude_correct(self) -> None:
        vel = Velocity3D(vx=3.0, vy=4.0, vz=0.0)
        assert vel.magnitude() == pytest.approx(5.0)

    def test_magnitude_3d(self) -> None:
        vel = Velocity3D(vx=1.0, vy=2.0, vz=2.0)
        assert vel.magnitude() == pytest.approx(3.0)


class TestStateVector:
    """Tests for StateVector dataclass."""

    def test_to_array_flattens_correctly(self) -> None:
        state = StateVector(
            pose=Pose3D(x=1.0, y=2.0, z=3.0, roll=0.1, pitch=0.2, yaw=0.3),
            velocity=Velocity3D(vx=4.0, vy=5.0, vz=6.0, vroll=0.4, vpitch=0.5, vyaw=0.6),
        )
        arr = state.to_array()
        assert len(arr) == 12
        np.testing.assert_array_almost_equal(
            arr,
            [1.0, 2.0, 3.0, 0.1, 0.2, 0.3, 4.0, 5.0, 6.0, 0.4, 0.5, 0.6],
        )

    def test_to_array_dtype(self) -> None:
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        assert state.to_array().dtype == np.float64


class TestTrajectory:
    """Tests for Trajectory dataclass."""

    def test_duration_empty(self) -> None:
        traj = Trajectory(
            states=[], controls=[], timestamps=np.array([]), vehicle_type=VehicleType.UAV_MULTIROTOR
        )
        assert traj.duration() == 0.0

    def test_duration_single_point(self) -> None:
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        traj = Trajectory(
            states=[state],
            controls=[],
            timestamps=np.array([0.0]),
            vehicle_type=VehicleType.UAV_MULTIROTOR,
        )
        assert traj.duration() == 0.0

    def test_duration_correct(self) -> None:
        s1 = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        s2 = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        traj = Trajectory(
            states=[s1, s2],
            controls=[],
            timestamps=np.array([0.0, 5.0]),
            vehicle_type=VehicleType.UAV_MULTIROTOR,
        )
        assert traj.duration() == pytest.approx(5.0)

    def test_length_empty(self) -> None:
        traj = Trajectory(
            states=[], controls=[], timestamps=np.array([]), vehicle_type=VehicleType.UAV_MULTIROTOR
        )
        assert traj.length() == 0.0

    def test_length_two_points(self) -> None:
        s1 = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        s2 = StateVector(pose=Pose3D(3, 4, 0), velocity=Velocity3D(0, 0, 0))
        traj = Trajectory(
            states=[s1, s2],
            controls=[],
            timestamps=np.array([0.0, 1.0]),
            vehicle_type=VehicleType.UAV_MULTIROTOR,
        )
        assert traj.length() == pytest.approx(5.0)

    def test_length_three_points(self) -> None:
        s1 = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        s2 = StateVector(pose=Pose3D(1, 0, 0), velocity=Velocity3D(0, 0, 0))
        s3 = StateVector(pose=Pose3D(1, 1, 0), velocity=Velocity3D(0, 0, 0))
        traj = Trajectory(
            states=[s1, s2, s3],
            controls=[],
            timestamps=np.array([0.0, 1.0, 2.0]),
            vehicle_type=VehicleType.UAV_MULTIROTOR,
        )
        assert traj.length() == pytest.approx(2.0)


class TestPlanningProblem:
    """Tests for PlanningProblem dataclass."""

    def test_defaults(self) -> None:
        problem = PlanningProblem(
            vehicle_type=VehicleType.UAV_MULTIROTOR,
            start=StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0)),
            goal=Waypoint(pose=Pose3D(1, 1, 1)),
        )
        assert problem.waypoints == []
        assert problem.obstacles == []
        assert problem.constraints == []
        assert problem.objectives == []
        assert problem.time_horizon_s == 60.0
        assert problem.resolution_m == 1.0


class TestPlanningResult:
    """Tests for PlanningResult dataclass."""

    def test_defaults(self) -> None:
        result = PlanningResult(success=True)
        assert result.trajectory is None
        assert result.computation_time_ms == 0.0
        assert result.iterations == 0
        assert result.cost == 0.0
        assert result.message == ""


class TestBottleneckReport:
    """Tests for BottleneckReport dataclass."""

    def test_creation(self) -> None:
        report = BottleneckReport(
            description="Test bottleneck",
            severity="high",
            category="computational",
            complexity=ComplexityClass.NP_HARD,
        )
        assert report.description == "Test bottleneck"
        assert report.severity == "high"
        assert report.complexity == ComplexityClass.NP_HARD


class TestVehicleType:
    """Tests for VehicleType enum."""

    def test_all_types_exist(self) -> None:
        assert len(VehicleType) == 6

    def test_specific_types(self) -> None:
        assert VehicleType.UAV_FIXED_WING is not None
        assert VehicleType.UAV_MULTIROTOR is not None
        assert VehicleType.GROUND_VEHICLE_ACKERMANN is not None


class TestComplexityClass:
    """Tests for ComplexityClass enum."""

    def test_all_classes_exist(self) -> None:
        assert len(ComplexityClass) == 7

    def test_specific_classes(self) -> None:
        assert ComplexityClass.P is not None
        assert ComplexityClass.NP_HARD is not None
        assert ComplexityClass.NP_COMPLETE is not None
