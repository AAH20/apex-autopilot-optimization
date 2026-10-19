"""TargetTransform: bearing + drone EKF state + extrinsics -> ENU Pose3D.

Implements Section 8 of the perception pipeline spec. Each confirmed track is
converted to a ``PerceptionTarget`` whose ``pose`` is an ENU ``Pose3D`` suitable
as a WTA ``Task`` input (StateVector-compatible).

Math:
1. Convert (bearing, elevation) to a unit bearing vector in the camera frame.
2. Rotate by camera extrinsics (mount roll/pitch/yaw) to the drone body frame.
3. Combine with the drone ENU state (Pose3D from StateVector) and rotate by the
   drone yaw into ENU.
4. Estimate range from angular_width_deg and the target size class
   (range = size / (2 * tan(angular_width / 2))).
5. pose = ENU position; timestamp = detection stamp.

A target is dropped if the drone state is older than MAX_STATE_AGE_S (100 ms).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from apex_autopilot_optimization.core.types import Pose3D, StateVector
from apex_autopilot_optimization.perception import (
    TYPICAL_SIZE_M,
    Extrinsics,
    PerceptionTarget,
    PerceptionTargetArray,
    TargetType,
)

MAX_STATE_AGE_S = 0.1


class TargetTransform:
    """Transforms confirmed tracks into ENU ``PerceptionTarget``s."""

    def __init__(
        self, config: dict[str, Any] | None = None, extrinsics: Extrinsics | None = None
    ) -> None:
        self.config = dict(config) if config is not None else {}
        transform_cfg = self.config.get("transform", {})
        self.max_state_age_s = float(transform_cfg.get("max_state_age_s", MAX_STATE_AGE_S))
        self.alignment_accuracy_m = float(transform_cfg.get("alignment_accuracy_m", 0.02))
        self.extrinsics = extrinsics or Extrinsics(
            roll_deg=float(transform_cfg.get("extrinsics", {}).get("roll_deg", 0.0)),
            pitch_deg=float(transform_cfg.get("extrinsics", {}).get("pitch_deg", 0.0)),
            yaw_deg=float(transform_cfg.get("extrinsics", {}).get("yaw_deg", 0.0)),
            tx_m=float(transform_cfg.get("extrinsics", {}).get("tx_m", 0.0)),
            ty_m=float(transform_cfg.get("extrinsics", {}).get("ty_m", 0.0)),
            tz_m=float(transform_cfg.get("extrinsics", {}).get("tz_m", 0.0)),
        )
        self.size_table = dict(TYPICAL_SIZE_M)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> TargetTransform:
        return cls(config)

    # ------------------------------------------------------------------ public
    def transform(
        self,
        tracks: list[Any],  # list of Track (confirmed) / PerceptionTarget inputs
        drone_state: StateVector | None,
        now: float,
        target_type_resolver: Callable[[str], TargetType] | None = None,
    ) -> PerceptionTargetArray:
        """Convert confirmed tracks into ENU ``PerceptionTarget``s.

        ``target_type_resolver`` is an optional callable(class_name) -> TargetType;
        defaults to using the track's class name via the bundled mapper table.
        """
        if drone_state is None:
            return PerceptionTargetArray()

        if self._is_stale(drone_state, now):
            return PerceptionTargetArray()

        targets: list[PerceptionTarget] = []
        for track in tracks:
            class_name = getattr(track, "class_name", "unclassified")
            confidence = getattr(track, "conf_hat", 0.0)
            stamp = track.last_seen
            if target_type_resolver is not None:
                target_type = target_type_resolver(class_name)
            else:
                target_type = _default_target_type(class_name)
            _default_size_class(class_name)

            pose = self._track_to_enu_pose(track, drone_state)
            if pose is None:
                continue

            cov = self._covariance_matrix()
            target_id = f"drone{getattr(track, 'drone_id', 0)}:track{track.track_id}"
            targets.append(
                PerceptionTarget(
                    target_id=target_id,
                    source_drone_id=getattr(track, "drone_id", 0),
                    source_camera_ids=(getattr(track, "camera_id", 0),),
                    pose=pose,
                    target_type=target_type,
                    confidence=float(confidence),
                    stamp=float(stamp),
                    bearing_deg=float(getattr(track, "bearing_hat", 0.0)),
                    elevation_deg=float(getattr(track, "elevation_hat", 0.0)),
                    angular_width_deg=float(getattr(track, "angular_width_hat", 0.0)),
                    position_cov_m=cov,
                )
            )

        return PerceptionTargetArray(targets=tuple(targets))

    def track_to_enu_position(
        self,
        bearing_deg: float,
        elevation_deg: float,
        angular_width_deg: float,
        size_class_name: str,
        drone_state: StateVector,
    ) -> Pose3D | None:
        """Single-track convenience: bearing/elevation + size class -> ENU Pose3D."""
        return self._bearing_to_enu_pose(
            bearing_deg, elevation_deg, angular_width_deg, size_class_name, drone_state
        )

    # ------------------------------------------------------------------ internals
    def _is_stale(self, drone_state: StateVector, now: float) -> bool:
        return (now - float(drone_state.timestamp)) > self.max_state_age_s

    def _track_to_enu_pose(self, track: Any, drone_state: StateVector) -> Pose3D | None:
        return self._bearing_to_enu_pose(
            float(getattr(track, "bearing_hat", 0.0)),
            float(getattr(track, "elevation_hat", 0.0)),
            float(getattr(track, "angular_width_hat", 0.0)),
            _default_size_class(getattr(track, "class_name", "unclassified")),
            drone_state,
        )

    def _bearing_to_enu_pose(
        self,
        bearing_deg: float,
        elevation_deg: float,
        angular_width_deg: float,
        size_class_name: str,
        drone_state: StateVector,
    ) -> Pose3D | None:
        # 1. Unit bearing vector in camera frame (x forward, y right, z up).
        br = math.radians(bearing_deg)
        el = math.radians(elevation_deg)
        cam_vec = self._unit_vector(
            math.cos(el) * math.cos(br),
            math.cos(el) * math.sin(br),
            math.sin(el),
        )

        # 2. Rotate by camera extrinsics to drone body frame.
        body_vec = self._rotate_by_euler(
            cam_vec, self.extrinsics.roll_deg, self.extrinsics.pitch_deg, self.extrinsics.yaw_deg
        )
        body_vec = self._add(
            body_vec, (self.extrinsics.tx_m, self.extrinsics.ty_m, self.extrinsics.tz_m)
        )

        # 3. Rotate by drone yaw (ENU alignment); direction is a unit vector.
        drone_pose = drone_state.pose
        enu_dir = self._rotate_z(body_vec, drone_pose.yaw)

        # Camera mount offset rotated into ENU.
        cam_offset_enu = self._rotate_z(
            (self.extrinsics.tx_m, self.extrinsics.ty_m, self.extrinsics.tz_m), drone_pose.yaw
        )

        # 4. Range from angular width + typical size (slant range).
        size = self.size_table.get(_size_class_enum(size_class_name), 2.0)
        aw = math.radians(angular_width_deg) if angular_width_deg > 0 else math.radians(5.0)
        range_m = size / (2.0 * math.tan(aw / 2.0)) if aw > 0 else 50.0

        x = drone_pose.x + cam_offset_enu[0] + enu_dir[0] * range_m
        y = drone_pose.y + cam_offset_enu[1] + enu_dir[1] * range_m
        z = drone_pose.z + cam_offset_enu[2] + enu_dir[2] * range_m

        # Yaw of the target points back toward the drone (bearing + drone yaw).
        target_yaw = drone_pose.yaw + br
        return Pose3D(x=x, y=y, z=z, yaw=target_yaw)

    @staticmethod
    def _rotate_by_euler(
        vec: tuple[float, float, float], roll_deg: float, pitch_deg: float, yaw_deg: float
    ) -> tuple[float, float, float]:
        r = math.radians(roll_deg)
        p = math.radians(pitch_deg)
        y = math.radians(yaw_deg)
        cr, sr = math.cos(r), math.sin(r)
        cp, sp = math.cos(p), math.sin(p)
        cy, sy = math.cos(y), math.sin(y)
        x, yc, z = vec
        # Roll (x)
        y1 = cr * yc - sr * z
        z1 = sr * yc + cr * z
        # Pitch (y)
        x2 = cp * x + sp * z1
        z2 = -sp * x + cp * z1
        # Yaw (z)
        x3 = cy * x2 - sy * y1
        y3 = sy * x2 + cy * y1
        return (x3, y3, z2)

    @staticmethod
    def _rotate_z(vec: tuple[float, float, float], yaw_deg: float) -> tuple[float, float, float]:
        y = math.radians(yaw_deg)
        cy, sy = math.cos(y), math.sin(y)
        x, yc, z = vec
        return (cy * x - sy * yc, sy * x + cy * yc, z)

    @staticmethod
    def _add(
        a: tuple[float, float, float], b: tuple[float, float, float]
    ) -> tuple[float, float, float]:
        return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

    @staticmethod
    def _unit_vector(x: float, y: float, z: float) -> tuple[float, float, float]:
        n = math.sqrt(x * x + y * y + z * z) or 1.0
        return (x / n, y / n, z / n)

    @staticmethod
    def _normalize(vec: tuple[float, float, float]) -> tuple[float, float, float]:
        return TargetTransform._unit_vector(vec[0], vec[1], vec[2])

    def _covariance_matrix(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
        acc = self.alignment_accuracy_m
        return (
            (acc * acc, 0.0, 0.0),
            (0.0, acc * acc, 0.0),
            (0.0, 0.0, (2.0 * acc) * (2.0 * acc)),
        )


def _default_target_type(class_name: str) -> TargetType:
    from apex_autopilot_optimization.perception import CLASS_MAP, DEFAULT_ENTRY

    entry = CLASS_MAP.get(class_name.strip().lower())
    return entry.target_type if entry is not None else DEFAULT_ENTRY.target_type


def _default_size_class(class_name: str) -> Any:
    from apex_autopilot_optimization.perception import CLASS_MAP, DEFAULT_ENTRY

    entry = CLASS_MAP.get(class_name.strip().lower())
    return entry.size_class if entry is not None else DEFAULT_ENTRY.size_class


def _size_class_enum(value: Any) -> Any:
    from apex_autopilot_optimization.perception import SizeClass

    if isinstance(value, SizeClass):
        return value
    try:
        return SizeClass(str(value))
    except (ValueError, TypeError):
        return SizeClass.MEDIUM
