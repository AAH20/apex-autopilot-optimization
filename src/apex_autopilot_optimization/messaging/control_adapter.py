"""Control / setpoint ROS2 adapter for the apex -> AAS setpoint contract.

Publishes :class:`OffboardSetpoint`, :class:`FormationSetpoint`,
:class:`WTAAssignment`, :class:`ModeCommand` and :class:`Veto` messages to the
namespaced ``/Drone{id}/...`` topics defined in ``docs/setpoint-contract.md``.

The adapter is deliberately ROS2-agnostic: it accepts an optional ``publishers``
mapping of ``topic -> publisher-like`` objects (each exposing ``.publish(msg)``,
e.g. a mock in tests or a real rclpy publisher in production) and a pluggable
``clock``. When no publishers are supplied it still records every outbound
message to :attr:`_published`, which is sufficient for unit testing without
rclpy or a running ROS2 daemon.

MAVLink parity (``docs/setpoint-contract.md`` §9) is provided by
:func:`mavlink_parity`, which maps each contract signal to the equivalent
MAVLink command/message for the MAVLinkBridge path.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from apex_autopilot_optimization.messaging.veto_manager import (
    VETO_CLEAR,
    VETO_HARD_EMERGENCY,
    VETO_SOFT_HOLD,  # noqa: F401 - re-exported for test import
    Veto,
    VetoManager,
)
from apex_autopilot_optimization.messaging.watchdog import SetpointWatchdog

# ---------------------------------------------------------------------------
# Contract constants (mirror apex_control_msgs / setpoint-contract.md)
# ---------------------------------------------------------------------------

# OffboardSetpoint.setpoint_type
SETPOINT_TYPE_UNSET = 0
SETPOINT_TYPE_VELOCITY_NED = 1
SETPOINT_TYPE_POSITION_NED = 2
SETPOINT_TYPE_ACCELERATION_NED = 3
SETPOINT_TYPE_BODY_RATES = 4

# OffboardSetpoint.frame
FRAME_NED = 0
FRAME_BODY_FRD = 1

# ModeCommand.target_mode (setpoint-contract.md §3.3.4)
MODE_STABILIZE = 0
MODE_ACRO = 1
MODE_ALT_HOLD = 2
MODE_AUTO = 3
MODE_GUIDED = 4
MODE_OFFBOARD = 5
MODE_LOITER = 6
MODE_RTL = 7
MODE_LAND = 8
MODE_POSHOLD = 9
MODE_HOLD = 10
# Adapter-internal pseudo-modes used by the takeoff sequence (ARM / TAKEOFF are
# expressed as MAVLink commands / action goals rather than a ModeCommand mode).
MODE_ARM = 11
MODE_TAKEOFF = 12

# Topic groups
TOPIC_OFFBOARD_SETPOINT = "/Drone{id}/offboard/setpoint"
TOPIC_FORMATION_SETPOINT = "/Drone{id}/formation/setpoint"
TOPIC_WTA_ASSIGNMENT = "/Drone{id}/wta/assignment"
TOPIC_FLEET_WTA_ASSIGNMENT = "/fleet/wta/assignments"
TOPIC_MODE_COMMAND = "/Drone{id}/mode/command"
TOPIC_VETO = "/Drone{id}/safety/veto"

DEFAULT_FRAME_ID = "ned"
HEARTBEAT_INTERVAL_SEC = 0.1  # 10 Hz


# ---------------------------------------------------------------------------
# Contract message dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Header:
    """std_msgs/Header analogue: stamp (ROS2/sim time) and frame_id."""

    stamp: float = 0.0
    frame_id: str = ""


@dataclass
class OffboardSetpoint:
    """Continuous offboard setpoint (>= 10 Hz while OFFBOARD)."""

    header: Header = field(default_factory=Header)
    drone_id: int = 0
    setpoint_type: int = SETPOINT_TYPE_UNSET
    frame: int = FRAME_NED
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    yaw_rate: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    az: float = 0.0
    yaw: float = 0.0
    duration_sec: float = 0.0


@dataclass
class FormationSetpoint:
    """Per-drone formation position target (10 Hz)."""

    header: Header = field(default_factory=Header)
    drone_id: int = 0
    formation_id: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw: float = 0.0
    spacing_m: float = 0.0
    slot_valid: bool = True


@dataclass
class WTAAssignment:
    """Winner-takes-all task assignment (event-driven, <= 1 Hz republish)."""

    header: Header = field(default_factory=Header)
    task_id: int = 0
    assigned_drone_id: int = 0
    previous_drone_id: int = 0
    priority: float = 0.0
    task_x: float = 0.0
    task_y: float = 0.0
    task_z: float = 0.0
    assign_time: float = 0.0
    status: int = 0  # 0=PROPOSED,1=ACKED,2=REJECTED,3=COMPLETED,4=EXPIRED


@dataclass
class ModeCommand:
    """Explicit flight mode change (event-driven, retry 1 Hz)."""

    header: Header = field(default_factory=Header)
    drone_id: int = 0
    target_mode: int = MODE_STABILIZE
    mode_source: str = "apex/governance"
    timeout_sec: float = 5.0


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class ControlAdapter:
    """ROS2 adapter publishing apex setpoint / command / veto contract messages.

    Args:
        drone_id: The drone id (== DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID).
        publishers: Optional mapping ``topic -> publisher`` where each publisher
            exposes ``.publish(msg)``. A mock publisher works for tests.
        clock: Callable returning current time (defaults to ``time.time``).
        firmware: ``"px4"`` (default) or ``"ardupilot"``. ArduPilot has no
            OFFBOARD equivalent and skips that step in the takeoff sequence.
    """

    def __init__(
        self,
        drone_id: int,
        publishers: dict[str, Any] | None = None,
        clock: Callable[[], float] = time.time,
        firmware: str = "px4",
    ) -> None:
        self.drone_id = int(drone_id)
        self._publishers = dict(publishers or {})
        self._clock = clock
        self._firmware = firmware.lower()

        # Tracked vehicle state.
        self.mode = "STABILIZE"
        self.armed = False
        self.sequence_state = "IDLE"  # IDLE | GUIDED | OFFBOARD | ARMED | TAKEOFF | HOLD

        # Sub-components.
        self.watchdog = SetpointWatchdog(timeout_sec=0.5, clock=self._clock)
        self.veto_manager = VetoManager(clock=self._clock)

        # Heartbeat (10 Hz offboard setpoint) state.
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_setpoint: OffboardSetpoint | None = None
        self._last_offboard_setpoint: OffboardSetpoint | None = None
        self._heartbeat_interval = HEARTBEAT_INTERVAL_SEC
        self._last_heartbeat_ts: float = 0.0

        # History of every outbound (topic, message) pair — useful in tests.
        self._published: list[tuple[str, object]] = []

    # -- publishing ---------------------------------------------------------

    def _publish(self, topic: str, msg: object) -> None:
        publisher = self._publishers.get(topic)
        if publisher is not None:
            publisher.publish(msg)
        self._published.append((topic, msg))

    def _topic(self, pattern: str) -> str:
        return pattern.format(id=self.drone_id)

    def _now(self) -> float:
        return float(self._clock())

    def _stamp(self) -> float:
        return self._now()

    # -- offboard setpoint --------------------------------------------------

    def publish_offboard_setpoint(
        self,
        *,
        vx: float = 0.0,
        vy: float = 0.0,
        vz: float = 0.0,
        yaw_rate: float = 0.0,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        ax: float = 0.0,
        ay: float = 0.0,
        az: float = 0.0,
        yaw: float = 0.0,
        setpoint_type: int = SETPOINT_TYPE_VELOCITY_NED,
        frame: int = FRAME_NED,
        duration_sec: float = 0.0,
        stamp: float | None = None,
    ) -> OffboardSetpoint:
        """Publish a single offboard setpoint and refresh the watchdog."""
        msg = OffboardSetpoint(
            header=Header(
                stamp=self._stamp() if stamp is None else stamp, frame_id=DEFAULT_FRAME_ID
            ),
            drone_id=self.drone_id,
            setpoint_type=setpoint_type,
            frame=frame,
            vx=vx,
            vy=vy,
            vz=vz,
            yaw_rate=yaw_rate,
            x=x,
            y=y,
            z=z,
            ax=ax,
            ay=ay,
            az=az,
            yaw=yaw,
            duration_sec=duration_sec,
        )
        self._publish(self._topic(TOPIC_OFFBOARD_SETPOINT), msg)
        self.watchdog.record_setpoint(msg.header.stamp)
        self._last_offboard_setpoint = msg
        return msg

    def publish_heartbeat(self) -> OffboardSetpoint | None:
        """Publish the last valid offboard setpoint as a heartbeat tick.

        Returns the message published, or None if no setpoint has ever been
        published.
        """
        template = self._heartbeat_setpoint or self._last_offboard_setpoint
        if template is None:
            return None
        msg = OffboardSetpoint(
            header=Header(stamp=self._stamp(), frame_id=DEFAULT_FRAME_ID),
            drone_id=template.drone_id,
            setpoint_type=template.setpoint_type,
            frame=template.frame,
            vx=template.vx,
            vy=template.vy,
            vz=template.vz,
            yaw_rate=template.yaw_rate,
            x=template.x,
            y=template.y,
            z=template.z,
            ax=template.ax,
            ay=template.ay,
            az=template.az,
            yaw=template.yaw,
            duration_sec=template.duration_sec,
        )
        self._publish(self._topic(TOPIC_OFFBOARD_SETPOINT), msg)
        self.watchdog.record_setpoint(msg.header.stamp)
        self._last_heartbeat_ts = msg.header.stamp
        return msg

    # -- formation setpoint -------------------------------------------------

    def publish_formation_setpoint(
        self,
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        yaw: float = 0.0,
        spacing_m: float = 0.0,
        slot_valid: bool = True,
        formation_id: int = 0,
        stamp: float | None = None,
    ) -> FormationSetpoint:
        msg = FormationSetpoint(
            header=Header(
                stamp=self._stamp() if stamp is None else stamp, frame_id=DEFAULT_FRAME_ID
            ),
            drone_id=self.drone_id,
            formation_id=formation_id,
            x=x,
            y=y,
            z=z,
            yaw=yaw,
            spacing_m=spacing_m,
            slot_valid=slot_valid,
        )
        self._publish(self._topic(TOPIC_FORMATION_SETPOINT), msg)
        return msg

    # -- WTA assignment -----------------------------------------------------

    def publish_wta_assignment(
        self,
        *,
        task_id: int = 0,
        assigned_drone_id: int = 0,
        previous_drone_id: int = 0,
        priority: float = 0.0,
        task_x: float = 0.0,
        task_y: float = 0.0,
        task_z: float = 0.0,
        assign_time: float | None = None,
        status: int = 0,
        stamp: float | None = None,
    ) -> WTAAssignment:
        msg = WTAAssignment(
            header=Header(
                stamp=self._stamp() if stamp is None else stamp, frame_id=DEFAULT_FRAME_ID
            ),
            task_id=task_id,
            assigned_drone_id=assigned_drone_id,
            previous_drone_id=previous_drone_id,
            priority=priority,
            task_x=task_x,
            task_y=task_y,
            task_z=task_z,
            assign_time=self._stamp() if assign_time is None else assign_time,
            status=status,
        )
        self._publish(TOPIC_WTA_ASSIGNMENT.format(id=assigned_drone_id), msg)
        return msg

    def publish_fleet_wta_assignment(
        self,
        *,
        task_id: int = 0,
        assigned_drone_id: int = 0,
        previous_drone_id: int = 0,
        priority: float = 0.0,
        task_x: float = 0.0,
        task_y: float = 0.0,
        task_z: float = 0.0,
        assign_time: float | None = None,
        status: int = 0,
        stamp: float | None = None,
    ) -> WTAAssignment:
        msg = WTAAssignment(
            header=Header(
                stamp=self._stamp() if stamp is None else stamp, frame_id=DEFAULT_FRAME_ID
            ),
            task_id=task_id,
            assigned_drone_id=assigned_drone_id,
            previous_drone_id=previous_drone_id,
            priority=priority,
            task_x=task_x,
            task_y=task_y,
            task_z=task_z,
            assign_time=self._stamp() if assign_time is None else assign_time,
            status=status,
        )
        self._publish(TOPIC_FLEET_WTA_ASSIGNMENT, msg)
        return msg

    # -- mode command -------------------------------------------------------

    def publish_mode_command(
        self,
        *,
        target_mode: int = MODE_STABILIZE,
        mode_source: str = "apex/governance",
        timeout_sec: float = 5.0,
        stamp: float | None = None,
    ) -> ModeCommand:
        msg = ModeCommand(
            header=Header(
                stamp=self._stamp() if stamp is None else stamp, frame_id=DEFAULT_FRAME_ID
            ),
            drone_id=self.drone_id,
            target_mode=target_mode,
            mode_source=mode_source,
            timeout_sec=timeout_sec,
        )
        self._publish(self._topic(TOPIC_MODE_COMMAND), msg)
        self.mode = _mode_name(target_mode)
        return msg

    # -- veto ---------------------------------------------------------------

    def publish_veto(
        self,
        *,
        veto_type: int = VETO_CLEAR,
        drone_id: int | None = None,
        severity: int = 3,
        reason: str = "",
        authority: str = "operator",
        valid_until: float = 0.0,
        require_clear_ack: bool = False,
        stamp: float | None = None,
    ) -> Veto:
        target_drone = self.drone_id if drone_id is None else int(drone_id)
        msg = Veto(
            drone_id=target_drone,
            veto_type=veto_type,
            severity=severity,
            reason=reason,
            authority=authority,
            valid_until=valid_until,
            require_clear_ack=require_clear_ack,
            stamp=self._stamp() if stamp is None else stamp,
        )
        self.veto_manager.issue(msg, now=msg.stamp)
        self._publish(self._topic(TOPIC_VETO), msg)
        return msg

    def clear_veto(self, authority: str) -> bool:
        return self.veto_manager.clear(authority, now=self._now())

    # -- heartbeat (10 Hz offboard) ----------------------------------------

    def start_heartbeat(
        self,
        *,
        vx: float = 0.0,
        vy: float = 0.0,
        vz: float = 0.0,
        yaw_rate: float = 0.0,
        interval: float = HEARTBEAT_INTERVAL_SEC,
    ) -> None:
        """Arm (and start a background thread for) the 10 Hz offboard heartbeat.

        The last setpoint published via :meth:`publish_offboard_setpoint` is
        re-published every ``interval`` seconds. Call :meth:`stop_heartbeat` to
        stop.
        """
        self.stop_heartbeat()
        self._heartbeat_setpoint = OffboardSetpoint(
            header=Header(stamp=self._stamp(), frame_id=DEFAULT_FRAME_ID),
            drone_id=self.drone_id,
            setpoint_type=SETPOINT_TYPE_VELOCITY_NED,
            frame=FRAME_NED,
            vx=vx,
            vy=vy,
            vz=vz,
            yaw_rate=yaw_rate,
        )
        self._heartbeat_interval = float(interval)
        self._heartbeat_stop.clear()
        self._last_heartbeat_ts = self._now()

        def _loop() -> None:
            while not self._heartbeat_stop.is_set():
                self._heartbeat_stop.wait(self._heartbeat_interval)
                if self._heartbeat_stop.is_set():
                    break
                self.publish_heartbeat()

        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=1.0)
            self._heartbeat_thread = None
        self._heartbeat_setpoint = None

    def tick(self, now: float | None = None) -> None:
        """Advance the adapter by one cycle: heartbeat + watchdog check.

        Called periodically (>= 10 Hz). Publishes a heartbeat if the interval
        has elapsed, then raises a setpoint-loss watchdog event (OFFBOARD ->
        HOLD) when the setpoint stream has lapsed beyond 500 ms.
        """
        now = self._now() if now is None else float(now)

        if (
            self._heartbeat_setpoint is not None
            and (now - self._last_heartbeat_ts) >= self._heartbeat_interval
        ):
            self.publish_heartbeat()

        if self.watchdog.is_lost(now):
            self._handle_setpoint_loss(now)

    # -- setpoint-loss watchdog response -----------------------------------

    def _handle_setpoint_loss(self, now: float) -> None:
        self.watchdog.check(now)
        # Exit OFFBOARD -> HOLD per contract §8.3 / §5.
        if self.mode != "HOLD":
            self.publish_mode_command(target_mode=MODE_HOLD)
        self.mode = "HOLD"
        self.armed = False
        self.sequence_state = "HOLD"

    # -- MAVLink parity -----------------------------------------------------

    @staticmethod
    def mavlink_parity(msg: object) -> dict[str, Any]:
        """Map a contract message (or command name) to its MAVLink equivalent.

        Returns a dict with the MAVLink message/command and relevant params,
        per ``docs/setpoint-contract.md`` §9.
        """
        if isinstance(msg, OffboardSetpoint):
            return _offboard_setpoint_parity(msg)
        if isinstance(msg, ModeCommand):
            return {
                "command": "MAV_CMD_DO_SET_MODE",
                "custom_mode": msg.target_mode,
                "mavlink_mode_map": {
                    "STABILIZE": 0,
                    "ACRO": 1,
                    "ALT_HOLD": 2,
                    "AUTO": 3,
                    "GUIDED": 4,
                    "OFFBOARD": 5,
                    "LOITER": 6,
                    "RTL": 7,
                    "LAND": 8,
                    "POSHOLD": 9,
                    "HOLD": 10,
                },
            }
        if isinstance(msg, str):
            upper = msg.upper()
            if upper == "ARM":
                return {"command": "MAV_CMD_COMPONENT_ARM_DISARM", "param1": 1}
            if upper == "DISARM":
                return {"command": "MAV_CMD_COMPONENT_ARM_DISARM", "param1": 0}
            if upper == "TAKEOFF":
                return {"command": "MAV_CMD_NAV_TAKEOFF"}
            if upper == "LAND":
                return {"command": "MAV_CMD_NAV_LAND"}
            if upper == "REPOSITION":
                return {"command": "MAV_CMD_DO_REPOSITION"}
            if upper == "HARD_EMERGENCY":
                return {
                    "command": "MAV_CMD_NAV_LAND",
                    "disarm": True,
                    "disarm_after_landing": True,
                    "cancel_action_goals": True,
                }
        return {"command": None}

    # -- mode transition sequence GUIDED -> OFFBOARD -> ARM -> TAKEOFF -----

    def begin_takeoff_sequence(self) -> bool:
        """Run the contract-mandated launch sequence.

        GUIDED -> (OFFBOARD, PX4 only) -> ARM -> TAKEOFF, each with per-step
        preconditions. Returns True when the full sequence completed; False if
        blocked (e.g. by a HARD veto or missing setpoints).
        """
        if self.veto_manager.veto_type() == VETO_HARD_EMERGENCY:
            self.sequence_state = "IDLE"
            return False

        # 1. GUIDED
        if not self._attempt_guided():
            return False
        # 2. OFFBOARD (PX4 only)
        if self._firmware == "px4" and not self._attempt_offboard():
            return False
        # 3. ARM
        if not self._attempt_arm():
            return False
        # 4. TAKEOFF
        return self._attempt_takeoff()

    def _attempt_guided(self) -> bool:
        if self.veto_manager.veto_type() == VETO_HARD_EMERGENCY:
            return False
        self.publish_mode_command(target_mode=MODE_GUIDED)
        self.mode = "GUIDED"
        self.sequence_state = "GUIDED"
        return True

    def _attempt_offboard(self) -> bool:
        # PX4 requires the offboard setpoint stream established before the mode
        # switch. A cold bridge (no setpoint ever received) or a watchdog loss
        # both mean the stream is not established.
        if self.watchdog.last_setpoint_ts is None:
            return False
        if self.watchdog.is_lost():
            return False
        self.publish_mode_command(target_mode=MODE_OFFBOARD)
        self.mode = "OFFBOARD"
        self.sequence_state = "OFFBOARD"
        return True

    def _attempt_arm(self) -> bool:
        if self.veto_manager.veto_type() == VETO_HARD_EMERGENCY:
            return False
        if self.mode not in ("GUIDED", "OFFBOARD"):
            return False
        # MAVLink parity: MAV_CMD_COMPONENT_ARM_DISARM (param1=1).
        self.armed = True
        self.sequence_state = "ARMED"
        return True

    def _attempt_takeoff(self) -> bool:
        if not self.armed:
            return False
        if self.veto_manager.veto_type() == VETO_HARD_EMERGENCY:
            return False
        # MAVLink parity: MAV_CMD_NAV_TAKEOFF (via takeoff action goal).
        self.sequence_state = "TAKEOFF"
        return True


def _mode_name(mode: int) -> str:
    names = {
        MODE_STABILIZE: "STABILIZE",
        MODE_ACRO: "ACRO",
        MODE_ALT_HOLD: "ALT_HOLD",
        MODE_AUTO: "AUTO",
        MODE_GUIDED: "GUIDED",
        MODE_OFFBOARD: "OFFBOARD",
        MODE_LOITER: "LOITER",
        MODE_RTL: "RTL",
        MODE_LAND: "LAND",
        MODE_POSHOLD: "POSHOLD",
        MODE_HOLD: "HOLD",
        MODE_ARM: "ARM",
        MODE_TAKEOFF: "TAKEOFF",
    }
    return names.get(mode, f"MODE_{mode}")


def mavlink_parity(msg: object) -> dict[str, Any]:
    """Map a contract message (or command name) to its MAVLink equivalent.

    Module-level convenience wrapper around :meth:`ControlAdapter.mavlink_parity`,
    per ``docs/setpoint-contract.md`` §9.
    """
    return ControlAdapter.mavlink_parity(msg)


def _offboard_setpoint_parity(msg: OffboardSetpoint) -> dict[str, Any]:
    type_mask = 0  # position+velocity+acceleration+yaw all used (simplified)
    if msg.setpoint_type == SETPOINT_TYPE_VELOCITY_NED:
        type_mask = 0b0000111111110000  # velocity-only
    elif msg.setpoint_type == SETPOINT_TYPE_POSITION_NED:
        type_mask = 0b0000111111000111  # position-only
    elif msg.setpoint_type == SETPOINT_TYPE_BODY_RATES:
        return {
            "message": "SET_ATTITUDE_TARGET",
            "body_rate": True,
            "frame": msg.frame,
        }
    return {
        "message": "SET_POSITION_TARGET_LOCAL_NED",
        "type_mask": type_mask,
        "frame": msg.frame,
        "x": msg.x,
        "y": msg.y,
        "z": msg.z,
        "vx": msg.vx,
        "vy": msg.vy,
        "vz": msg.vz,
        "yaw": msg.yaw,
        "yaw_rate": msg.yaw_rate,
    }
