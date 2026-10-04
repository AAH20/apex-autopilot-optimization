"""Serialization utilities for planning problems, results, and states."""

from __future__ import annotations

import dataclasses
import json
import types
import typing
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
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

T = TypeVar("T")


# ── StateVector ──────────────────────────────────────────────────────────────


def state_to_dict(state: StateVector) -> dict[str, Any]:
    """Serialize a StateVector to a plain dictionary."""
    return {
        "pose": {
            "x": state.pose.x,
            "y": state.pose.y,
            "z": state.pose.z,
            "roll": state.pose.roll,
            "pitch": state.pose.pitch,
            "yaw": state.pose.yaw,
        },
        "velocity": {
            "vx": state.velocity.vx,
            "vy": state.velocity.vy,
            "vz": state.velocity.vz,
            "vroll": state.velocity.vroll,
            "vpitch": state.velocity.vpitch,
            "vyaw": state.velocity.vyaw,
        },
        "timestamp": state.timestamp,
        "metadata": dict(state.metadata),
    }


def state_from_dict(data: dict[str, Any]) -> StateVector:
    """Deserialize a dictionary to a StateVector."""
    pose_data = data["pose"]
    vel_data = data["velocity"]
    return StateVector(
        pose=Pose3D(
            x=pose_data["x"],
            y=pose_data["y"],
            z=pose_data["z"],
            roll=pose_data.get("roll", 0.0),
            pitch=pose_data.get("pitch", 0.0),
            yaw=pose_data.get("yaw", 0.0),
        ),
        velocity=Velocity3D(
            vx=vel_data["vx"],
            vy=vel_data["vy"],
            vz=vel_data["vz"],
            vroll=vel_data.get("vroll", 0.0),
            vpitch=vel_data.get("vpitch", 0.0),
            vyaw=vel_data.get("vyaw", 0.0),
        ),
        timestamp=data.get("timestamp", 0.0),
        metadata=dict(data.get("metadata", {})),
    )


# ── Waypoint helpers ─────────────────────────────────────────────────────────


def _waypoint_to_dict(wp: Waypoint) -> dict[str, Any]:
    return {
        "pose": {
            "x": wp.pose.x,
            "y": wp.pose.y,
            "z": wp.pose.z,
            "roll": wp.pose.roll,
            "pitch": wp.pose.pitch,
            "yaw": wp.pose.yaw,
        },
        "speed": wp.speed,
        "arrival_time": wp.arrival_time,
        "tolerance_m": wp.tolerance_m,
        "hold_time_s": wp.hold_time_s,
    }


def _waypoint_from_dict(data: dict[str, Any]) -> Waypoint:
    pose_data = data["pose"]
    return Waypoint(
        pose=Pose3D(
            x=pose_data["x"],
            y=pose_data["y"],
            z=pose_data["z"],
            roll=pose_data.get("roll", 0.0),
            pitch=pose_data.get("pitch", 0.0),
            yaw=pose_data.get("yaw", 0.0),
        ),
        speed=data.get("speed", 0.0),
        arrival_time=data.get("arrival_time"),
        tolerance_m=data.get("tolerance_m", 1.0),
        hold_time_s=data.get("hold_time_s", 0.0),
    )


# ── Constraint / Objective helpers ───────────────────────────────────────────


def _constraint_to_dict(c: OptimizationConstraint) -> dict[str, Any]:
    return {
        "name": c.name,
        "constraint_type": c.constraint_type,
        "lower_bound": c.lower_bound,
        "upper_bound": c.upper_bound,
        "params": dict(c.params),
    }


def _constraint_from_dict(data: dict[str, Any]) -> OptimizationConstraint:
    return OptimizationConstraint(
        name=data["name"],
        constraint_type=data["constraint_type"],
        lower_bound=data.get("lower_bound"),
        upper_bound=data.get("upper_bound"),
        params=dict(data.get("params", {})),
    )


