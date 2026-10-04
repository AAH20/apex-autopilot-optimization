"""Tests for serialization utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pytest
import yaml

from apex_autopilot_optimization.core.types import (
    ControlInput,
    OptimizationConstraint,
    OptimizationObjective,
    PlanningProblem,
    PlanningResult,
    Pose3D,
    StateVector,
    Trajectory,
    VehicleType,
    Velocity3D,
    Waypoint,
)
from apex_autopilot_optimization.serialization import (
    config_from_dict,
    config_to_dict,
    load_json,
    load_yaml,
    problem_from_dict,
    problem_to_dict,
    result_from_dict,
    result_to_dict,
    save_json,
    save_yaml,
    state_from_dict,
    state_to_dict,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_state() -> StateVector:
    return StateVector(
        pose=Pose3D(x=1.0, y=2.0, z=3.0, roll=0.1, pitch=0.2, yaw=0.3),
        velocity=Velocity3D(vx=4.0, vy=5.0, vz=6.0, vroll=0.4, vpitch=0.5, vyaw=0.6),
        timestamp=42.0,
        metadata={"source": "test", "quality": 0.95},
    )


def _make_waypoint() -> Waypoint:
    return Waypoint(
        pose=Pose3D(x=10.0, y=20.0, z=30.0, roll=0.0, pitch=0.0, yaw=1.57),
        speed=5.0,
        arrival_time=120.0,
        tolerance_m=2.0,
        hold_time_s=3.0,
    )


def _make_problem() -> PlanningProblem:
    return PlanningProblem(
        vehicle_type=VehicleType.UAV_MULTIROTOR,
        start=_make_state(),
        goal=_make_waypoint(),
        waypoints=[
            Waypoint(pose=Pose3D(x=5.0, y=5.0, z=5.0), speed=3.0),
        ],
        obstacles=[
            {"type": "sphere", "center": [5.0, 5.0, 5.0], "radius": 2.0},
        ],
        constraints=[
            OptimizationConstraint(
                name="max_speed",
                constraint_type="bound",
                upper_bound=15.0,
                params={"unit": "m/s"},
            ),
        ],
        objectives=[
            OptimizationObjective(
                name="min_time",
                weight=1.0,
                minimize=True,
            ),
        ],
        time_horizon_s=120.0,
        resolution_m=0.5,
    )


def _make_trajectory() -> Trajectory:
    return Trajectory(
        states=[
            StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0)),
            StateVector(pose=Pose3D(1, 1, 0), velocity=Velocity3D(1, 1, 0)),
            StateVector(pose=Pose3D(2, 2, 0), velocity=Velocity3D(1, 1, 0)),
        ],
        controls=[
            ControlInput(throttle=0.5, roll_rate=0.1, pitch_rate=0.05, yaw_rate=0.02),
            ControlInput(throttle=0.6, roll_rate=0.0, pitch_rate=0.0, yaw_rate=0.0),
        ],
        timestamps=np.array([0.0, 1.0, 2.0]),
        vehicle_type=VehicleType.UAV_MULTIROTOR,
    )


def _make_result() -> PlanningResult:
    return PlanningResult(
        success=True,
        trajectory=_make_trajectory(),
        computation_time_ms=150.5,
        iterations=500,
        cost=42.0,
        message="Path found",
        metadata={"algorithm": "RRT", "seed": 42},
    )


def _assert_result_equal(a: PlanningResult, b: PlanningResult) -> None:
    """Compare two PlanningResult objects, handling numpy arrays in Trajectory."""
    assert a.success == b.success
    assert a.computation_time_ms == b.computation_time_ms
    assert a.iterations == b.iterations
    assert a.cost == b.cost
    assert a.message == b.message
    assert a.metadata == b.metadata
    if a.trajectory is None or b.trajectory is None:
        assert a.trajectory is b.trajectory
        return
    assert len(a.trajectory.states) == len(b.trajectory.states)
    for sa, sb in zip(a.trajectory.states, b.trajectory.states):
        assert sa == sb
    assert len(a.trajectory.controls) == len(b.trajectory.controls)
    for ca, cb in zip(a.trajectory.controls, b.trajectory.controls):
        assert ca == cb
    np.testing.assert_array_equal(a.trajectory.timestamps, b.trajectory.timestamps)
    assert a.trajectory.vehicle_type == b.trajectory.vehicle_type


# ── StateVector round-trip ──────────────────────────────────────────────────


class TestStateVectorRoundTrip:
    """Tests for state_to_dict / state_from_dict."""

    def test_round_trip_basic(self) -> None:
        state = _make_state()
        data = state_to_dict(state)
        restored = state_from_dict(data)
        assert restored == state

    def test_round_trip_defaults(self) -> None:
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        data = state_to_dict(state)
        restored = state_from_dict(data)
        assert restored == state

    def test_dict_structure(self) -> None:
        state = _make_state()
        data = state_to_dict(state)
        assert data["pose"]["x"] == 1.0
        assert data["pose"]["y"] == 2.0
        assert data["pose"]["z"] == 3.0
        assert data["pose"]["roll"] == pytest.approx(0.1)
        assert data["pose"]["pitch"] == pytest.approx(0.2)
        assert data["pose"]["yaw"] == pytest.approx(0.3)
        assert data["velocity"]["vx"] == 4.0
        assert data["velocity"]["vy"] == 5.0
        assert data["velocity"]["vz"] == 6.0
        assert data["velocity"]["vroll"] == pytest.approx(0.4)
        assert data["velocity"]["vpitch"] == pytest.approx(0.5)
        assert data["velocity"]["vyaw"] == pytest.approx(0.6)
        assert data["timestamp"] == 42.0
        assert data["metadata"]["source"] == "test"

    def test_metadata_preserved(self) -> None:
        state = StateVector(
            pose=Pose3D(0, 0, 0),
            velocity=Velocity3D(0, 0, 0),
            metadata={"key": "value", "nested": {"a": 1}},
        )
        data = state_to_dict(state)
        restored = state_from_dict(data)
        assert restored.metadata == state.metadata

    def test_empty_metadata(self) -> None:
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        data = state_to_dict(state)
        restored = state_from_dict(data)
        assert restored.metadata == {}


# ── PlanningProblem round-trip ──────────────────────────────────────────────


class TestPlanningProblemRoundTrip:
    """Tests for problem_to_dict / problem_from_dict."""

    def test_round_trip_full(self) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        restored = problem_from_dict(data)
        assert restored == problem

    def test_round_trip_minimal(self) -> None:
        problem = PlanningProblem(
            vehicle_type=VehicleType.GROUND_VEHICLE_ACKERMANN,
            start=StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0)),
            goal=Waypoint(pose=Pose3D(1, 1, 1)),
        )
        data = problem_to_dict(problem)
        restored = problem_from_dict(data)
        assert restored == problem

    def test_vehicle_type_preserved(self) -> None:
        for vt in VehicleType:
            problem = PlanningProblem(
                vehicle_type=vt,
                start=StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0)),
                goal=Waypoint(pose=Pose3D(1, 1, 1)),
            )
            data = problem_to_dict(problem)
            restored = problem_from_dict(data)
            assert restored.vehicle_type == vt

    def test_waypoints_preserved(self) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        restored = problem_from_dict(data)
        assert len(restored.waypoints) == len(problem.waypoints)
        for orig, rest in zip(problem.waypoints, restored.waypoints):
            assert orig == rest

    def test_obstacles_preserved(self) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        restored = problem_from_dict(data)
        assert restored.obstacles == problem.obstacles

    def test_constraints_preserved(self) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        restored = problem_from_dict(data)
        assert len(restored.constraints) == len(problem.constraints)
        for orig, rest in zip(problem.constraints, restored.constraints):
            assert orig == rest

    def test_objectives_preserved(self) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        restored = problem_from_dict(data)
        assert len(restored.objectives) == len(problem.objectives)
        for orig, rest in zip(problem.objectives, restored.objectives):
            assert orig == rest

    def test_scalar_fields_preserved(self) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        restored = problem_from_dict(data)
        assert restored.time_horizon_s == problem.time_horizon_s
        assert restored.resolution_m == problem.resolution_m


# ── PlanningResult round-trip ───────────────────────────────────────────────


class TestPlanningResultRoundTrip:
    """Tests for result_to_dict / result_from_dict."""

    def test_round_trip_with_trajectory(self) -> None:
        result = _make_result()
        data = result_to_dict(result)
        restored = result_from_dict(data)
        _assert_result_equal(restored, result)

    def test_round_trip_without_trajectory(self) -> None:
        result = PlanningResult(success=False, message="No path found")
        data = result_to_dict(result)
        restored = result_from_dict(data)
        assert restored == result

    def test_trajectory_none_in_dict(self) -> None:
        result = PlanningResult(success=False)
        data = result_to_dict(result)
        assert data["trajectory"] is None

    def test_trajectory_fields_preserved(self) -> None:
        result = _make_result()
        data = result_to_dict(result)
        restored = result_from_dict(data)
        assert restored.trajectory is not None
        assert len(restored.trajectory.states) == 3
        assert len(restored.trajectory.controls) == 2
        np.testing.assert_array_almost_equal(
            restored.trajectory.timestamps, np.array([0.0, 1.0, 2.0])
        )
        assert restored.trajectory.vehicle_type == VehicleType.UAV_MULTIROTOR

    def test_result_metadata_preserved(self) -> None:
        result = _make_result()
        data = result_to_dict(result)
        restored = result_from_dict(data)
        assert restored.metadata == result.metadata

    def test_result_scalar_fields(self) -> None:
        result = _make_result()
        data = result_to_dict(result)
        restored = result_from_dict(data)
        assert restored.success is True
        assert restored.computation_time_ms == pytest.approx(150.5)
        assert restored.iterations == 500
        assert restored.cost == pytest.approx(42.0)
        assert restored.message == "Path found"


# ── Generic config serialization ─────────────────────────────────────────────


class Color(Enum):
    """Test enum."""

    RED = 1
    GREEN = 2
    BLUE = 3


@dataclass
class NestedConfig:
    """Test nested dataclass."""

    value: int = 0
    label: str = ""


@dataclass
class SimpleConfig:
    """Test dataclass for generic serialization."""

    name: str = ""
    count: int = 0
    ratio: float = 0.0
    enabled: bool = True
    color: Color = Color.RED
    tags: list[str] = field(default_factory=list)
    nested: Optional[NestedConfig] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TestConfigSerialization:
    """Tests for config_to_dict / config_from_dict."""

    def test_simple_round_trip(self) -> None:
        config = SimpleConfig(
            name="test",
            count=10,
            ratio=0.5,
            enabled=False,
            color=Color.BLUE,
            tags=["a", "b"],
            nested=NestedConfig(value=42, label="hello"),
            metadata={"key": "value"},
        )
        data = config_to_dict(config)
        restored = config_from_dict(data, SimpleConfig)
        assert restored == config

    def test_defaults_round_trip(self) -> None:
        config = SimpleConfig()
        data = config_to_dict(config)
        restored = config_from_dict(data, SimpleConfig)
        assert restored == config

    def test_enum_serialized_as_name(self) -> None:
        config = SimpleConfig(color=Color.GREEN)
        data = config_to_dict(config)
        assert data["color"] == "GREEN"

    def test_enum_deserialized_from_name(self) -> None:
        data = {"color": "BLUE"}
        restored = config_from_dict(data, SimpleConfig)
        assert restored.color == Color.BLUE

    def test_nested_dataclass(self) -> None:
        config = SimpleConfig(nested=NestedConfig(value=99, label="deep"))
        data = config_to_dict(config)
        restored = config_from_dict(data, SimpleConfig)
        assert restored.nested == NestedConfig(value=99, label="deep")

    def test_list_field(self) -> None:
        config = SimpleConfig(tags=["x", "y", "z"])
        data = config_to_dict(config)
        restored = config_from_dict(data, SimpleConfig)
        assert restored.tags == ["x", "y", "z"]

    def test_dict_field(self) -> None:
        config = SimpleConfig(metadata={"a": 1, "b": 2})
        data = config_to_dict(config)
        restored = config_from_dict(data, SimpleConfig)
        assert restored.metadata == {"a": 1, "b": 2}

    def test_non_dataclass_raises(self) -> None:
        with pytest.raises(TypeError):
            config_to_dict("not a dataclass")

    def test_non_dataclass_cls_raises(self) -> None:
        with pytest.raises(TypeError):
            config_from_dict({}, str)


# ── JSON file I/O ───────────────────────────────────────────────────────────


class TestJsonFileIO:
    """Tests for save_json / load_json."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        data = {"key": "value", "number": 42, "nested": {"a": 1}}
        path = str(tmp_path / "test.json")
        save_json(data, path)
        loaded = load_json(path)
        assert loaded == data

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        data = {"test": True}
        path = str(tmp_path / "sub" / "dir" / "test.json")
        save_json(data, path)
        assert Path(path).exists()

    def test_round_trip_problem(self, tmp_path: Path) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        path = str(tmp_path / "problem.json")
        save_json(data, path)
        loaded = load_json(path)
        restored = problem_from_dict(loaded)
        assert restored == problem

    def test_round_trip_result(self, tmp_path: Path) -> None:
        result = _make_result()
        data = result_to_dict(result)
        path = str(tmp_path / "result.json")
        save_json(data, path)
        loaded = load_json(path)
        restored = result_from_dict(loaded)
        _assert_result_equal(restored, result)

    def test_round_trip_state(self, tmp_path: Path) -> None:
        state = _make_state()
        data = state_to_dict(state)
        path = str(tmp_path / "state.json")
        save_json(data, path)
        loaded = load_json(path)
        restored = state_from_dict(loaded)
        assert restored == state

    def test_json_is_valid(self, tmp_path: Path) -> None:
        data = {"name": "test", "values": [1, 2, 3]}
        path = str(tmp_path / "valid.json")
        save_json(data, path)
        with open(path) as f:
            parsed = json.load(f)
        assert parsed == data


