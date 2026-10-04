"""Tests for Model Predictive Control."""

from __future__ import annotations

from apex_autopilot_optimization.control.mpc import MPCConfig, MPCController
from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
    Velocity3D,
)


class TestMPCConfig:
    """Tests for MPCConfig."""

    def test_defaults(self) -> None:
        config = MPCConfig()
        assert config.horizon == 10
        assert config.dt == 0.1
        assert config.max_iterations == 100
        assert config.convergence_threshold == 1e-4

    def test_custom_values(self) -> None:
        config = MPCConfig(horizon=20, dt=0.05, max_iterations=200)
        assert config.horizon == 20
        assert config.dt == 0.05
        assert config.max_iterations == 200


class TestMPCController:
    """Tests for MPCController."""

    def _make_state(self, x: float = 0, y: float = 0, z: float = 0) -> StateVector:
        return StateVector(
            pose=Pose3D(x=x, y=y, z=z),
            velocity=Velocity3D(0, 0, 0),
        )

    def test_compute_control(self) -> None:
        mpc = MPCController()
        state = self._make_state(0, 0, 0)
        target = self._make_state(5, 5, 0)
        control = mpc.compute_control(state, target)
        assert isinstance(control, ControlInput)

    def test_compute_control_returns_reasonable_values(self) -> None:
        mpc = MPCController()
        state = self._make_state(0, 0, 0)
        target = self._make_state(5, 5, 0)
        control = mpc.compute_control(state, target)
        # Control should be bounded
        assert abs(control.throttle) <= 10.0
        assert abs(control.roll_rate) <= 10.0
        assert abs(control.pitch_rate) <= 10.0
        assert abs(control.yaw_rate) <= 10.0

    def test_compute_control_same_state(self) -> None:
        mpc = MPCController()
        state = self._make_state(5, 5, 0)
        target = self._make_state(5, 5, 0)
        control = mpc.compute_control(state, target)
        # Same state should produce near-zero control
        assert abs(control.throttle) < 1.0

    def test_compute_control_long_distance(self) -> None:
        mpc = MPCController()
        state = self._make_state(0, 0, 0)
        target = self._make_state(100, 100, 0)
        control = mpc.compute_control(state, target)
        assert isinstance(control, ControlInput)

    def test_compute_control_3d(self) -> None:
        mpc = MPCController()
        state = self._make_state(0, 0, 0)
        target = self._make_state(10, 10, 10)
        control = mpc.compute_control(state, target)
        assert isinstance(control, ControlInput)

    def test_compute_control_with_custom_config(self) -> None:
        mpc = MPCController(config=MPCConfig(horizon=5, dt=0.2))
        state = self._make_state(0, 0, 0)
        target = self._make_state(5, 5, 0)
        control = mpc.compute_control(state, target)
        assert isinstance(control, ControlInput)

    def test_compute_control_negative_direction(self) -> None:
        mpc = MPCController()
        state = self._make_state(10, 10, 0)
        target = self._make_state(0, 0, 0)
        control = mpc.compute_control(state, target)
        assert isinstance(control, ControlInput)

    def test_compute_control_with_velocity(self) -> None:
        mpc = MPCController()
        state = StateVector(
            pose=Pose3D(x=0, y=0, z=0),
            velocity=Velocity3D(vx=1, vy=1, vz=0),
        )
        target = self._make_state(5, 5, 0)
        control = mpc.compute_control(state, target)
        assert isinstance(control, ControlInput)
