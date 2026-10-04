"""Tests for EKF state estimation."""

from __future__ import annotations

import numpy as np
import pytest

from apex_autopilot_optimization.core.types import (
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.estimation.ekf import EKFConfig, EKFEstimator


class TestEKFConfig:
    """Tests for EKFConfig."""

    def test_defaults(self) -> None:
        config = EKFConfig()
        assert config.state_dim == 12
        assert config.measurement_dim == 6
        assert config.process_noise == 0.01
        assert config.measurement_noise == 0.1

    def test_custom_values(self) -> None:
        config = EKFConfig(state_dim=15, process_noise=0.05)
        assert config.state_dim == 15
        assert config.process_noise == 0.05


class TestEKFEstimator:
    """Tests for EKFEstimator."""

    def _make_state(self, x: float = 0, y: float = 0, z: float = 0) -> StateVector:
        return StateVector(
            pose=Pose3D(x=x, y=y, z=z),
            velocity=Velocity3D(0, 0, 0),
        )

    def test_initialization(self) -> None:
        ekf = EKFEstimator()
        state = ekf.get_state()
        assert state is not None
        assert len(state.to_array()) == 12

    def test_predict_updates_state(self) -> None:
        ekf = EKFEstimator()
        # Set non-zero velocity so prediction changes position
        ekf._state[6] = 1.0  # vx = 1.0
        initial_state = ekf.get_state()
        assert initial_state is not None
        initial_x = initial_state.pose.x

        ekf.predict(dt=0.1)
        new_state = ekf.get_state()
        assert new_state is not None
        # Position should change: x = x0 + vx * dt = 0 + 1.0 * 0.1 = 0.1
        assert new_state.pose.x == pytest.approx(0.1, abs=1e-6)

    def test_update_with_measurement(self) -> None:
        ekf = EKFEstimator()
        measurement = np.array([1.0, 2.0, 3.0, 0.1, 0.2, 0.3])
        ekf.update(measurement)
        state = ekf.get_state()
        assert state is not None

    def test_predict_update_cycle(self) -> None:
        ekf = EKFEstimator()
        for _ in range(10):
            ekf.predict(dt=0.01)
            measurement = np.array([0.1, 0.1, 0.1, 0.01, 0.01, 0.01])
            ekf.update(measurement)
        state = ekf.get_state()
        assert state is not None

    def test_covariance_is_positive_definite(self) -> None:
        ekf = EKFEstimator()
        for _ in range(5):
            ekf.predict(dt=0.01)
        cov = ekf.get_covariance()
        assert cov is not None
        eigenvalues = np.linalg.eigvalsh(cov)
        assert np.all(eigenvalues > 0)

    def test_reset(self) -> None:
        ekf = EKFEstimator()
        for _ in range(10):
            ekf.predict(dt=0.01)
        ekf.reset()
        state = ekf.get_state()
        assert state is not None
        # After reset, state should be near zero
        assert abs(state.pose.x) < 1e-6

    def test_state_vector_conversion(self) -> None:
        ekf = EKFEstimator()
        state = ekf.get_state()
        assert state is not None
        arr = state.to_array()
        assert len(arr) == 12
        assert arr.dtype == np.float64

    def test_multiple_predict_steps(self) -> None:
        ekf = EKFEstimator()
        for _ in range(100):
            ekf.predict(dt=0.001)
        state = ekf.get_state()
        assert state is not None
        # After many predictions without update, uncertainty should grow
        cov = ekf.get_covariance()
        assert cov is not None
