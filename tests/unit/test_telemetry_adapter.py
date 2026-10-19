"""Unit tests for the ROS2 telemetry adapter.

No ROS2 environment is required: rclpy is never imported by the module
under test, subscriptions/publishers are driven through a fake node, and
time is driven through an injected clock.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apex_autopilot_optimization.core.types import (
    Pose3D,
    StateVector,
    VehicleType,
    Velocity3D,
)
from apex_autopilot_optimization.events.bus import EventBus
from apex_autopilot_optimization.events.event import Event
from apex_autopilot_optimization.messaging.qos import (
    QOS_AGGREGATE,
    QOS_MODE,
    QOS_SENSOR,
    QOS_STATUS,
    qos_for_topic,
)
from apex_autopilot_optimization.messaging.telemetry_adapter import (
    AGGREGATE_TOPIC,
    TelemetryAdapter,
)

EVENT_TYPE_STATE = "apex.telemetry.state"


class FakeNode:
    """Records create_subscription/create_publisher calls without rclpy."""

    def __init__(self) -> None:
        self.subscriptions: list[dict[str, Any]] = []
        self.publishers: list[dict[str, Any]] = []

    def create_subscription(
        self, msg_type: Any, topic: str, callback: Any, qos_profile: Any, **kwargs: Any
    ) -> SimpleNamespace:
        self.subscriptions.append(
            {
                "msg_type": msg_type,
                "topic": topic,
                "callback": callback,
                "qos": qos_profile,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace()

    def create_publisher(
        self, msg_type: Any, topic: str, qos_profile: Any, **kwargs: Any
    ) -> SimpleNamespace:
        self.publishers.append(
            {
                "msg_type": msg_type,
                "topic": topic,
                "qos": qos_profile,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace()


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def make_telemetry(
    *, drone_id: int = 1, stamp: float = 1_000_000.0, **overrides: Any
) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "header": SimpleNamespace(stamp=SimpleNamespace(sec=int(stamp), nanosec=0)),
        "drone_id": int(drone_id),
        "timestamp_us": int(stamp * 1e6),
        "x": 10.0,
        "y": 20.0,
        "z": 30.0,
        "roll": 0.1,
        "pitch": 0.2,
        "yaw": 0.3,
        "vx": 1.0,
        "vy": 2.0,
        "vz": 3.0,
        "battery_voltage": 12.0,
        "battery_current": -1.5,
        "battery_remaining": 0.75,
        "battery_charge_state": 1,
        "lat": 37.7749,
        "lon": -122.4194,
        "alt_amsl": 100.0,
        "alt_ellipsoid": 98.0,
        "gps_fix_type": 3,
        "nsat": 12,
        "eph": 1.5,
        "epv": 2.0,
        "ground_speed": 5.0,
        "nav_state": 14,
        "arming_state": 2,
        "vehicle_type": 1,
        "pre_flight_checks_pass": True,
        "is_vtol": False,
        "in_transition_mode": False,
        "source": "px4_interface",
        "pose_frame": 1,
        "velocity_frame": 1,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def make_yolo(
    *,
    drone_id: int = 1,
    stamp: float = 1_000_000.0,
    detections: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    if detections is None:
        detections = [
            SimpleNamespace(
                class_id="person",
                score=0.9,
                center_x=0.5,
                center_y=0.5,
                size_x=0.1,
                size_y=0.1,
                azimuth_deg=10.0,
                elevation_deg=5.0,
                depth_m=12.0,
            )
        ]
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=int(stamp), nanosec=0)),
        drone_id=int(drone_id),
        timestamp_us=int(stamp * 1e6),
        detections=list(detections),
    )


def make_adapter(
    clock: FakeClock | None = None, **kwargs: Any
) -> tuple[TelemetryAdapter, EventBus, dict, FakeClock]:
    bus = EventBus()
    store: dict = {}
    if clock is None:
        clock = FakeClock()
    adapter = TelemetryAdapter(event_bus=bus, state_store=store, now=clock, **kwargs)
    return adapter, bus, store, clock


class TestQoSProfiles:
    def test_qos_sensor_is_best_effort_volatile(self) -> None:
        assert QOS_SENSOR.reliability == "best_effort"
        assert QOS_SENSOR.durability == "volatile"
        assert QOS_SENSOR.depth == 10

    def test_qos_status_is_reliable_volatile(self) -> None:
        assert QOS_STATUS.reliability == "reliable"
        assert QOS_STATUS.durability == "volatile"

    def test_qos_mode_is_reliable_transient_local(self) -> None:
        assert QOS_MODE.reliability == "reliable"
        assert QOS_MODE.durability == "transient_local"

    def test_qos_aggregate_is_reliable_transient_local(self) -> None:
        assert QOS_AGGREGATE.reliability == "reliable"
        assert QOS_AGGREGATE.durability == "transient_local"

    def test_qos_profiles_are_distinct(self) -> None:
        profiles = [QOS_SENSOR, QOS_STATUS, QOS_MODE, QOS_AGGREGATE]
        assert len({(p.reliability, p.durability, p.depth) for p in profiles}) == 4

    def test_qos_for_topic_mapping(self) -> None:
        assert qos_for_topic(AGGREGATE_TOPIC) is QOS_AGGREGATE
        assert qos_for_topic("/Drone1/telemetry/vehicle_telemetry") is QOS_SENSOR
        assert qos_for_topic("/Drone7/yolo/detections") is QOS_SENSOR
        assert qos_for_topic("/Drone3/fmu/out/vehicle_status") is QOS_STATUS
        assert qos_for_topic("/unknown/topic") is QOS_SENSOR


class TestTelemetryAdapterConstruction:
    def test_constructs_without_ros2_node(self) -> None:
        adapter, _, _, _ = make_adapter()
        assert adapter.event_bus is not None
        assert adapter.state_store == {}
        assert not adapter.started

    def test_defaults_ttl_and_window(self) -> None:
        adapter, _, _, _ = make_adapter()
        assert adapter.staleness_ttl_sec == 0.5
        assert adapter.time_sync_window_sec == 0.05

    def test_custom_ttl_and_window(self) -> None:
        adapter, _, _, _ = make_adapter(staleness_ttl_sec=1.0, time_sync_window_sec=0.1)
        assert adapter.staleness_ttl_sec == 1.0
        assert adapter.time_sync_window_sec == 0.1

    def test_start_without_node_runs_without_ros2(self) -> None:
        adapter, _, _, _ = make_adapter()
        adapter.start()  # type: ignore[arg-type]
        # No ROS2 wiring is possible, but the adapter is still usable.
        assert adapter.started
        assert adapter.subscription_count == 0

    def test_event_bus_defaults_to_new_bus(self) -> None:
        adapter = TelemetryAdapter()
        assert isinstance(adapter.event_bus, EventBus)


class TestAdapterRosWiring:
    def test_start_subscribes_to_aggregate_with_aggregate_qos(self) -> None:
        node = FakeNode()
        adapter, _, _, _ = make_adapter()
        adapter.start(node=node)
        assert adapter.started
        aggregate = [s for s in node.subscriptions if s["topic"] == AGGREGATE_TOPIC]
        assert len(aggregate) == 1
        assert aggregate[0]["qos"] is QOS_AGGREGATE
        # Callback is bound to the adapter (behavioral check: it demuxes by drone_id).
        callback = aggregate[0]["callback"]
        callback(make_telemetry(drone_id=3))
        assert adapter.get_state(3) is not None

    def test_start_subscribes_per_drone_telemetry_and_yolo(self) -> None:
        node = FakeNode()
        adapter, _, _, _ = make_adapter(drone_ids=[1, 7])
        adapter.start(node=node)
        topics = {s["topic"]: s for s in node.subscriptions}
        assert topics["/Drone1/telemetry/vehicle_telemetry"]["qos"] is QOS_SENSOR
        assert topics["/Drone1/yolo/detections"]["qos"] is QOS_SENSOR
        assert topics["/Drone7/telemetry/vehicle_telemetry"]["qos"] is QOS_SENSOR
        assert topics["/Drone7/yolo/detections"]["qos"] is QOS_SENSOR
        # per-drone callbacks are bound to their drone_id
        msg = make_telemetry(drone_id=1)
        topics["/Drone1/telemetry/vehicle_telemetry"]["callback"](msg)
        assert adapter.get_state(1) is not None

    def test_start_creates_no_subscriptions_without_node(self) -> None:
        adapter, _, _, _ = make_adapter()
        adapter.start()  # type: ignore[arg-type]
        assert adapter.started
        assert adapter.subscription_count == 0

    def test_shutdown_clears_subscriptions(self) -> None:
        node = FakeNode()
        adapter, _, _, _ = make_adapter()
        adapter.start(node=node)
        adapter.shutdown()
        assert not adapter.started
        assert adapter.subscription_count == 0


class TestTelemetryMapping:
    def test_vehicle_telemetry_maps_pose_velocity_timestamp(self) -> None:
        adapter, _, store, clock = make_adapter()
        msg = make_telemetry(drone_id=1, stamp=clock.now)
        adapter.ingest_vehicle_telemetry(msg)

        state = store[1]
        assert isinstance(state, StateVector)
        assert state.pose == Pose3D(x=10.0, y=20.0, z=30.0, roll=0.1, pitch=0.2, yaw=0.3)
        assert state.velocity == Velocity3D(vx=1.0, vy=2.0, vz=3.0)
        assert state.timestamp == pytest.approx(clock.now)

    def test_aggregate_message_is_keyed_by_drone_id(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_aggregate(make_telemetry(drone_id=5))
        assert 5 in store
        assert 1 not in store

    def test_metadata_contains_required_keys(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        meta = store[1].metadata
        for key in ("battery", "gps_fix", "mode", "armed", "vehicle_type", "yolo_detections"):
            assert key in meta, f"missing metadata key {key!r}"
        assert meta["drone_id"] == 1
        assert meta["source"] == "px4_interface"

    def test_metadata_battery_values(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        battery = store[1].metadata["battery"]
        assert battery == {
            "voltage_v": 12.0,
            "current_a": -1.5,
            "remaining_fraction": 0.75,
            "charge_state": 1,
        }

    def test_metadata_gps_fix_values(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        gps = store[1].metadata["gps_fix"]
        assert gps["fix_type"] == 3
        assert gps["nsat"] == 12
        assert gps["eph_m"] == 1.5
        assert gps["epv_m"] == 2.0
        assert gps["ground_speed_m_s"] == 5.0
        assert gps["lat"] == 37.7749
        assert gps["lon"] == -122.4194
        assert gps["alt_amsl_m"] == 100.0
        assert gps["alt_ellipsoid_m"] == 98.0

    def test_metadata_mode_from_nav_state(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, nav_state=14))
        assert store[1].metadata["mode"] == "OFFBOARD"

        adapter2, _, store2, _ = make_adapter()
        adapter2.ingest_vehicle_telemetry(make_telemetry(drone_id=1, nav_state=15))
        assert store2[1].metadata["mode"] == "AUTO_MISSION"

        adapter3, _, store3, _ = make_adapter()
        adapter3.ingest_vehicle_telemetry(make_telemetry(drone_id=1, nav_state=99))
        assert store3[1].metadata["mode"] == "NAV_STATE_99"

    def test_armed_derived_from_arming_state(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, arming_state=2))
        assert store[1].metadata["armed"] is True

        adapter2, _, store2, _ = make_adapter()
        adapter2.ingest_vehicle_telemetry(make_telemetry(drone_id=1, arming_state=1))
        assert store2[1].metadata["armed"] is False

    def test_vehicle_type_mapping(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, vehicle_type=1))
        assert store[1].metadata["vehicle_type"] == VehicleType.UAV_MULTIROTOR.name

        adapter2, _, store2, _ = make_adapter()
        adapter2.ingest_vehicle_telemetry(make_telemetry(drone_id=1, vehicle_type=2))
        assert store2[1].metadata["vehicle_type"] == VehicleType.UAV_FIXED_WING.name

        adapter3, _, store3, _ = make_adapter()
        adapter3.ingest_vehicle_telemetry(make_telemetry(drone_id=1, vehicle_type=3))
        assert store3[1].metadata["vehicle_type"] == VehicleType.GROUND_VEHICLE_ACKERMANN.name

        adapter4, _, store4, _ = make_adapter()
        adapter4.ingest_vehicle_telemetry(make_telemetry(drone_id=1, vehicle_type=99))
        assert store4[1].metadata["vehicle_type"] == "UNKNOWN"
        assert store4[1].metadata["vehicle_type_raw"] == 99

    def test_yolo_detections_merged_into_metadata(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        adapter.ingest_yolo(make_yolo(drone_id=1))
        meta = store[1].metadata
        assert meta["synced"] is True
        assert len(meta["yolo_detections"]) == 1
        detection = meta["yolo_detections"][0]
        assert detection["class_id"] == "person"
        assert detection["score"] == 0.9
        assert detection["depth_m"] == 12.0

    def test_timestamp_from_timestamp_us(self) -> None:
        stamp = 1_500_000.0
        clock = FakeClock(stamp)
        adapter, _, store, _ = make_adapter(clock=clock)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=stamp))
        assert store[1].timestamp == pytest.approx(stamp)


class TestStalenessTTL:
    def test_fresh_telemetry_publishes_state(self) -> None:
        adapter, bus, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        assert 1 in store
        events = bus.get_event_history()
        assert len(events) == 1
        assert events[0].type == EVENT_TYPE_STATE

    def test_stale_telemetry_is_skipped(self) -> None:
        adapter, bus, store, clock = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        clock.advance(1.0)  # well beyond the 500 ms TTL
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        # Re-ingesting an old-stamped message must not publish again.
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now - 1.0))
        assert len(bus.get_event_history()) == 2  # two fresh publishes only
        # store keeps the latest *published* state
        assert store[1].timestamp == pytest.approx(clock.now)

    def test_staleness_exact_ttl_is_still_fresh(self) -> None:
        adapter, bus, store, clock = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        clock.advance(0.5)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        assert len(bus.get_event_history()) == 2
        clock.advance(0.0001)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now - 0.5001))
        assert len(bus.get_event_history()) == 2

    def test_get_state_none_when_no_data(self) -> None:
        adapter, _, _, _ = make_adapter()
        assert adapter.get_state(1) is None

    def test_get_state_returns_latest_published(self) -> None:
        adapter, _, store, clock = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        clock.advance(0.1)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, x=99.0, stamp=clock.now))
        state = adapter.get_state(1)
        assert state is not None
        assert state.pose.x == pytest.approx(99.0)


class TestTimeSyncWindow:
    def test_yolo_within_window_is_synced(self) -> None:
        adapter, _, store, clock = make_adapter(time_sync_window_sec=0.05)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        clock.advance(0.02)  # 20 ms < 50 ms window
        adapter.ingest_yolo(make_yolo(drone_id=1, stamp=clock.now))
        assert store[1].metadata["synced"] is True
        assert len(store[1].metadata["yolo_detections"]) == 1

    def test_yolo_outside_window_is_not_synced(self) -> None:
        adapter, _, store, clock = make_adapter(time_sync_window_sec=0.05)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        clock.advance(0.2)  # 200 ms > 50 ms window
        adapter.ingest_yolo(make_yolo(drone_id=1, stamp=clock.now))
        assert store[1].metadata["synced"] is False
        assert store[1].metadata["yolo_detections"] == []

    def test_yolo_before_telemetry_within_window(self) -> None:
        adapter, _, store, clock = make_adapter(time_sync_window_sec=0.05)
        adapter.ingest_yolo(make_yolo(drone_id=1, stamp=clock.now))
        clock.advance(0.01)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        assert store[1].metadata["synced"] is True

    def test_auto_publish_after_each_message(self) -> None:
        adapter, bus, _, clock = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        assert len(bus.get_event_history()) == 1
        clock.advance(0.01)
        adapter.ingest_yolo(make_yolo(drone_id=1, stamp=clock.now))
        assert len(bus.get_event_history()) == 2

    def test_no_auto_publish_when_disabled(self) -> None:
        adapter, bus, _, clock = make_adapter(auto_publish=False)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        assert len(bus.get_event_history()) == 0
        adapter.publish_states()
        assert len(bus.get_event_history()) == 1


class TestEventBusPublishing:
    def test_publishes_apex_telemetry_state_event(self) -> None:
        adapter, bus, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        event = bus.get_event_history()[-1]
        assert isinstance(event, Event)
        assert event.type == EVENT_TYPE_STATE
        assert event.source == "telemetry_adapter"
        assert event.payload["drone_id"] == 1
        assert "state" in event.payload
        assert event.timestamp == store[1].timestamp

    def test_event_payload_state_matches_state_to_dict(self) -> None:
        from apex_autopilot_optimization.serialization import state_to_dict

        adapter, bus, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        payload = bus.get_event_history()[-1].payload
        assert payload["state"] == state_to_dict(store[1])

    def test_state_store_holds_state_vector(self) -> None:
        adapter, _, store, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        assert isinstance(store[1], StateVector)
        assert store[1].metadata["armed"] is True

    def test_get_all_states(self) -> None:
        adapter, _, _, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=2))
        states = adapter.get_all_states()
        assert set(states) == {1, 2}


class TestMultiDrone:
    def test_multiple_drones_are_independent(self) -> None:
        adapter, bus, store, clock = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now))
        clock.advance(1.0)
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=2, x=5.0, stamp=clock.now))
        # Re-issuing drone 1's old stamp is stale and must not publish.
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1, stamp=clock.now - 1.0))
        assert len(bus.get_event_history()) == 2  # one publish per drone
        assert store[2].pose.x == pytest.approx(5.0)
        assert store[1].pose.x == pytest.approx(10.0)


class TestTelemetryAdapterEdgeCases:
    def test_aggregate_without_drone_id_is_ignored(self) -> None:
        adapter, bus, _, _ = make_adapter()
        adapter.ingest_aggregate(SimpleNamespace())  # no drone_id
        assert len(bus.get_event_history()) == 0

    def test_handle_telemetry_before_start_works(self) -> None:
        adapter, bus, _, _ = make_adapter()
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=1))
        assert len(bus.get_event_history()) == 1

    def test_unknown_drone_id_still_tracked(self) -> None:
        adapter, _, store, _ = make_adapter(drone_ids=[1])
        adapter.ingest_vehicle_telemetry(make_telemetry(drone_id=42))
        assert 42 in store
