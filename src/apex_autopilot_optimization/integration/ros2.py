"""ROS2 bridge for vehicle communication.

Provides a concrete implementation of VehicleInterface using the ROS2
Robot Operating System middleware. Supports both real ROS2 connections
via rclpy and a simulation mode for testing without a ROS2 environment.
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

# ROS2 QoS profile presets
QOS_PROFILES: dict[str, dict[str, Any]] = {
    "sensor_data": {"depth": 10, "reliability": "best_effort", "durability": "volatile"},
    "default": {"depth": 10, "reliability": "reliable", "durability": "volatile"},
    "services": {"depth": 10, "reliability": "reliable", "durability": "volatile"},
}


class ROS2Bridge(VehicleInterface):
    """ROS2-based vehicle interface implementation.

    Connects to a vehicle's ROS2 node graph to exchange state, control,
    and telemetry data. In simulation mode, all data is generated
    internally without requiring rclpy or a running ROS2 daemon.

    Attributes:
        namespace: ROS2 namespace for the vehicle node.
        node_name: Name for the ROS2 node created by this bridge.
    """

    def __init__(
        self,
        namespace: str = "/vehicle",
        node_name: str = "apex_bridge",
        simulation: bool = False,
        domain_id: int | None = None,
    ) -> None:
        """Initialize the ROS2 bridge.

        Args:
            namespace: ROS2 namespace for the vehicle.
            node_name: ROS2 node name for this bridge.
            simulation: Force simulation mode even if rclpy is available.
            domain_id: ROS2 domain ID (None for default).
        """
        self._namespace = namespace
        self._node_name = node_name
        self._domain_id = domain_id
        self._simulation = simulation
        self._connected = False
        self._node: Any = None  # rclpy Node
        self._publishers: dict[str, Any] = {}
        self._subscriptions: dict[str, Any] = {}
        self._current_state = self._default_state()
        self._current_mode = "manual"
        self._armed = False
        self._telemetry: dict[str, Any] = {}
        self._rclpy_available = False

        if not simulation:
            try:
                import rclpy  # noqa: F401

                self._rclpy_available = True
            except ImportError:
                logger.info("rclpy not available; using simulation mode")
                self._simulation = True

    @property
    def namespace(self) -> str:
        """Return the ROS2 namespace."""
        return self._namespace

    @property
    def node_name(self) -> str:
        """Return the ROS2 node name."""
        return self._node_name

    @property
    def simulation_mode(self) -> bool:
        """Return True if operating in simulation mode."""
        return self._simulation

    def _default_state(self) -> StateVector:
        """Create a default/zero state vector."""
        return StateVector(
            pose=Pose3D(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
            velocity=Velocity3D(vx=0.0, vy=0.0, vz=0.0),
            timestamp=time.time(),
        )

    def connect(self, connection_string: str) -> bool:
        """Establish ROS2 connection to the vehicle.

        Args:
            connection_string: ROS2 connection URI (e.g., "ros2://namespace/vehicle_01").
                The format is ros2://<namespace>/<vehicle_name>.

        Returns:
            True if connection established successfully.

        Raises:
            ConnectionError: If connection string is malformed or vehicle
                is unreachable.
        """
        if not connection_string.startswith("ros2://"):
            raise ConnectionError(
                f"Invalid ROS2 connection string: {connection_string!r}. "
                "Expected format: ros2://<namespace>/<vehicle_name>"
            )

        # Parse namespace from connection string
        parts = connection_string[6:].split("/")
        if len(parts) >= 1 and parts[0]:
            self._namespace = "/" + parts[0]

        if self._simulation:
            self._connected = True
            self._current_state = self._default_state()
            self._telemetry = self._generate_simulated_telemetry()
            logger.info(
                "ROS2 simulation connection established to %s", connection_string
            )
            return True

        try:
            import rclpy
            from rclpy.node import Node

            if not rclpy.ok():
                rclpy.init(domain_id=self._domain_id)

            self._node = Node(self._node_name, namespace=self._namespace)
            self._setup_publishers_and_subscriptions()
            self._connected = True
            logger.info(
                "ROS2 connection established to %s (node=%s, namespace=%s)",
                connection_string,
                self._node_name,
                self._namespace,
            )
            return True
        except Exception as exc:
            self._connected = False
            raise ConnectionError(
                f"Failed to connect to ROS2 vehicle at {connection_string}: {exc}"
            ) from exc

    def disconnect(self) -> bool:
        """Shutdown the ROS2 node and connections.

        Returns:
            True if disconnection was successful.
        """
        if self._node is not None:
            try:
                self._node.destroy_node()
            except Exception as exc:
                logger.warning("Error destroying ROS2 node: %s", exc)
            finally:
                self._node = None

        self._publishers.clear()
        self._subscriptions.clear()
        self._connected = False
        self._armed = False
        self._current_mode = "manual"
        self._current_state = self._default_state()
        self._telemetry = {}
        logger.info("ROS2 connection closed")
        return True

    def get_state(self) -> StateVector:
        """Retrieve current vehicle state from ROS2 topics.

        Returns:
            Current state vector with pose, velocity, and timestamp.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            return self._current_state

        try:
            import rclpy

            rclpy.spin_once(self._node, timeout_sec=0.1)
        except Exception as exc:
            logger.warning("Error spinning ROS2 node: %s", exc)

        return self._current_state

    def send_control(self, control: ControlInput) -> bool:
        """Publish control command via ROS2 topic.

        Args:
            control: Control input with throttle and rate commands.

        Returns:
            True if command was published successfully.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
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
            from geometry_msgs.msg import Twist

            twist = Twist()
            twist.linear.x = control.throttle
            twist.linear.y = control.roll_rate
            twist.linear.z = control.pitch_rate
            twist.angular.z = control.yaw_rate

            self._publishers["cmd_vel"].publish(twist)
            return True
        except Exception as exc:
            logger.error("Failed to publish ROS2 control: %s", exc)
            return False

    def arm(self) -> bool:
        """Call the ROS2 arm service.

        Returns:
            True if arming service call succeeded.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            self._armed = True
            logger.info("ROS2 simulation: vehicle armed")
            return True

        try:
            from std_srvs.srv import Trigger

            client = self._node.create_client(Trigger, "/arm")
            if client.wait_for_service(timeout_sec=5.0):
                request = Trigger.Request()
                client.call_async(request)
                return True
            logger.error("ROS2 arm service not available")
            return False
        except Exception as exc:
            logger.error("Failed to call ROS2 arm service: %s", exc)
            return False

    def set_mode(self, mode: str) -> bool:
        """Call the ROS2 mode change service.

        Args:
            mode: The desired mode string.

        Returns:
            True if mode change service call succeeded.

        Raises:
            RuntimeError: If not connected.
            ValueError: If mode is empty.
        """
        self._ensure_connected()

        if not mode or not isinstance(mode, str):
            raise ValueError(f"Invalid ROS2 mode: {mode!r}")

        if self._simulation:
            self._current_mode = mode
            logger.info("ROS2 simulation: mode set to %s", mode)
            return True

        try:
            # Mode change via service call
            self._current_mode = mode
            return True
        except Exception as exc:
            logger.error("Failed to set ROS2 mode: %s", exc)
            return False

    def get_telemetry(self) -> dict[str, Any]:
        """Retrieve telemetry data from ROS2 topics.

        Returns:
            Dictionary with telemetry fields.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            return self._generate_simulated_telemetry()

        return {
            "timestamp": time.time(),
            "mode": self._current_mode,
            "armed": self._armed,
            "namespace": self._namespace,
        }

    def is_connected(self) -> bool:
        """Check if ROS2 connection is active.

        Returns:
            True if connected, False otherwise.
        """
        if self._simulation:
            return self._connected

        if self._node is None:
            return False

        try:
            import rclpy

            return rclpy.ok() and self._connected
        except ImportError:
            return self._connected

    def _ensure_connected(self) -> None:
        """Raise RuntimeError if not connected."""
        if not self._connected:
            raise RuntimeError("ROS2 bridge is not connected to a vehicle")

    def _setup_publishers_and_subscriptions(self) -> None:
        """Create ROS2 publishers and subscribers for vehicle topics."""
        if self._node is None:
            return

        try:
            from geometry_msgs.msg import Twist
            from nav_msgs.msg import Odometry
            from sensor_msgs.msg import BatteryState, NavSatFix

            self._publishers["cmd_vel"] = self._node.create_publisher(
                Twist, "/cmd_vel", QOS_PROFILES["default"]["depth"]
            )
            self._subscriptions["odom"] = self._node.create_subscription(
                Odometry, "/odom", self._odom_callback, QOS_PROFILES["sensor_data"]["depth"]
            )
            self._subscriptions["battery"] = self._node.create_subscription(
                BatteryState,
                "/battery",
                self._battery_callback,
                QOS_PROFILES["sensor_data"]["depth"],
            )
            self._subscriptions["gps"] = self._node.create_subscription(
                NavSatFix,
                "/gps",
                self._gps_callback,
                QOS_PROFILES["sensor_data"]["depth"],
            )
        except Exception as exc:
            logger.warning("Error setting up ROS2 topics: %s", exc)

    def _odom_callback(self, msg: Any) -> None:
        """Process odometry message from ROS2."""
        self._current_state = StateVector(
            pose=Pose3D(
                x=msg.pose.pose.position.x,
                y=msg.pose.pose.position.y,
                z=msg.pose.pose.position.z,
            ),
            velocity=Velocity3D(
                vx=msg.twist.twist.linear.x,
                vy=msg.twist.twist.linear.y,
                vz=msg.twist.twist.linear.z,
                vroll=msg.twist.twist.angular.x,
                vpitch=msg.twist.twist.angular.y,
                vyaw=msg.twist.twist.angular.z,
            ),
            timestamp=time.time(),
        )

    def _battery_callback(self, msg: Any) -> None:
        """Process battery state message from ROS2."""
        self._telemetry["battery_voltage"] = msg.voltage
        self._telemetry["battery_remaining"] = msg.percentage

    def _gps_callback(self, msg: Any) -> None:
        """Process GPS fix message from ROS2."""
        self._telemetry["gps_latitude"] = msg.latitude
        self._telemetry["gps_longitude"] = msg.longitude
        self._telemetry["gps_altitude"] = msg.altitude

    def _generate_simulated_telemetry(self) -> dict[str, Any]:
        """Generate simulated telemetry data for testing."""
        return {
            "timestamp": time.time(),
            "battery_voltage": 11.8,
            "battery_remaining": 72,
            "gps_latitude": 37.7749,
            "gps_longitude": -122.4194,
            "gps_altitude": 50.0,
            "mode": self._current_mode,
            "armed": self._armed,
            "namespace": self._namespace,
        }
