"""Tests for Control Barrier Function safety filter."""

from __future__ import annotations

import numpy as np
import pytest

from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.safety.cbf import CBFFilter, CBFConfig


class TestCBFConfig:
    """Tests for CBFConfig."""

    def test_defaults(self) -> None:
        config = CBFConfig()
        assert config.alpha == 1.0
        assert config.beta == 1.0
        assert config.safety_margin == 0.5
        assert config.max_correction == 10.0

    def test_custom_values(self) -> None:
        config = CBFConfig(alpha=2.0, safety_margin=1.0)
        assert config.alpha == 2.0
        assert config.safety_margin == 1.0


class TestCBFFilter:
    """Tests for CBFFilter."""

    def _make_state(self, x: float = 0, y: float = 0, z: float = 0) -> StateVector:
        return StateVector(
            pose=Pose3D(x=x, y=y, z=z),
            velocity=Velocity3D(0, 0, 0),
        )

    def test_filter_safe_state(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(0, 0, 0)
        control = ControlInput(throttle=0.5)
        obstacles: list[dict] = []
        result = cbf.filter(state, control, obstacles)
        assert result is not None
        # Safe state should pass through with minimal correction
        assert result.throttle == pytest.approx(0.5, abs=0.1)

    def test_filter_near_obstacle(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(1.0, 0, 0)
        control = ControlInput(throttle=0.5)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result is not None
        # Near obstacle should apply correction
        assert result.throttle != pytest.approx(0.5, abs=0.1)

    def test_filter_collision_imminent(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(1.5, 0, 0)
        control = ControlInput(throttle=1.0)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result is not None
        # Collision imminent should apply strong correction
        assert result.throttle < 0.5

    def test_filter_no_obstacles(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(0, 0, 0)
        control = ControlInput(throttle=0.8)
        obstacles: list[dict] = []
        result = cbf.filter(state, control, obstacles)
        assert result is not None
        assert result.throttle == pytest.approx(0.8, abs=0.01)

    def test_filter_multiple_obstacles(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(1.0, 1.0, 0)
        control = ControlInput(throttle=0.5)
        obstacles = [
            {"type": "sphere", "center": [2.0, 1.0, 0], "radius": 1.0},
            {"type": "sphere", "center": [1.0, 2.0, 0], "radius": 1.0},
        ]
        result = cbf.filter(state, control, obstacles)
        assert result is not None

    def test_filter_returns_control_input(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(0, 0, 0)
        control = ControlInput(throttle=0.5, roll_rate=0.1, pitch_rate=0.2, yaw_rate=0.3)
        obstacles: list[dict] = []
        result = cbf.filter(state, control, obstacles)
        assert isinstance(result, ControlInput)

    def test_filter_with_custom_config(self) -> None:
        cbf = CBFFilter(config=CBFConfig(alpha=2.0, safety_margin=1.0))
        state = self._make_state(1.0, 0, 0)
        control = ControlInput(throttle=0.5)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result is not None

    def test_filter_3d_obstacle(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(1.0, 0, 1.0)
        control = ControlInput(throttle=0.5)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 1.0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result is not None

    def test_filter_boundary_case(self) -> None:
        cbf = CBFFilter()
        state = self._make_state(1.5, 0, 0)
        control = ControlInput(throttle=0.0)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result is not None
        # At boundary with zero throttle, should still be safe
        assert result.throttle >= 0.0