def _objective_to_dict(o: OptimizationObjective) -> dict[str, Any]:
    return {
        "name": o.name,
        "weight": o.weight,
        "minimize": o.minimize,
        "params": dict(o.params),
    }


def _objective_from_dict(data: dict[str, Any]) -> OptimizationObjective:
    return OptimizationObjective(
        name=data["name"],
        weight=data.get("weight", 1.0),
        minimize=data.get("minimize", True),
        params=dict(data.get("params", {})),
    )


# ── PlanningProblem ──────────────────────────────────────────────────────────


def problem_to_dict(problem: PlanningProblem) -> dict[str, Any]:
    """Serialize a PlanningProblem to a plain dictionary."""
    return {
        "vehicle_type": problem.vehicle_type.name,
        "start": state_to_dict(problem.start),
        "goal": _waypoint_to_dict(problem.goal),
        "waypoints": [_waypoint_to_dict(wp) for wp in problem.waypoints],
        "obstacles": [dict(obs) for obs in problem.obstacles],
        "constraints": [_constraint_to_dict(c) for c in problem.constraints],
        "objectives": [_objective_to_dict(o) for o in problem.objectives],
        "time_horizon_s": problem.time_horizon_s,
        "resolution_m": problem.resolution_m,
    }


def problem_from_dict(data: dict[str, Any]) -> PlanningProblem:
    """Deserialize a dictionary to a PlanningProblem."""
    return PlanningProblem(
        vehicle_type=VehicleType[data["vehicle_type"]],
        start=state_from_dict(data["start"]),
        goal=_waypoint_from_dict(data["goal"]),
        waypoints=[_waypoint_from_dict(wp) for wp in data.get("waypoints", [])],
        obstacles=[dict(obs) for obs in data.get("obstacles", [])],
        constraints=[_constraint_from_dict(c) for c in data.get("constraints", [])],
        objectives=[_objective_from_dict(o) for o in data.get("objectives", [])],
        time_horizon_s=data.get("time_horizon_s", 60.0),
        resolution_m=data.get("resolution_m", 1.0),
    )


# ── PlanningResult ──────────────────────────────────────────────────────────


def _control_input_to_dict(ci: ControlInput) -> dict[str, Any]:
    return {
        "throttle": ci.throttle,
        "roll_rate": ci.roll_rate,
        "pitch_rate": ci.pitch_rate,
        "yaw_rate": ci.yaw_rate,
        "timestamp": ci.timestamp,
    }


def _control_input_from_dict(data: dict[str, Any]) -> ControlInput:
    return ControlInput(
        throttle=data.get("throttle", 0.0),
        roll_rate=data.get("roll_rate", 0.0),
        pitch_rate=data.get("pitch_rate", 0.0),
        yaw_rate=data.get("yaw_rate", 0.0),
        timestamp=data.get("timestamp", 0.0),
    )


def _trajectory_to_dict(traj: Trajectory) -> dict[str, Any]:
    return {
        "states": [state_to_dict(s) for s in traj.states],
        "controls": [_control_input_to_dict(c) for c in traj.controls],
        "timestamps": traj.timestamps.tolist(),
        "vehicle_type": traj.vehicle_type.name,
    }


def _trajectory_from_dict(data: dict[str, Any]) -> Trajectory:
    return Trajectory(
        states=[state_from_dict(s) for s in data.get("states", [])],
        controls=[_control_input_from_dict(c) for c in data.get("controls", [])],
        timestamps=np.array(data.get("timestamps", []), dtype=np.float64),
        vehicle_type=VehicleType[data["vehicle_type"]],
    )


def result_to_dict(result: PlanningResult) -> dict[str, Any]:
    """Serialize a PlanningResult to a plain dictionary."""
    return {
        "success": result.success,
        "trajectory": _trajectory_to_dict(result.trajectory)
        if result.trajectory is not None
        else None,
        "computation_time_ms": result.computation_time_ms,
        "iterations": result.iterations,
        "cost": result.cost,
        "message": result.message,
        "metadata": dict(result.metadata),
    }


