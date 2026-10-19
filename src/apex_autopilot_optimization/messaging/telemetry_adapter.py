"""ROS2 telemetry adapter for the apex / AAS integration.

Subscribes to the fleet aggregate topic (``/fleet/telemetry/aggregate``) and
to per-vehicle topics (``/Drone{id}/telemetry/vehicle_telemetry`` and
``/Drone{id}/yolo/detections``), demuxes all telemetry by ``drone_id``,
enforces a 500 ms staleness TTL and a 50 ms time-sync window, maps
``VehicleTelemetry.msg`` fields onto an apex :class:`StateVector` with a
metadata dict (battery, GPS fix, mode, armed, vehicle_type, YOLO
detections), and publishes the aggregated state to the apex event bus and
an in-memory state store.

The module imports neither rclpy nor apex_telemetry_msgs at import time, so
it can be unit-tested without a ROS2 environment: pass a fake node-like
object exposing ``create_subscription``/``create_publisher`` to
:meth:`start`. All message access is duck-typed (``getattr`` with defaults),
so plain ``types.SimpleNamespace`` objects stand in for ROS2 messages in
tests.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from apex_autopilot_optimization.core.types import (
    Pose3D,
    StateVector,
    VehicleType,
    Velocity3D,
)
from apex_autopilot_optimization.events import Event, EventBus
from apex_autopilot_optimization.messaging.qos import (
    AGGREGATE_TOPIC,
    QOS_SENSOR,
    qos_for_topic,
)

logger = logging.getLogger(__name__)

DEFAULT_STALENESS_TTL_SEC = 0.5
DEFAULT_TIME_SYNC_WINDOW_SEC = 0.05

VEHICLE_TELEMETRY_TOPIC = "/Drone{drone_id}/telemetry/vehicle_telemetry"
YOLO_TOPIC = "/Drone{drone_id}/yolo/detections"

EVENT_TYPE_STATE = "apex.telemetry.state"

# PX4 navigation state -> mode string. The contract comment pins
# OFFBOARD=14, AUTO_MISSION=15, HOLD=4; remaining entries follow common
# PX4 numbering. Unknown states fall back to "NAV_STATE_<n>".
_NAV_STATE_NAMES: dict[int, str] = {
    0: "MANUAL",
    1: "ALTCTL",
    2: "POSCTL",
    4: "HOLD",
    5: "AUTO_RTL",
    6: "AUTO_LAND",
    7: "AUTO_TAKEOFF",
    9: "FOLLOW_TARGET",
    10: "STAB",
    11: "ACRO",
    13: "AUTO_PRECLAND",
    14: "OFFBOARD",
    15: "AUTO_MISSION",
}

# PX4 vehicle_type (per contract comment: 1=ROTARY_WING, 2=FIXED_WING,
# 3=ROVER) -> apex VehicleType.
_VEHICLE_TYPE_BY_CODE: dict[int, VehicleType] = {
    1: VehicleType.UAV_MULTIROTOR,
    2: VehicleType.UAV_FIXED_WING,
    3: VehicleType.GROUND_VEHICLE_ACKERMANN,
}

_ARMED_STATE = 2  # PX4 arming_state: 2 = ARMED

_TELEMETRY_FIELDS: dict[str, Any] = {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
    "vx": 0.0,
    "vy": 0.0,
    "vz": 0.0,
    "battery_voltage": 0.0,
    "battery_current": 0.0,
    "battery_remaining": 0.0,
    "battery_charge_state": 0,
    "lat": 0.0,
    "lon": 0.0,
    "alt_amsl": 0.0,
    "alt_ellipsoid": 0.0,
    "gps_fix_type": 0,
    "nsat": 0,
    "eph": 0.0,
    "epv": 0.0,
    "ground_speed": 0.0,
    "nav_state": 0,
    "arming_state": 1,
    "vehicle_type": 0,
    "pre_flight_checks_pass": False,
    "is_vtol": False,
    "in_transition_mode": False,
    "source": "",
    "pose_frame": 0,
    "velocity_frame": 0,
}


@dataclass
class _DroneSnapshot:
    """Latest demuxed telemetry for a single drone."""

    telemetry: dict[str, Any] | None = None
    telemetry_ts: float | None = None
    yolo_detections: list[dict[str, Any]] | None = None
    yolo_ts: float | None = None


class TelemetryAdapter:
    """Demux vehicle telemetry into apex state vectors.

    Args:
        node: Optional ROS2-like node with ``create_subscription`` /
            ``create_publisher``. When ``None`` the adapter runs without
            ROS2 (useful for tests and offline contexts).
        event_bus: Optional apex :class:`EventBus`. A new bus is created
            when omitted.
        state_store: Optional mutable mapping drone_id -> StateVector used
            as the published state store. A fresh dict is used when omitted.
        drone_ids: Per-vehicle drone IDs to subscribe to (in addition to
            the fleet aggregate, which is keyed by ``msg.drone_id``).
        staleness_ttl_sec: Telemetry older than this (seconds) is not
            published. Default 0.5 s per the contract.
        time_sync_window_sec: Telemetry and YOLO messages for a drone are
            considered synchronized when their stamps differ by at most
            this many seconds. Default 0.05 s per the contract.
        now: Callable returning the current time as a float (seconds).
            Defaults to :func:`time.time`.
        auto_publish: When True, every ingested message triggers
            :meth:`publish_states` for the affected drone.
    """

    def __init__(
        self,
        *,
        node: Any = None,
        event_bus: EventBus | None = None,
        state_store: dict[int, StateVector] | None = None,
        drone_ids: Iterable[int] = (),
        staleness_ttl_sec: float = DEFAULT_STALENESS_TTL_SEC,
        time_sync_window_sec: float = DEFAULT_TIME_SYNC_WINDOW_SEC,
        now: Callable[[], float] = time.time,
        auto_publish: bool = True,
    ) -> None:
        self._node = node
        self._event_bus = event_bus or EventBus()
        self._state_store: dict[int, StateVector] = {} if state_store is None else state_store
        self._drone_ids = {int(drone_id) for drone_id in drone_ids}
        self.staleness_ttl_sec = float(staleness_ttl_sec)
        self.time_sync_window_sec = float(time_sync_window_sec)
        self._now = now
        self.auto_publish = auto_publish
        self._snapshots: dict[int, _DroneSnapshot] = defaultdict(_DroneSnapshot)
        self._subscription_handles: list[Any] = []
        self.started = False

    # ── ROS2 wiring ───────────────────────────────────────────────────────

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def state_store(self) -> dict[int, StateVector]:
        return self._state_store

    @property
    def subscription_count(self) -> int:
        return len(self._subscription_handles)

    def start(self, node: Any | None = None) -> None:
        """Create ROS2 subscriptions (and aggregate re-publisher).

        When *node* is None the call is a no-op, which keeps the adapter
        usable without rclpy installed.
        """
        if node is not None:
            self._node = node
        if self._node is None:
            logger.debug("TelemetryAdapter.start() with no node; running without ROS2")
            self.started = True
            return

        vehicle_telemetry_type, yolo_array_type = self._resolve_message_types()

        subscriptions: list[tuple[Any, str, Any, Any]] = [
            (
                vehicle_telemetry_type,
                AGGREGATE_TOPIC,
                self._on_aggregate,
                qos_for_topic(AGGREGATE_TOPIC),
            )
        ]
        for drone_id in sorted(self._drone_ids):
            subscriptions.extend(
                [
                    (
                        vehicle_telemetry_type,
                        VEHICLE_TELEMETRY_TOPIC.format(drone_id=drone_id),
                        self._bind(self._on_vehicle_telemetry, drone_id),
                        QOS_SENSOR,
                    ),
                    (
                        yolo_array_type,
                        YOLO_TOPIC.format(drone_id=drone_id),
                        self._bind(self._on_yolo, drone_id),
                        QOS_SENSOR,
                    ),
                ]
            )

        for msg_type, topic, callback, qos in subscriptions:
            handle = self._node.create_subscription(
                msg_type, topic, callback, self._as_rclpy_qos(qos)
            )
            self._subscription_handles.append(handle)
        self.started = True
        logger.info("TelemetryAdapter started with %d subscriptions", len(subscriptions))

    def shutdown(self) -> None:
        """Drop ROS2 subscription handles and clear the demux buffer."""
        for handle in self._subscription_handles:
            destroyer = getattr(handle, "destroy", None) or getattr(
                handle, "destroy_subscription", None
            )
            if callable(destroyer):
                try:
                    destroyer()
                except Exception:  # noqa: BLE001 - best effort cleanup
                    logger.warning("Failed to destroy ROS2 subscription handle")
        self._subscription_handles.clear()
        self._snapshots.clear()
        self.started = False

    def _resolve_message_types(self) -> tuple[Any, Any]:
        """Lazily resolve VehicleTelemetry / YoloDetectionArray (rclpy-free)."""
        vehicle_telemetry_type: Any = None
        yolo_array_type: Any = None
        try:
            from apex_telemetry_msgs import (
                VehicleTelemetry,
                YoloDetectionArray,
            )

            vehicle_telemetry_type = VehicleTelemetry
            yolo_array_type = YoloDetectionArray
        except ImportError:
            logger.debug(
                "apex_telemetry_msgs not importable; ROS2 subscriptions will "
                "require message types passed through the node mock"
            )
        return vehicle_telemetry_type, yolo_array_type

    @staticmethod
    def _bind(method: Any, drone_id: int) -> Any:
        """Return a callback that fixes drone_id for per-vehicle topics."""

        def bound(msg: Any) -> None:
            method(msg, drone_id=drone_id)

        return bound

    @staticmethod
    def _as_rclpy_qos(qos: Any) -> Any:
        """Convert a contract QoSProfile to rclpy when possible, else pass through."""
        converter = getattr(qos, "to_rclpy", None)
        if callable(converter):
            try:
                return converter()
            except ImportError:  # rclpy not installed
                return qos
        return qos

    # ── Ingestion (ROS2 callbacks and public entry points) ────────────────

    def ingest_vehicle_telemetry(self, msg: Any, drone_id: int | None = None) -> None:
        """Handle one per-vehicle vehicle_telemetry message."""
        if drone_id is None:
            drone_id = getattr(msg, "drone_id", None)
        if drone_id is None:
            logger.warning("vehicle_telemetry without drone_id; ignoring")
            return
        drone_id = int(drone_id)
        fields = self._extract_telemetry_fields(msg)
        fields["drone_id"] = drone_id
        ts = self._message_timestamp(msg)
        snapshot = self._snapshots[drone_id]
        snapshot.telemetry = fields
        snapshot.telemetry_ts = ts if ts is not None else self._now()
        logger.debug("vehicle_telemetry demuxed for drone %s", drone_id)
        if self.auto_publish:
            self.publish_states(drone_id)

    def ingest_aggregate(self, msg: Any) -> None:
        """Handle one fleet aggregate message (keyed by msg.drone_id)."""
        drone_id = getattr(msg, "drone_id", None)
        if drone_id is None:
            logger.warning("aggregate telemetry without drone_id; ignoring")
            return
        self.ingest_vehicle_telemetry(msg, drone_id=int(drone_id))

    def ingest_yolo(self, msg: Any, drone_id: int | None = None) -> None:
        """Handle one YoloDetectionArray message for a drone."""
        if drone_id is None:
            drone_id = getattr(msg, "drone_id", None)
        if drone_id is None:
            logger.warning("yolo detections without drone_id; ignoring")
            return
        drone_id = int(drone_id)
        snapshot = self._snapshots[drone_id]
        snapshot.yolo_detections = [
            self._detection_dict(detection) for detection in getattr(msg, "detections", []) or []
        ]
        ts = self._message_timestamp(msg)
        snapshot.yolo_ts = ts if ts is not None else self._now()
        logger.debug("yolo detections demuxed for drone %s", drone_id)
        if self.auto_publish:
            self.publish_states(drone_id)

    # alias names used by ROS2 subscriptions created in start()
    _on_aggregate = ingest_aggregate
    _on_vehicle_telemetry = ingest_vehicle_telemetry
    _on_yolo = ingest_yolo

    # ── State assembly and publishing ─────────────────────────────────────

    def publish_states(self, drone_id: int | None = None) -> None:
        """Build and publish StateVectors for stale-free drones.

        Args:
            drone_id: Publish only this drone when given, else every drone
                with demuxed telemetry.
        """
        ids = [int(drone_id)] if drone_id is not None else list(self._snapshots)
        for did in ids:
            self._publish_for(did)

    def get_state(self, drone_id: int) -> StateVector | None:
        """Return the latest published StateVector for a drone, or None."""
        return self._state_store.get(int(drone_id))

    def get_all_states(self) -> dict[int, StateVector]:
        """Return a copy of the drone_id -> StateVector store."""
        return dict(self._state_store)

    def _publish_for(self, drone_id: int) -> None:
        snapshot = self._snapshots.get(drone_id)
        if snapshot is None or snapshot.telemetry is None:
            return
        if snapshot.telemetry_ts is None:
            return
        now = self._now()
        if now - snapshot.telemetry_ts > self.staleness_ttl_sec:
            return  # stale: do not publish or overwrite the store

        fields = snapshot.telemetry
        assert fields is not None  # narrowed above
        state = self._build_state(drone_id, fields, snapshot)
        self._state_store[drone_id] = state
        self._event_bus.publish(
            Event(
                type=EVENT_TYPE_STATE,
                source="telemetry_adapter",
                timestamp=state.timestamp,
                payload={
                    "drone_id": drone_id,
                    "state": self._state_payload(state),
                },
            )
        )

    def _build_state(
        self, drone_id: int, fields: dict[str, Any], snapshot: _DroneSnapshot
    ) -> StateVector:
        return StateVector(
            pose=Pose3D(
                x=fields.get("x", 0.0),
                y=fields.get("y", 0.0),
                z=fields.get("z", 0.0),
                roll=fields.get("roll", 0.0),
                pitch=fields.get("pitch", 0.0),
                yaw=fields.get("yaw", 0.0),
            ),
            velocity=Velocity3D(
                vx=fields.get("vx", 0.0),
                vy=fields.get("vy", 0.0),
                vz=fields.get("vz", 0.0),
            ),
            timestamp=snapshot.telemetry_ts or 0.0,
            metadata=self._build_metadata(drone_id, fields, snapshot),
        )

    def _build_metadata(
        self,
        drone_id: int,
        fields: dict[str, Any],
        snapshot: _DroneSnapshot,
    ) -> dict[str, Any]:
        telemetry_ts = snapshot.telemetry_ts
        yolo_ts = snapshot.yolo_ts
        if yolo_ts is None or telemetry_ts is None:
            synced = True
        else:
            synced = abs(yolo_ts - telemetry_ts) <= self.time_sync_window_sec

        nav_state = fields.get("nav_state", 0)
        arming_state = fields.get("arming_state", 1)
        vehicle_type_code = fields.get("vehicle_type", 0)
        vehicle_type = _VEHICLE_TYPE_BY_CODE.get(vehicle_type_code)

        yolo_detections = snapshot.yolo_detections or []
        if not synced:
            yolo_detections = []

        return {
            "drone_id": fields.get("drone_id", drone_id),
            "source": fields.get("source", ""),
            "battery": {
                "voltage_v": fields.get("battery_voltage", 0.0),
                "current_a": fields.get("battery_current", 0.0),
                "remaining_fraction": fields.get("battery_remaining", 0.0),
                "charge_state": fields.get("battery_charge_state", 0),
            },
            "gps_fix": {
                "fix_type": fields.get("gps_fix_type", 0),
                "nsat": fields.get("nsat", 0),
                "eph_m": fields.get("eph", 0.0),
                "epv_m": fields.get("epv", 0.0),
                "ground_speed_m_s": fields.get("ground_speed", 0.0),
                "lat": fields.get("lat", 0.0),
                "lon": fields.get("lon", 0.0),
                "alt_amsl_m": fields.get("alt_amsl", 0.0),
                "alt_ellipsoid_m": fields.get("alt_ellipsoid", 0.0),
            },
            "mode": _NAV_STATE_NAMES.get(nav_state, f"NAV_STATE_{nav_state}"),
            "armed": arming_state == _ARMED_STATE,
            "vehicle_type": vehicle_type.name if vehicle_type is not None else "UNKNOWN",
            "vehicle_type_raw": vehicle_type_code,
            "arming_state": arming_state,
            "nav_state": nav_state,
            "yolo_detections": yolo_detections,
            "synced": synced,
            "pose_frame": fields.get("pose_frame", 0),
            "velocity_frame": fields.get("velocity_frame", 0),
            "pre_flight_checks_pass": fields.get("pre_flight_checks_pass", False),
            "is_vtol": fields.get("is_vtol", False),
            "in_transition_mode": fields.get("in_transition_mode", False),
            "timestamp_us": fields.get("timestamp_us"),
        }

    # ── Message field extraction (duck-typed, no ROS2 msg dependency) ─────

    @staticmethod
    def _extract_telemetry_fields(msg: Any) -> dict[str, Any]:
        return {name: getattr(msg, name, default) for name, default in _TELEMETRY_FIELDS.items()}

    @staticmethod
    def _message_timestamp(msg: Any) -> float | None:
        """Best-effort message timestamp in seconds (epoch float).

        Prefers the PX4 ``timestamp_us`` source time, then the ROS2
        ``header.stamp``, and returns None when neither is available.
        """
        timestamp_us = getattr(msg, "timestamp_us", None)
        if timestamp_us is not None:
            return float(timestamp_us) / 1e6
        header = getattr(msg, "header", None)
        if header is None:
            return None
        stamp = getattr(header, "stamp", None)
        if stamp is None:
            return None
        sec = getattr(stamp, "sec", None)
        nanosec = getattr(stamp, "nanosec", None)
        if sec is None:
            return None
        return float(sec) + float(nanosec or 0) * 1e-9

    @staticmethod
    def _detection_dict(detection: Any) -> dict[str, Any]:
        return {
            "class_id": getattr(detection, "class_id", ""),
            "score": float(getattr(detection, "score", 0.0) or 0.0),
            "center_x": float(getattr(detection, "center_x", 0.0) or 0.0),
            "center_y": float(getattr(detection, "center_y", 0.0) or 0.0),
            "size_x": float(getattr(detection, "size_x", 0.0) or 0.0),
            "size_y": float(getattr(detection, "size_y", 0.0) or 0.0),
            "azimuth_deg": float(getattr(detection, "azimuth_deg", 0.0) or 0.0),
            "elevation_deg": float(getattr(detection, "elevation_deg", 0.0) or 0.0),
            "depth_m": float(getattr(detection, "depth_m", 0.0) or 0.0),
        }

    @staticmethod
    def _state_payload(state: StateVector) -> dict[str, Any]:
        """JSON-friendly rendering of a StateVector for the event payload."""
        try:
            from apex_autopilot_optimization.serialization import state_to_dict

            return state_to_dict(state)
        except ImportError:  # pragma: no cover - serialization always present
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
