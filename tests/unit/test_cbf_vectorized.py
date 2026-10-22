"""Tests for the vectorized CBF safety filter.

Covers: basic pass-through, obstacle avoidance, batch processing equivalence,
adversarial edge cases (NaN coordinates, missing keys, empty obstacles),
and performance scaling with obstacle count.
"""

from __future__ import annotations

from typing import Any

import pytest

from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.safety.cbf import CBFConfig, CBFFilter

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _state(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> StateVector:
    return StateVector(
        pose=Pose3D(x=x, y=y, z=z),
        velocity=Velocity3D(0, 0, 0),
        timestamp=0.0,
    )


def _control(throttle: float = 1.0) -> ControlInput:
    return ControlInput(
        throttle=throttle,
        roll_rate=0.0,
        pitch_rate=0.0,
        yaw_rate=0.0,
        timestamp=0.0,
    )


def _sphere(center: tuple[float, float, float], radius: float) -> dict[str, Any]:
    return {"type": "sphere", "center": list(center), "radius": radius}


# --------------------------------------------------------------------------- #
# Basic behavior
# --------------------------------------------------------------------------- #


def test_no_obstacles_passes_through() -> None:
    f = CBFFilter()
    s = _state()
    c = _control()
    assert f.filter(s, c, []) is c


def test_safe_distance_passes_through() -> None:
    f = CBFFilter()
    s = _state(0.0, 0.0, 0.0)
    c = _control(throttle=1.0)
    # Obstacle 20 m away, safety margin 0.5 → h = 19.5 > 0 → pass through
    obs = [_sphere((20.0, 0.0, 0.0), 1.0)]
    result = f.filter(s, c, obs)
    assert result.throttle == 1.0
    assert result.roll_rate == 0.0


def test_close_obstacle_reduces_throttle() -> None:
    f = CBFFilter()
    s = _state(0.0, 0.0, 0.0)
    c = _control(throttle=1.0)
    # Obstacle 0.3 m away, safety margin 0.5 → h = -0.2 → correction = 0.2
    obs = [_sphere((0.3, 0.0, 0.0), 0.0)]
    result = f.filter(s, c, obs)
    assert 0.0 <= result.throttle < 1.0
    assert result.throttle == pytest.approx(0.8, abs=1e-9)


def test_obstacle_inside_margin_triggers_correction() -> None:
    f = CBFFilter(CBFConfig(alpha=2.0, safety_margin=1.0))
    s = _state(0.0, 0.0, 0.0)
    c = _control(throttle=1.0)
    # Obstacle 0.5 m away, margin 1.0 → h = -0.5 → correction = 1.0 → throttle 0
    obs = [_sphere((0.5, 0.0, 0.0), 0.0)]
    result = f.filter(s, c, obs)
    assert result.throttle == 0.0


def test_non_sphere_obstacles_ignored() -> None:
    f = CBFFilter()
    s = _state()
    c = _control(throttle=1.0)
    obs = [{"type": "box", "center": [0.1, 0.0, 0.0], "size": [1, 1, 1]}]
    result = f.filter(s, c, obs)
    assert result.throttle == 1.0


# --------------------------------------------------------------------------- #
# Adversarial edge cases
# --------------------------------------------------------------------------- #


def test_missing_center_is_skipped() -> None:
    f = CBFFilter()
    s = _state()
    c = _control(throttle=1.0)
    obs = [{"type": "sphere", "radius": 1.0}]  # no "center"
    result = f.filter(s, c, obs)
    assert result.throttle == 1.0


def test_missing_radius_is_skipped() -> None:
    f = CBFFilter()
    s = _state()
    c = _control(throttle=1.0)
    obs = [{"type": "sphere", "center": [0.1, 0.0, 0.0]}]  # no "radius"
    result = f.filter(s, c, obs)
    assert result.throttle == 1.0


def test_nan_coordinates_do_not_crash() -> None:
    f = CBFFilter()
    s = _state()
    c = _control(throttle=1.0)
    obs = [_sphere((float("nan"), 0.0, 0.0), 1.0)]
    result = f.filter(s, c, obs)
    # NaN distance → min is NaN → h is NaN → h > 0 is False → correction applied
    # Should not crash; throttle should be reduced
    assert result.throttle <= 1.0


def test_inf_coordinates_do_not_crash() -> None:
    f = CBFFilter()
    s = _state()
    c = _control(throttle=1.0)
    obs = [_sphere((float("inf"), 0.0, 0.0), 1.0)]
    result = f.filter(s, c, obs)
    assert result.throttle <= 1.0


def test_negative_radius_treated_as_zero() -> None:
    f = CBFFilter()
    s = _state(0.0, 0.0, 0.0)
    c = _control(throttle=1.0)
    obs = [_sphere((0.3, 0.0, 0.0), -1.0)]
    result = f.filter(s, c, obs)
    # distance = 0.3 - (-1.0) = 1.3 → h = 0.8 > 0 → pass through
    assert result.throttle == 1.0


# --------------------------------------------------------------------------- #
# Batch processing equivalence
# --------------------------------------------------------------------------- #


def test_batch_filter_matches_single_filter() -> None:
    f = CBFFilter(CBFConfig(alpha=1.0, safety_margin=0.5))
    states = {
        0: _state(0.0, 0.0, 0.0),
        1: _state(10.0, 0.0, 0.0),
        2: _state(20.0, 0.0, 0.0),
    }
    controls = {0: _control(1.0), 1: _control(1.0), 2: _control(1.0)}
    # Vehicle 0 has a close obstacle; vehicles 1 and 2 are clear
    obstacles_per_vehicle = {
        0: [_sphere((0.3, 0.0, 0.0), 0.0)],
        1: [_sphere((30.0, 0.0, 0.0), 1.0)],
        2: [],
    }

    batch_result = f.batch_filter(states, controls, obstacles_per_vehicle)

    for vid in (0, 1, 2):
        single = f.filter(states[vid], controls[vid], obstacles_per_vehicle[vid])
        batched = batch_result[vid]
        assert batched.throttle == single.throttle, f"vehicle {vid} mismatch"
        assert batched.roll_rate == single.roll_rate
        assert batched.pitch_rate == single.pitch_rate
        assert batched.yaw_rate == single.yaw_rate


def test_batch_filter_empty_states() -> None:
    f = CBFFilter()
    result = f.batch_filter({}, {}, {})
    assert result == {}


def test_batch_filter_no_obstacles() -> None:
    f = CBFFilter()
    states = {0: _state(), 1: _state(5.0, 0.0, 0.0)}
    controls = {0: _control(1.0), 1: _control(0.5)}
    result = f.batch_filter(states, controls, {})
    assert result[0].throttle == 1.0
    assert result[1].throttle == 0.5


def test_batch_filter_vehicle_without_control_is_skipped() -> None:
    f = CBFFilter()
    states = {0: _state(), 1: _state(5.0, 0.0, 0.0)}
    controls = {0: _control(1.0)}  # vehicle 1 has no control
    result = f.batch_filter(states, controls, {})
    assert 0 in result
    assert 1 not in result


# --------------------------------------------------------------------------- #
# Performance scaling (obstacle count)
# --------------------------------------------------------------------------- #


def test_batch_filter_scales_with_obstacle_count() -> None:
    """Batch filter should handle 1000+ obstacles without crashing."""
    f = CBFFilter()
    states = {0: _state(0.0, 0.0, 0.0)}
    controls = {0: _control(1.0)}
    # 1000 obstacles, all far away from vehicle at origin
    obstacles = [_sphere((float(i + 100), 0.0, 0.0), 0.1) for i in range(1000)]
    result = f.filter(states[0], controls[0], obstacles)
    assert result.throttle == 1.0  # all far, no correction


# --------------------------------------------------------------------------- #
# Config edge cases
# --------------------------------------------------------------------------- #


def test_max_correction_clamped() -> None:
    f = CBFFilter(CBFConfig(alpha=100.0, max_correction=0.5, safety_margin=1.0))
    s = _state(0.0, 0.0, 0.0)
    c = _control(throttle=1.0)
    # Obstacle at 0.0 m, margin 1.0 → h = -1.0 → correction = 100 → clamped to 0.5
    obs = [_sphere((0.0, 0.0, 0.0), 0.0)]
    result = f.filter(s, c, obs)
    assert result.throttle == pytest.approx(0.5, abs=1e-9)


def test_zero_alpha_no_correction() -> None:
    f = CBFFilter(CBFConfig(alpha=0.0, safety_margin=1.0))
    s = _state(0.0, 0.0, 0.0)
    c = _control(throttle=1.0)
    obs = [_sphere((0.1, 0.0, 0.0), 0.0)]
    result = f.filter(s, c, obs)
    # h = -0.9, correction = 0 → throttle unchanged
    assert result.throttle == 1.0