# ── YAML file I/O ───────────────────────────────────────────────────────────


class TestYamlFileIO:
    """Tests for save_yaml / load_yaml."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        data = {"key": "value", "number": 42, "nested": {"a": 1}}
        path = str(tmp_path / "test.yaml")
        save_yaml(data, path)
        loaded = load_yaml(path)
        assert loaded == data

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        data = {"test": True}
        path = str(tmp_path / "sub" / "dir" / "test.yaml")
        save_yaml(data, path)
        assert Path(path).exists()

    def test_round_trip_problem(self, tmp_path: Path) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)
        path = str(tmp_path / "problem.yaml")
        save_yaml(data, path)
        loaded = load_yaml(path)
        restored = problem_from_dict(loaded)
        assert restored == problem

    def test_round_trip_result(self, tmp_path: Path) -> None:
        result = _make_result()
        data = result_to_dict(result)
        path = str(tmp_path / "result.yaml")
        save_yaml(data, path)
        loaded = load_yaml(path)
        restored = result_from_dict(loaded)
        _assert_result_equal(restored, result)

    def test_round_trip_state(self, tmp_path: Path) -> None:
        state = _make_state()
        data = state_to_dict(state)
        path = str(tmp_path / "state.yaml")
        save_yaml(data, path)
        loaded = load_yaml(path)
        restored = state_from_dict(loaded)
        assert restored == state

    def test_yaml_is_valid(self, tmp_path: Path) -> None:
        data = {"name": "test", "values": [1, 2, 3]}
        path = str(tmp_path / "valid.yaml")
        save_yaml(data, path)
        with open(path) as f:
            parsed = yaml.safe_load(f)
        assert parsed == data


# ── Cross-format consistency ────────────────────────────────────────────────


class TestCrossFormatConsistency:
    """Tests that JSON and YAML produce equivalent results."""

    def test_problem_json_yaml_equivalent(self, tmp_path: Path) -> None:
        problem = _make_problem()
        data = problem_to_dict(problem)

        json_path = str(tmp_path / "problem.json")
        yaml_path = str(tmp_path / "problem.yaml")

        save_json(data, json_path)
        save_yaml(data, yaml_path)

        json_loaded = load_json(json_path)
        yaml_loaded = load_yaml(yaml_path)

        assert json_loaded == yaml_loaded

    def test_result_json_yaml_equivalent(self, tmp_path: Path) -> None:
        result = _make_result()
        data = result_to_dict(result)

        json_path = str(tmp_path / "result.json")
        yaml_path = str(tmp_path / "result.yaml")

        save_json(data, json_path)
        save_yaml(data, yaml_path)

        json_loaded = load_json(json_path)
        yaml_loaded = load_yaml(yaml_path)

        assert json_loaded == yaml_loaded
