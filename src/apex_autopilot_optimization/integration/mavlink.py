"""MAVLink protocol bridge for vehicle communication.

Provides a concrete implementation of VehicleInterface using the MAVLink
micro air vehicle communication protocol. Supports both real hardware
connections via pymavlink and a simulation mode for testing and
development without physical vehicles.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.integration.vehicle import VehicleInterface

logger = logging.getLogger(__name__)

# MAVLink mode mappings for common autopilot firmware
MAVLINK_MODE_MAP: dict[str, int] = {
    "STABILIZE": 0,
    "ACRO": 1,
    "ALT_HOLD": 2,
    "AUTO": 3,
    "GUIDED": 4,
    "LOITER": 5,
    "RTL": 6,
    "CIRCLE": 7,
    "LAND": 9,
    "DRIFT": 11,
    "SPORT": 13,
    "FLIP": 14,
    "POSHOLD": 16,
    "BRAKE": 17,
    "THROW": 18,
    "AVOID_ADSB": 19,
    "GUIDED_NOGPS": 20,
    "SMART_RTL": 21,
    "FLOWHOLD": 22,
    "FOLLOW": 23,
    "ZIGZAG": 24,
    "SYSTEMID": 25,
    "AUTOROTATE": 26,
    "AUTO_RTL": 27,
    "TURTLE": 28,
}

# Reverse mapping for mode name lookup
MAVLINK_MODE_REVERSE: dict[int, str] = {v: k for k, v in MAVLINK_MODE_MAP.items()}


class MAVLinkBridge(VehicleInterface):
    """MAVLink-based vehicle interface implementation.

    Supports connection to real vehicles via pymavlink or simulation mode
    for testing. In simulation mode, all state and telemetry data is
    generated internally without requiring pymavlink or physical hardware.

    Attributes:
        connection_string: The URI used for the current/last connection.
        simulation_mode: Whether operating without pymavlink hardware.
    """

    def __init__(
        self,
        connection_string: str = "",
        simulation: bool = False,
        system_id: int = 1,
        component_id: int = 1,
    ) -> None:
        """Initialize the MAVLink bridge.

        Args:
            connection_string: MAVLink connection URI (e.g., "udp:127.0.0.1:14550").
            simulation: Force simulation mode even if pymavlink is available.
            system_id: MAVLink system ID for this component.
            component_id: MAVLink component ID for this component.
        """
        self._connection_string = connection_string
        self._system_id = system_id
        self._component_id = component_id
        self._connected = False
        self._simulation = simulation
        self._master: Any = None  # pymavlink connection object
        self._current_state = self._default_state()
        self._current_mode = "STABILIZE"
        self._armed = False
        self._telemetry: dict[str, Any] = {}
        self._last_heartbeat = 0.0
        self._message_count = 0

        # Try to import pymavlink; fall back to simulation if unavailable
        self._pymavlink_available = False
        if not simulation:
            try:
                import pymavlink  # type: ignore[import-not-found] # noqa: F401

                self._pymavlink_available = True
            except ImportError:
                logger.info("pymavlink not available; using simulation mode")
                self._simulation = True

    @property
    def connection_string(self) -> str:
        """Return the current connection string."""
        return self._connection_string

    @property
    def simulation_mode(self) -> bool:
        """Return True if operating in simulation mode."""
        return self._simulation

    @property
    def system_id(self) -> int:
        """Return the MAVLink system ID."""
        return self._system_id

    @property
    def component_id(self) -> int:
        """Return the MAVLink component ID."""
        return self._component_id

    def _default_state(self) -> StateVector:
        """Create a default/zero state vector."""
        return StateVector(
            pose=Pose3D(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
            velocity=Velocity3D(vx=0.0, vy=0.0, vz=0.0),
            timestamp=time.time(),
        )

    def _validate_connection_string(self, conn_str: str) -> bool:
        """Validate a MAVLink connection string format.

        Supported formats:
        - udp:<host>:<port>
        - tcp:<host>:<port>
        - serial:<device>:<baud>
        - udpout:<host>:<port>
        """
        if not conn_str or not isinstance(conn_str, str):
            return False
        valid_prefixes = ("udp:", "tcp:", "serial:", "udpout:")
        return conn_str.startswith(valid_prefixes)

    def connect(self, connection_string: str) -> bool:
        """Establish MAVLink connection to the vehicle.

        Args:
            connection_string: MAVLink URI (e.g., "udp:127.0.0.1:14550").

        Returns:
            True if connection established successfully.

        Raises:
            ConnectionError: If connection string is malformed or vehicle
                is unreachable.
        """
        if not self._validate_connection_string(connection_string):
            raise ConnectionError(
                f"Invalid MAVLink connection string: {connection_string!r}. "
                "Expected format: udp:<host>:<port>, tcp:<host>:<port>, "
                "or serial:<device>:<baud>"
            )

        self._connection_string = connection_string

        if self._simulation:
            self._connected = True
            self._current_state = self._default_state()
            self._telemetry = self._generate_simulated_telemetry()
            logger.info("MAVLink simulation connection established to %s", connection_string)
            return True

        # Real hardware connection via pymavlink
        try:
            from pymavlink import mavutil

            self._master = mavutil.mavlink_connection(connection_string)
            # Wait for heartbeat to confirm connection
            self._master.wait_heartbeat(timeout=10)
            self._connected = True
            self._last_heartbeat = time.time()
            logger.info(
                "MAVLink connection established to %s (system=%d, component=%d)",
                connection_string,
                self._master.target_system,
                self._master.target_component,
            )
            return True
        except Exception as exc:
            self._connected = False
            raise ConnectionError(
                f"Failed to connect to MAVLink vehicle at {connection_string}: {exc}"
            ) from exc

    def disconnect(self) -> bool:
        """Close the MAVLink connection.

        Returns:
            True if disconnection was successful.
        """
        if self._master is not None:
            try:
                self._master.close()
            except Exception as exc:
                logger.warning("Error closing MAVLink connection: %s", exc)
            finally:
                self._master = None

        self._connected = False
        self._armed = False
        self._current_mode = "STABILIZE"
        self._current_state = self._default_state()
        self._telemetry = {}
        logger.info("MAVLink connection closed")
        return True

    def get_state(self) -> StateVector:
        """Retrieve current vehicle state from MAVLink messages.

        Returns:
            Current state vector with pose, velocity, and timestamp.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            return self._current_state

        # Parse real MAVLink messages
        try:
            msg = self._master.recv_match(
                type=["GLOBAL_POSITION_INT", "ATTITUDE", "VFR_HUD"],
                blocking=False,
            )
            if msg is not None:
                self._message_count += 1
                self._update_state_from_message(msg)
        except Exception as exc:
            logger.warning("Error reading MAVLink state: %s", exc)

        return self._current_state

    def send_control(self, control: ControlInput) -> bool:
        """Send RC override or position target via MAVLink.

        Args:
            control: Control input with throttle and rate commands.

        Returns:
            True if command was sent successfully.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            # In simulation, update internal state based on control
            self._current_state = StateVector(
                pose=Pose3D(
                    x=self._current_state.pose.x + control.throttle * 0.1,
                    y=self._current_state.pose.y + control.roll_rate * 0.01,
                    z=self._current_state.pose.z + control.pitch_rate * 0.01,
                    roll=control.roll_rate,
                    pitch=control.pitch_rate,
                    yaw=self._current_state.pose.yaw + control.yaw_rate * 0.01,
                ),
                velocity=Velocity3D(
                    vx=control.throttle * 5.0,
                    vy=control.roll_rate * 2.0,
                    vz=control.pitch_rate * 2.0,
                    vroll=control.roll_rate,
                    vpitch=control.pitch_rate,
                    vyaw=control.yaw_rate,
                ),
                timestamp=time.time(),
            )
            return True

        try:
            # Send RC channel override
            self._master.mav.rc_channels_override_send(
                self._master.target_system,
                self._master.target_component,
                int(control.throttle * 1000 + 1000),
                int(control.roll_rate * 500 + 1500),
                int(control.pitch_rate * 500 + 1500),
                int(control.yaw_rate * 500 + 1500),
                0, 0, 0, 0,
            )
            return True
        except Exception as exc:
            logger.error("Failed to send MAVLink control: %s", exc)
            return False

    def arm(self) -> bool:
        """Arm the vehicle motors via MAVLink command.

        Returns:
            True if arming command was accepted.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            self._armed = True
            logger.info("MAVLink simulation: vehicle armed")
            return True

        try:
            self._master.mav.command_long_send(
                self._master.target_system,
                self._master.target_component,
                400,  # MAV_CMD_COMPONENT_ARM_DISARM
                0,
                1,  # arm
                0, 0, 0, 0, 0, 0,
            )
            self._armed = True
            return True
        except Exception as exc:
            logger.error("Failed to arm via MAVLink: %s", exc)
            return False

    def set_mode(self, mode: str) -> bool:
        """Set vehicle flight mode via MAVLink.

        Args:
            mode: Flight mode name (e.g., "GUIDED", "LOITER", "AUTO").

        Returns:
            True if mode change command was accepted.

        Raises:
            RuntimeError: If not connected.
            ValueError: If mode is not recognized.
        """
        self._ensure_connected()

        mode_upper = mode.upper()
        if mode_upper not in MAVLINK_MODE_MAP:
            raise ValueError(
                f"Unknown MAVLink mode: {mode!r}. "
                f"Supported modes: {sorted(MAVLINK_MODE_MAP.keys())}"
            )

        if self._simulation:
            self._current_mode = mode_upper
            logger.info("MAVLink simulation: mode set to %s", mode_upper)
            return True

        try:
            mode_id = MAVLINK_MODE_MAP[mode_upper]
            self._master.mav.set_mode_send(
                self._master.target_system,
                1,  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
                mode_id,
            )
            self._current_mode = mode_upper
            return True
        except Exception as exc:
            logger.error("Failed to set MAVLink mode: %s", exc)
            return False

    def get_telemetry(self) -> dict[str, Any]:
        """Retrieve telemetry data from the vehicle.

        Returns:
            Dictionary with telemetry fields including battery, GPS,
            signal quality, and error counts.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            return self._generate_simulated_telemetry()

        telemetry: dict[str, Any] = {
            "timestamp": time.time(),
            "message_count": self._message_count,
            "mode": self._current_mode,
            "armed": self._armed,
        }

        try:
            # Request and parse telemetry messages
            for msg_type in ["SYS_STATUS", "GPS_RAW_INT", "VFR_HUD", "ATTITUDE"]:
                msg = self._master.recv_match(type=msg_type, blocking=False)
                if msg is not None:
                    self._update_telemetry_from_message(telemetry, msg)
        except Exception as exc:
            logger.warning("Error reading MAVLink telemetry: %s", exc)

        return telemetry

    def is_connected(self) -> bool:
        """Check if MAVLink connection is active.

        Returns:
            True if connected, False otherwise.
        """
        if self._simulation:
            return self._connected

        if self._master is None:
            return False

        # Check heartbeat timeout (5 seconds)
        if time.time() - self._last_heartbeat > 5.0:
            self._connected = False
            return False

        return self._connected

    def _ensure_connected(self) -> None:
        """Raise RuntimeError if not connected."""
        if not self._connected:
            raise RuntimeError("MAVLink bridge is not connected to a vehicle")

    def _update_state_from_message(self, msg: Any) -> None:
        """Update internal state from a MAVLink message."""
        msg_type = msg.get_type()
        if msg_type == "GLOBAL_POSITION_INT":
            self._current_state = StateVector(
                pose=Pose3D(
                    x=msg.lat / 1e7,
                    y=msg.lon / 1e7,
                    z=msg.relative_alt / 1000.0,
                    yaw=msg.hdg / 100.0 if msg.hdg != 0 else 0.0,
                ),
                velocity=Velocity3D(
                    vx=msg.vx / 100.0,
                    vy=msg.vy / 100.0,
                    vz=msg.vz / 100.0,
                ),
                timestamp=time.time(),
            )
        elif msg_type == "ATTITUDE":
            self._current_state = StateVector(
                pose=Pose3D(
                    x=self._current_state.pose.x,
                    y=self._current_state.pose.y,
                    z=self._current_state.pose.z,
                    roll=msg.roll,
                    pitch=msg.pitch,
                    yaw=msg.yaw,
                ),
                velocity=self._current_state.velocity,
                timestamp=time.time(),
            )

    def _update_telemetry_from_message(self, telemetry: dict[str, Any], msg: Any) -> None:
        """Update telemetry dict from a MAVLink message."""
        msg_type = msg.get_type()
        if msg_type == "SYS_STATUS":
            telemetry["battery_voltage"] = msg.voltage_battery / 1000.0
            telemetry["battery_remaining"] = msg.battery_remaining
        elif msg_type == "GPS_RAW_INT":
            telemetry["gps_satellites"] = msg.satellites_visible
            telemetry["gps_fix_type"] = msg.fix_type
        elif msg_type == "VFR_HUD":
            telemetry["groundspeed"] = msg.groundspeed
            telemetry["heading"] = msg.heading
            telemetry["throttle"] = msg.throttle
        elif msg_type == "ATTITUDE":
            telemetry["roll"] = msg.roll
            telemetry["pitch"] = msg.pitch
            telemetry["yaw"] = msg.yaw

    def _generate_simulated_telemetry(self) -> dict[str, Any]:
        """Generate simulated telemetry data for testing."""
        return {
            "timestamp": time.time(),
            "battery_voltage": 12.6,
            "battery_remaining": 85,
            "gps_satellites": 12,
            "gps_fix_type": 3,
            "groundspeed": 5.2,
            "heading": 90,
            "throttle": 45,
            "mode": self._current_mode,
            "armed": self._armed,
            "message_count": self._message_count,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 1.57,
        }
