"""Adversarial tests for the Control Barrier Function (CBF) safety filter.

Property-based tests (Hypothesis) assert safety invariants hold across a wide
range of inputs; directed tests pin specific edge cases (NaN, inf, boundary,
max_correction clamping, malicious obstacle specs).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from hypothesis import HealthCheck

from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.safety.cbf import CBFConfig, CBFFilter
from apex_autopilot_optimization.chaos.probes import (
    cbf_correction_when_unsafe,
    cbf_output_valid,
    cbf_throttle_monotonic,
)

_FINITE = st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False)
_ADVERSARIAL = st.one_of(
    _FINITE,
    st.just(0.0),
    st.just(1e-12),
    st.just(-1e-12),
)

_VALID_SPHERE = st.fixed_dictionaries(
    {
        "type": st.just("sphere"),
        "center": st.lists(_ADVERSARIAL, min_size=3, max_size=3),
        "radius": st.floats(-10.0, 10.0, allow_nan=False, allow_infinity=False),
    }
)

_MALICIOUS_OBSTACLE = st.one_of(
    _VALID_SPHERE,
    st.just({"type": "box", "center": [0.0, 0.0, 0.0], "radius": 1.0}),  # wrong type
    st.just({}),                                                           # empty (no "type")
    st.just({"type": "sphere", "center": None, "radius": 1.0}),           # None center -> nan
)


def _min_distance(state: StateVector, obstacles: list[dict]) -> float:
    pos = np.array([state.pose.x, state.pose.y, state.pose.z], dtype=np.float64)
    min_dist = float("inf")
    for obs in obstacles:
        if obs.get("type") != "sphere":
            continue
        try:
            center = np.array(obs["center"], dtype=np.float64)
            radius = float(obs["radius"])
        except Exception:
            continue
        dist = float(np.linalg.norm(pos - center) - radius)
        min_dist = min(min_dist, dist)
    return min_dist


# --------------------------------------------------------------------------- #
# Property-based: invariants must hold for all generated inputs
# --------------------------------------------------------------------------- #

@settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    x=_ADVERSARIAL,
    y=_ADVERSARIAL,
    z=_ADVERSARIAL,
    throttle=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
    margin=st.floats(0.0, 5.0, allow_nan=False, allow_infinity=False),
    alpha=st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False),
    max_corr=st.floats(0.1, 100.0, allow_nan=False, allow_infinity=False),
    obstacles=st.lists(_MALICIOUS_OBSTACLE, min_size=0, max_size=4),
)
def test_never_raises_returns_control_input(
    x, y, z, throttle, margin, alpha, max_corr, obstacles
) -> None:
    """Any input (incl. NaN/inf coords, malicious obstacles) must not crash."""
    cbf = CBFFilter(
        config=CBFConfig(alpha=alpha, safety_margin=margin, max_correction=max_corr)
    )
    state = StateVector(pose=Pose3D(x=x, y=y, z=z), velocity=Velocity3D(0, 0, 0))
    control = ControlInput(throttle=throttle)
    result = cbf.filter(state, control, obstacles)
    assert isinstance(result, ControlInput)


@settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    x=_FINITE,
    y=_FINITE,
    z=_FINITE,
    throttle=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
    margin=st.floats(0.0, 5.0, allow_nan=False, allow_infinity=False),
    alpha=st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False),
    max_corr=st.floats(0.1, 100.0, allow_nan=False, allow_infinity=False),
    obstacles=st.lists(_VALID_SPHERE, min_size=0, max_size=4),
)
def test_throttle_never_increases_or_goes_negative(
    x, y, z, throttle, margin, alpha, max_corr, obstacles
) -> None:
    """Correction only reduces throttle; output never negative; rates preserved."""
    cbf = CBFFilter(
        config=CBFConfig(alpha=alpha, safety_margin=margin, max_correction=max_corr)
    )
    state = StateVector(pose=Pose3D(x=x, y=y, z=z), velocity=Velocity3D(0, 0, 0))
    control = ControlInput(throttle=throttle)
    result = cbf.filter(state, control, obstacles)
    assert cbf_throttle_monotonic(control, result) == [], cbf_throttle_monotonic(
        control, result
    )
    assert cbf_output_valid(control, result) == [], cbf_output_valid(control, result)


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    x=_FINITE,
    y=_FINITE,
    z=_FINITE,
    throttle=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
    margin=st.floats(0.0, 5.0, allow_nan=False, allow_infinity=False),
    alpha=st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False),
    max_corr=st.floats(0.1, 100.0, allow_nan=False, allow_infinity=False),
)
def test_safe_state_passthrough(x, y, z, throttle, margin, alpha, max_corr) -> None:
    """Outside the safety margin, control passes through unchanged."""
    cbf = CBFFilter(
        config=CBFConfig(alpha=alpha, safety_margin=margin, max_correction=max_corr)
    )
    # Place obstacles far away so h > 0.
    obstacles = [
        {"type": "sphere", "center": [x + 100.0, y + 100.0, z + 100.0], "radius": 1.0}
    ]
    state = StateVector(pose=Pose3D(x=x, y=y, z=z), velocity=Velocity3D(0, 0, 0))
    control = ControlInput(throttle=throttle)
    result = cbf.filter(state, control, obstacles)
    assert result.throttle == pytest.approx(throttle, abs=1e-9)
    assert result.throttle >= 0.0


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    x=_FINITE,
    y=_FINITE,
    z=_FINITE,
    throttle=st.floats(0.01, 1.0, allow_nan=False, allow_infinity=False),
    margin=st.floats(0.1, 5.0, allow_nan=False, allow_infinity=False),
    alpha=st.floats(0.1, 10.0, allow_nan=False, allow_infinity=False),
    max_corr=st.floats(0.1, 100.0, allow_nan=False, allow_infinity=False),
)
def test_unsafe_state_reduces_throttle(x, y, z, throttle, margin, alpha, max_corr) -> None:
    """Inside the safety margin, throttle must be reduced."""
    cbf = CBFFilter(
        config=CBFConfig(alpha=alpha, safety_margin=margin, max_correction=max_corr)
    )
    # Obstacle centered on the vehicle: distance = -radius <= margin -> unsafe.
    obstacles = [{"type": "sphere", "center": [x, y, z], "radius": 1.0}]
    state = StateVector(pose=Pose3D(x=x, y=y, z=z), velocity=Velocity3D(0, 0, 0))
    control = ControlInput(throttle=throttle)
    result = cbf.filter(state, control, obstacles)
    min_dist = _min_distance(state, obstacles)
    violations = cbf_correction_when_unsafe(min_dist, margin, control, result)
    assert violations == [], violations


# --------------------------------------------------------------------------- #
# Directed edge cases
# --------------------------------------------------------------------------- #

class TestDirectedEdgeCases:
    def test_nan_state_coords_do_not_crash(self) -> None:
        cbf = CBFFilter()
        state = StateVector(
            pose=Pose3D(x=float("nan"), y=float("nan"), z=float("nan")),
            velocity=Velocity3D(0, 0, 0),
        )
        control = ControlInput(throttle=0.5)
        result = cbf.filter(state, control, [])
        assert isinstance(result, ControlInput)

    def test_inf_obstacle_center_does_not_crash(self) -> None:
        cbf = CBFFilter()
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        obstacles = [{"type": "sphere", "center": [float("inf"), 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert isinstance(result, ControlInput)

    def test_negative_radius_does_not_crash(self) -> None:
        cbf = CBFFilter()
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": -1.0}]
        result = cbf.filter(state, control, obstacles)
        assert isinstance(result, ControlInput)

    def test_missing_keys_raise_keyerror(self) -> None:
        """Malformed sphere obstacles (missing ``center``/``radius``) crash the filter.

        This documents a real vulnerability: :meth:`CBFFilter._min_distance_to_obstacles`
        indexes ``obs["center"]`` / ``obs["radius"]`` directly, so a malformed
        obstacle spec propagates a ``KeyError`` instead of degrading safely.
        """
        cbf = CBFFilter()
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        for bad in [{"type": "sphere"}, {"type": "sphere", "radius": 1.0}]:
            with pytest.raises(KeyError):
                cbf.filter(state, control, [bad])

    def test_boundary_h_equals_zero_reduces_throttle(self) -> None:
        """h == 0 (dist == margin) is treated as unsafe and reduces throttle."""
        cbf = CBFFilter(config=CBFConfig(safety_margin=0.5, max_correction=10.0))
        state = StateVector(pose=Pose3D(1.5, 0, 0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        # center [2,0,0] radius 1.0 -> dist = 0.5 == margin -> h == 0 -> unsafe.
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result.throttle < control.throttle

    def test_max_correction_clamped_throttle_floor_zero(self) -> None:
        """Deeply negative h clamps correction to max_correction; throttle floored at 0."""
        cbf = CBFFilter(config=CBFConfig(alpha=1.0, safety_margin=0.5, max_correction=0.1))
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        # obstacle centered on vehicle, radius 10 -> dist=-10, h=-10.5, correction=10.5 clamped to 0.1
        obstacles = [{"type": "sphere", "center": [0.0, 0.0, 0.0], "radius": 10.0}]
        result = cbf.filter(state, control, obstacles)
        assert result.throttle == pytest.approx(max(0.0, 0.5 - 0.1), abs=1e-9)

    def test_zero_throttle_stays_zero(self) -> None:
        cbf = CBFFilter()
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.0)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result.throttle == 0.0

    def test_rates_and_timestamp_preserved(self) -> None:
        cbf = CBFFilter()
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5, roll_rate=0.1, pitch_rate=0.2, yaw_rate=0.3, timestamp=123.0)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = cbf.filter(state, control, obstacles)
        assert result.roll_rate == 0.1
        assert result.pitch_rate == 0.2
        assert result.yaw_rate == 0.3
        assert result.timestamp == 123.0
