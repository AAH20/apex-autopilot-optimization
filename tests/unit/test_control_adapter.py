"""Unit tests for the control/setpoint ROS2 adapter.

These tests use mocks only: a fake clock, a mock publisher (no rclpy/ROS2),
and in-memory message capture. They drive the adapter through its public API
and assert on the topics, payloads, watchdog, veto latch, mode sequence, and
MAVLink parity mapping.

TDD: this file is written first (RED), then the implementation is added to
make it GREEN, then refactored.
"""

from __future__ import annotations

from apex_autopilot_optimization.messaging.control_adapter import (
    FRAME_NED,
    MODE_GUIDED,
    MODE_HOLD,
    MODE_OFFBOARD,
    SETPOINT_TYPE_POSITION_NED,
    SETPOINT_TYPE_VELOCITY_NED,
    VETO_HARD_EMERGENCY,
    VETO_SOFT_HOLD,
    ControlAdapter,
    FormationSetpoint,
    Header,
    ModeCommand,
    OffboardSetpoint,
    Veto,
    WTAAssignment,
    mavlink_parity,
)
from apex_autopilot_optimization.messaging.veto_manager import VetoManager
from apex_autopilot_optimization.messaging.watchdog import SetpointWatchdog

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeClock:
    """Deterministic clock; time only advances when tick() is called."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def tick(self, dt: float) -> float:
        self.now += float(dt)
        return self.now


class MockPublisher:
    """A mock ROS2-style publisher with a .publish(msg) method."""

    def __init__(self, topic: str) -> None:
        self.topic = topic
        self.calls: list = []

    def publish(self, msg) -> None:
        self.calls.append(msg)


class FakePublishers(dict):
    """dict[str, MockPublisher] with a helper to fetch by topic."""


def make_adapter(drone_id=1, clock=None, publishers=None, firmware="px4"):
    if clock is None:
        clock = FakeClock()
    return ControlAdapter(
        drone_id=drone_id,
        publishers=publishers,
        clock=clock,
        firmware=firmware,
    )


# ---------------------------------------------------------------------------
# Message dataclasses
# ---------------------------------------------------------------------------


class TestHeader:
    def test_defaults(self) -> None:
        h = Header()
        assert h.stamp == 0.0
        assert h.frame_id == ""

    def test_values(self) -> None:
        h = Header(stamp=123.0, frame_id="ned")
        assert h.stamp == 123.0
        assert h.frame_id == "ned"


class TestOffboardSetpoint:
    def test_velocity_ned_fields(self) -> None:
        m = OffboardSetpoint(
            header=Header(stamp=1.0, frame_id="ned"),
            drone_id=3,
            setpoint_type=SETPOINT_TYPE_VELOCITY_NED,
            frame=FRAME_NED,
            vx=1.0,
            vy=2.0,
            vz=-3.0,
            yaw_rate=0.5,
            duration_sec=0.0,
        )
        assert m.drone_id == 3
        assert m.setpoint_type == SETPOINT_TYPE_VELOCITY_NED
        assert m.frame == FRAME_NED
        assert (m.vx, m.vy, m.vz) == (1.0, 2.0, -3.0)
        assert m.yaw_rate == 0.5
        assert m.duration_sec == 0.0

    def test_position_ned_defaults_zero(self) -> None:
        m = OffboardSetpoint(drone_id=1, setpoint_type=SETPOINT_TYPE_POSITION_NED)
        assert m.x == 0.0 and m.y == 0.0 and m.z == 0.0
        assert m.ax == 0.0 and m.ay == 0.0 and m.az == 0.0


class TestFormationSetpoint:
    def test_fields(self) -> None:
        m = FormationSetpoint(
            header=Header(stamp=2.0),
            drone_id=2,
            formation_id=7,
            x=10.0,
            y=20.0,
            z=5.0,
            yaw=0.5,
            spacing_m=2.5,
            slot_valid=True,
        )
        assert m.formation_id == 7
        assert (m.x, m.y, m.z) == (10.0, 20.0, 5.0)
        assert m.slot_valid is True


class TestWTAAssignment:
    def test_fields_and_status(self) -> None:
        m = WTAAssignment(
            header=Header(stamp=3.0),
            task_id=42,
            assigned_drone_id=3,
            previous_drone_id=1,
            priority=1.5,
            task_x=1.0,
            task_y=2.0,
            task_z=3.0,
            assign_time=3.0,
            status=1,  # ACKED
        )
        assert m.task_id == 42
        assert m.assigned_drone_id == 3
        assert m.previous_drone_id == 1
        assert m.status == 1


class TestModeCommand:
    def test_fields(self) -> None:
        m = ModeCommand(
            header=Header(stamp=4.0),
            drone_id=1,
            target_mode=MODE_OFFBOARD,
            mode_source="apex/governance",
            timeout_sec=5.0,
        )
        assert m.target_mode == MODE_OFFBOARD
        assert m.mode_source == "apex/governance"
        assert m.timeout_sec == 5.0


class TestVeto:
    def test_fields(self) -> None:
        m = Veto(
            header=Header(stamp=5.0),
            drone_id=0,
            veto_type=VETO_HARD_EMERGENCY,
            severity=5,
            reason="geofence breach",
            authority="apex/governance",
            valid_until=0.0,
            require_clear_ack=True,
        )
        assert m.drone_id == 0  # fleet-wide
        assert m.veto_type == VETO_HARD_EMERGENCY
        assert m.require_clear_ack is True


# ---------------------------------------------------------------------------
# Publisher / topic naming
# ---------------------------------------------------------------------------


class TestPublishTopics:
    def _captured_topics(self, adapter) -> list[str]:
        return [topic for topic, _ in adapter._published]

    def test_offboard_setpoint_topic(self) -> None:
        a = make_adapter(drone_id=3)
        a.publish_offboard_setpoint(vx=1.0, vy=0.0, vz=0.0, yaw_rate=0.0, duration_sec=0.0)
        assert "/Drone3/offboard/setpoint" in self._captured_topics(a)
        msg = a._published[-1][1]
        assert msg.drone_id == 3
        assert msg.setpoint_type == SETPOINT_TYPE_VELOCITY_NED
        assert msg.vx == 1.0

    def test_formation_setpoint_topic(self) -> None:
        a = make_adapter(drone_id=2)
        a.publish_formation_setpoint(x=1.0, y=2.0, z=3.0, slot_valid=True)
        assert "/Drone2/formation/setpoint" in self._captured_topics(a)
        msg = a._published[-1][1]
        assert msg.drone_id == 2
        assert msg.slot_valid is True

    def test_wta_assignment_per_drone_topic(self) -> None:
        a = make_adapter(drone_id=1)
        a.publish_wta_assignment(task_id=9, assigned_drone_id=3, priority=1.0)
        assert "/Drone3/wta/assignment" in self._captured_topics(a)
        msg = a._published[-1][1]
        assert msg.assigned_drone_id == 3

    def test_fleet_wta_topic(self) -> None:
        a = make_adapter(drone_id=1)
        a.publish_fleet_wta_assignment(task_id=9, assigned_drone_id=3, priority=1.0)
        assert "/fleet/wta/assignments" in self._captured_topics(a)

    def test_mode_command_topic(self) -> None:
        a = make_adapter(drone_id=4)
        a.publish_mode_command(target_mode=MODE_GUIDED, timeout_sec=5.0)
        assert "/Drone4/mode/command" in self._captured_topics(a)
        msg = a._published[-1][1]
        assert msg.drone_id == 4
        assert msg.target_mode == MODE_GUIDED

    def test_veto_topic(self) -> None:
        a = make_adapter(drone_id=1)
        a.publish_veto(veto_type=VETO_SOFT_HOLD, reason="test", authority="apex/safety")
        assert "/Drone1/safety/veto" in self._captured_topics(a)
        msg = a._published[-1][1]
        assert msg.veto_type == VETO_SOFT_HOLD

    def test_mock_publisher_receives_message(self) -> None:
        pub = MockPublisher("/Drone1/offboard/setpoint")
        a = make_adapter(drone_id=1, publishers={"/Drone1/offboard/setpoint": pub})
        a.publish_offboard_setpoint(vx=5.0)
        assert len(pub.calls) == 1
        assert pub.calls[0].vx == 5.0
        assert pub.calls[0].drone_id == 1


# ---------------------------------------------------------------------------
# Heartbeat (10 Hz offboard)
# ---------------------------------------------------------------------------


class TestHeartbeat:
    def test_publish_heartbeat_sends_last_setpoint(self) -> None:
        a = make_adapter(drone_id=1)
        a.publish_offboard_setpoint(vx=1.0, vy=0.0, vz=0.0, yaw_rate=0.0)
        a.publish_heartbeat()
        topics = [t for t, _ in a._published]
        assert topics.count("/Drone1/offboard/setpoint") == 2
        assert a._published[-1][1].vx == 1.0

    def test_heartbeat_updates_watchdog(self) -> None:
        a = make_adapter(drone_id=1)
        a.publish_offboard_setpoint(vx=1.0)
        assert a.watchdog.last_setpoint_ts is not None


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------


class TestSetpointWatchdog:
    def test_not_lost_when_no_setpoint_seen(self) -> None:
        w = SetpointWatchdog(timeout_sec=0.5, clock=FakeClock(100.0))
        assert w.is_lost() is False

    def test_not_less_than_timeout(self) -> None:
        c = FakeClock(100.0)
        w = SetpointWatchdog(timeout_sec=0.5, clock=c)
        w.record_setpoint()
        assert w.is_lost() is False
        c.tick(0.4)
        assert w.is_lost() is False

    def test_lost_after_timeout(self) -> None:
        c = FakeClock(100.0)
        w = SetpointWatchdog(timeout_sec=0.5, clock=c)
        w.record_setpoint()
        c.tick(0.51)
        assert w.is_lost() is True

    def test_check_increments_loss_count(self) -> None:
        c = FakeClock(100.0)
        w = SetpointWatchdog(timeout_sec=0.5, clock=c)
        w.record_setpoint()
        c.tick(1.0)
        assert w.check() is True
        assert w.loss_count == 1
        assert w.check() is True
        assert w.loss_count == 2


class TestWatchdogIntegration:
    def test_setpoint_loss_detected_and_exits_offboard_to_hold(self) -> None:
        c = FakeClock(100.0)
        a = make_adapter(drone_id=1, clock=c)
        a.publish_offboard_setpoint(vx=1.0, vy=0.0, vz=0.0, yaw_rate=0.0)
        assert a.watchdog.is_lost() is False
        a.mode = "OFFBOARD"

        # Silence the stream beyond the 500 ms window (no tick/heartbeat refresh).
        c.tick(1.0)
        assert a.watchdog.is_lost() is True
        assert a.watchdog.check() is True
        assert a.watchdog.loss_count >= 1

        # Adapter translates loss into an OFFBOARD -> HOLD transition.
        a._handle_setpoint_loss(a._now())
        assert a.mode == "HOLD"
        assert a.sequence_state == "HOLD"
        assert a.armed is False
        assert any(
            isinstance(m, ModeCommand) and m.target_mode == MODE_HOLD for _, m in a._published
        )


# ---------------------------------------------------------------------------
# Veto manager
# ---------------------------------------------------------------------------


class TestVetoManager:
    def test_issue_and_active(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        v = Veto(
            drone_id=1, veto_type=VETO_SOFT_HOLD, severity=3, reason="r", authority="apex/safety"
        )
        vm.issue(v)
        active = vm.active()
        assert active is not None
        assert active.veto_type == VETO_SOFT_HOLD

    def test_clear_by_same_authority(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_SOFT_HOLD,
                severity=3,
                reason="r",
                authority="apex/safety",
            )
        )
        assert vm.active() is not None
        assert vm.clear("apex/safety") is True
        assert vm.active() is None

    def test_clear_by_higher_authority(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_SOFT_HOLD,
                severity=3,
                reason="r",
                authority="apex/planner",
            )
        )
        assert vm.clear("apex/governance") is True
        assert vm.active() is None

    def test_clear_by_lower_authority_denied(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_SOFT_HOLD,
                severity=3,
                reason="r",
                authority="apex/safety",
            )
        )
        assert vm.clear("operator") is False
        assert vm.active() is not None

    def test_hard_overrides_soft(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_SOFT_HOLD,
                severity=3,
                reason="r",
                authority="apex/planner",
            )
        )
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_HARD_EMERGENCY,
                severity=5,
                reason="r2",
                authority="apex/planner",
            )
        )
        active = vm.active()
        assert active is not None
        assert active.veto_type == VETO_HARD_EMERGENCY

    def test_fleet_wide_drone_id_zero(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=0,
                veto_type=VETO_HARD_EMERGENCY,
                severity=5,
                reason="fleet",
                authority="apex/governance",
            )
        )
        active = vm.active()
        assert active is not None
        assert active.drone_id == 0

    def test_valid_until_expiry(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_SOFT_HOLD,
                severity=3,
                reason="r",
                authority="apex/safety",
                valid_until=101.0,
                require_clear_ack=False,
            )
        )
        assert vm.active() is not None
        c.tick(2.0)  # now 102.0 > 101.0
        assert vm.active() is None

    def test_require_clear_ack_holds_after_expiry(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_SOFT_HOLD,
                severity=3,
                reason="r",
                authority="apex/safety",
                valid_until=101.0,
                require_clear_ack=True,
            )
        )
        c.tick(2.0)
        assert vm.active() is not None  # still latched

    def test_should_republish_at_1hz(self) -> None:
        c = FakeClock(100.0)
        vm = VetoManager(clock=c)
        vm.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_SOFT_HOLD,
                severity=3,
                reason="r",
                authority="apex/safety",
            )
        )
        assert vm.should_republish() is True
        vm._last_republish = 100.0
        c.tick(0.5)
        assert vm.should_republish() is False
        c.tick(0.6)
        assert vm.should_republish() is True


class TestVetoIntegration:
    def test_hard_veto_blocks_offboard_sequence(self) -> None:
        c = FakeClock(100.0)
        a = make_adapter(drone_id=1, clock=c)
        a.veto_manager.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_HARD_EMERGENCY,
                severity=5,
                reason="r",
                authority="apex/governance",
            )
        )
        result = a.begin_takeoff_sequence()
        assert result is False  # blocked by hard veto
        assert a.sequence_state == "IDLE"


# ---------------------------------------------------------------------------
# Mode transition sequence
# ---------------------------------------------------------------------------


class TestModeSequence:
    def test_guided_then_offboard_px4(self) -> None:
        c = FakeClock(100.0)
        a = make_adapter(drone_id=1, clock=c, firmware="px4")
        a.publish_offboard_setpoint(vx=1.0)  # establish setpoint stream
        a.sequence_state = "IDLE"
        assert a.begin_takeoff_sequence() is True
        # sequence advances GUIDED -> OFFBOARD -> ARM -> TAKEOFF
        assert a.sequence_state in ("TAKEOFF", "ARMED")

    def test_ardupilot_skips_offboard(self) -> None:
        c = FakeClock(100.0)
        a = make_adapter(drone_id=1, clock=c, firmware="ardupilot")
        a.begin_takeoff_sequence()
        assert a.sequence_state in ("TAKEOFF", "ARMED")

    def test_mode_command_published_for_transition(self) -> None:
        c = FakeClock(100.0)
        a = make_adapter(drone_id=1, clock=c)
        a.begin_takeoff_sequence()
        mode_cmds = [m for _, m in a._published if isinstance(m, ModeCommand)]
        assert any(m.target_mode == MODE_GUIDED for m in mode_cmds)

    def test_arm_requires_no_hard_veto(self) -> None:
        c = FakeClock(100.0)
        a = make_adapter(drone_id=1, clock=c)
        a.veto_manager.issue(
            Veto(
                drone_id=1,
                veto_type=VETO_HARD_EMERGENCY,
                severity=5,
                reason="r",
                authority="apex/governance",
            )
        )
        a.sequence_state = "OFFBOARD"
        assert a._attempt_arm() is False
        assert a.armed is False

    def test_guidance_requires_setpoints_before_offboard_px4(self) -> None:
        c = FakeClock(100.0)
        a = make_adapter(drone_id=1, clock=c, firmware="px4")
        # no setpoints published
        a.sequence_state = "GUIDED"
        assert a._attempt_offboard() is False
        assert a.sequence_state == "GUIDED"


# ---------------------------------------------------------------------------
# MAVLink parity
# ---------------------------------------------------------------------------


class TestMavlinkParity:
    def test_offboard_position_maps_to_set_position_target_local_ned(self) -> None:
        m = OffboardSetpoint(
            drone_id=1, setpoint_type=SETPOINT_TYPE_POSITION_NED, x=1.0, y=2.0, z=3.0
        )
        parity = mavlink_parity(m)
        assert parity["message"] == "SET_POSITION_TARGET_LOCAL_NED"

    def test_mode_command_maps_to_do_set_mode(self) -> None:
        m = ModeCommand(drone_id=1, target_mode=MODE_OFFBOARD)
        parity = mavlink_parity(m)
        assert parity["command"] == "MAV_CMD_DO_SET_MODE"

    def test_arm_maps_to_component_arm_disarm(self) -> None:
        parity = mavlink_parity("ARM")
        assert parity["command"] == "MAV_CMD_COMPONENT_ARM_DISARM"

    def test_takeoff_maps_to_nav_takeoff(self) -> None:
        parity = mavlink_parity("TAKEOFF")
        assert parity["command"] == "MAV_CMD_NAV_TAKEOFF"

    def test_land_maps_to_nav_land(self) -> None:
        parity = mavlink_parity("LAND")
        assert parity["command"] == "MAV_CMD_NAV_LAND"

    def test_hard_emergency_maps_to_land_then_disarm(self) -> None:
        parity = mavlink_parity("HARD_EMERGENCY")
        assert parity["command"] == "MAV_CMD_NAV_LAND"
        assert "disarm" in parity