def result_from_dict(data: dict[str, Any]) -> PlanningResult:
    """Deserialize a dictionary to a PlanningResult."""
    traj_data = data.get("trajectory")
    return PlanningResult(
        success=data["success"],
        trajectory=_trajectory_from_dict(traj_data) if traj_data is not None else None,
        computation_time_ms=data.get("computation_time_ms", 0.0),
        iterations=data.get("iterations", 0),
        cost=data.get("cost", 0.0),
        message=data.get("message", ""),
        metadata=dict(data.get("metadata", {})),
    )


# ── Generic config serialization ─────────────────────────────────────────────


def _enum_to_value(e: Enum) -> str:
    """Convert an Enum to its name for serialization."""
    return e.name


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value to JSON-compatible types."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return _enum_to_value(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _serialize_value(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_serialize_value(item) for item in value]
    return value


def config_to_dict(config: Any) -> dict[str, Any]:
    """Generic dataclass-to-dict converter."""
    if not dataclasses.is_dataclass(config) or isinstance(config, type):
        raise TypeError(f"Expected a dataclass instance, got {type(config).__name__}")
    return {f.name: _serialize_value(getattr(config, f.name)) for f in dataclasses.fields(config)}


def _is_union_type(tp: Any) -> bool:
    """Check if a type hint is a Union (including Optional)."""
    origin = typing.get_origin(tp)
    if origin is typing.Union:
        return True
    return hasattr(types, "UnionType") and origin is types.UnionType


def _deserialize_value(value: Any, tp: Any) -> Any:
    """Deserialize a value according to its type hint."""
    if value is None:
        return None
    # Handle enums
    if isinstance(tp, type) and issubclass(tp, Enum):
        if isinstance(value, str):
            try:
                return tp[value]
            except KeyError:
                pass
        return tp(value)
    # Handle nested dataclasses
    if isinstance(tp, type) and dataclasses.is_dataclass(tp) and isinstance(value, dict):
        return _dataclass_from_dict(tp, value)
    # Handle Union/Optional
    origin = typing.get_origin(tp)
    if origin is not None:
        args = typing.get_args(tp)
        if _is_union_type(tp):
            for arg in args:
                if arg is type(None):
                    continue
                try:
                    return _deserialize_value(value, arg)
                except (ValueError, TypeError, KeyError):
                    continue
            return value
        if origin in (list, tuple):
            inner = args[0] if args else Any
            items = [_deserialize_value(item, inner) for item in value]
            return tuple(items) if origin is tuple else items
        if origin is dict:
            return {k: _deserialize_value(v, args[1] if args else Any) for k, v in value.items()}
    return value


def _dataclass_from_dict(cls: type[T], data: dict[str, Any]) -> T:
    """Construct a dataclass from a dictionary."""
    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        hints = {}
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        if f.name not in data:
            continue
        raw = data[f.name]
        tp = hints.get(f.name, Any)
        kwargs[f.name] = _deserialize_value(raw, tp)
    return cls(**kwargs)


def config_from_dict(data: dict[str, Any], cls: type[T]) -> T:
    """Generic dict-to-dataclass converter."""
    if not dataclasses.is_dataclass(cls) or not isinstance(cls, type):
        raise TypeError(f"Expected a dataclass type, got {cls}")
    return _dataclass_from_dict(cls, data)


# ── File I/O ────────────────────────────────────────────────────────────────


def save_json(data: dict[str, Any], path: str) -> None:
    """Save a dictionary to a JSON file."""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def load_json(path: str) -> dict[str, Any]:
    """Load a dictionary from a JSON file."""
    with open(path, encoding="utf-8") as f:
        result: dict[str, Any] = json.load(f)
        return result


def save_yaml(data: dict[str, Any], path: str) -> None:
    """Save a dictionary to a YAML file."""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_yaml(path: str) -> dict[str, Any]:
    """Load a dictionary from a YAML file."""
    with open(path, encoding="utf-8") as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result
