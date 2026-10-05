"""DDS bridge for vehicle communication.

Provides a concrete implementation of VehicleInterface using the Data
Distribution Service (DDS) middleware. Supports both real DDS connections
via Fast-DDS/CycloneDDS and a simulation mode for testing without a DDS
environment.
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

# DDS QoS profile presets
QOS_PROFILES: dict[str, dict[str, Any]] = {
    "best_effort": {"reliability": "BEST_EFFORT", "durability": "VOLATILE"},
    "reliable": {"reliability": "RELIABLE", "durability": "VOLATILE"},
    "transient_local": {"reliability": "RELIABLE", "durability": "TRANSIENT_LOCAL"},
}


class DDSBridge(VehicleInterface):
    """DDS-based vehicle interface implementation.

    Connects to a vehicle's DDS data bus to exchange state, control,
    and telemetry data. In simulation mode, all data is generated
    internally without requiring Fast-DDS/CycloneDDS or a running DDS
    daemon.

    Attributes:
        domain_id: DDS domain ID for the vehicle.
        participant_name: DDS participant name for this bridge.
    """

    def __init__(
        self,
        domain_id: int = 0,
        participant_name: str = "apex_bridge",
        simulation: bool = False,
    ) -> None:
        """Initialize the DDS bridge.

        Args:
            domain_id: DDS domain ID.
            participant_name: DDS participant name.
            simulation: Force simulation mode even if DDS libraries are available.
        """
        self._domain_id = domain_id
        self._participant_name = participant_name
        self._simulation = simulation
        self._connected = False
        self._participant: Any = None  # DDS DomainParticipant
        self._publishers: dict[str, Any] = {}
        self._subscribers: dict[str, Any] = {}
        self._current_state = self._default_state()
        self._current_mode = "manual"
        self._armed = False
        self._telemetry: dict[str, Any] = {}
        self._dds_available = False

        if not simulation:
            try:
                # Try Fast-DDS first, then CycloneDDS
                try:
                    import fastdds  # type: ignore[import-not-found] # noqa: F401

                    self._dds_available = True
                    self._dds_backend = "fastdds"
                except ImportError:
                    try:
                        from cyclonedds.domain import (
                            DomainParticipant,  # type: ignore[import-not-found] # noqa: F401
                        )

                        self._dds_available = True
                        self._dds_backend = "cyclonedds"
                    except ImportError:
                        logger.info("No DDS library available; using simulation mode")
                        self._simulation = True
            except ImportError:
                logger.info("No DDS library available; using simulation mode")
                self._simulation = True

    @property
    def domain_id(self) -> int:
        """Return the DDS domain ID."""
        return self._domain_id

    @property
    def participant_name(self) -> str:
        """Return the DDS participant name."""
        return self._participant_name

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
        """Establish DDS connection to the vehicle.

        Args:
            connection_string: DDS connection URI (e.g., "dds://domain_id/participant_name").
                The format is dds://<domain_id>/<participant_name>.

        Returns:
            True if connection established successfully.

        Raises:
            ConnectionError: If connection string is malformed or vehicle
                is unreachable.
        """
        if not connection_string.startswith("dds://"):
            raise ConnectionError(
                f"Invalid DDS connection string: {connection_string!r}. "
                "Expected format: dds://<domain_id>/<participant_name>"
            )

        # Parse domain_id from connection string
        parts = connection_string[6:].split("/")
        try:
            self._domain_id = int(parts[0])
        except (ValueError, IndexError) as exc:
            raise ConnectionError(
                f"Invalid DDS domain ID in connection string: {connection_string!r}"
            ) from exc

        if len(parts) >= 2 and parts[1]:
            self._participant_name = parts[1]

        if self._simulation:
            self._connected = True
            self._current_state = self._default_state()
            self._telemetry = self._generate_simulated_telemetry()
            logger.info(
                "DDS simulation connection established to %s", connection_string
            )
            return True

        try:
            if self._dds_backend == "fastdds":
                import fastdds

                factory = fastdds.DomainParticipantFactory.get_instance()
                qos = factory.get_default_participant_qos()
                self._participant = factory.create_participant(
                    self._domain_id, qos
                )
            elif self._dds_backend == "cyclonedds":
                from cyclonedds.domain import DomainParticipant

                self._participant = DomainParticipant(self._domain_id)

            self._setup_topics()
            self._connected = True
            logger.info(
                "DDS connection established to %s (domain=%d, participant=%s)",
                connection_string,
                self._domain_id,
                self._participant_name,
            )
            return True
        except Exception as exc:
            self._connected = False
            raise ConnectionError(
                f"Failed to connect to DDS vehicle at {connection_string}: {exc}"
            ) from exc

    def disconnect(self) -> bool:
        """Shutdown the DDS participant and connections.

        Returns:
            True if disconnection was successful.
        """
        if self._participant is not None:
            try:
                if self._dds_backend == "fastdds":
                    import fastdds

                    factory = fastdds.DomainParticipantFactory.get_instance()
                    factory.delete_participant(self._participant)
                elif self._dds_backend == "cyclonedds":
                    del self._participant
            except Exception as exc:
                logger.warning("Error deleting DDS participant: %s", exc)
            finally:
                self._participant = None

        self._publishers.clear()
        self._subscribers.clear()
        self._connected = False
        self._armed = False
        self._current_mode = "manual"
        self._current_state = self._default_state()
        self._telemetry = {}
        logger.info("DDS connection closed")
        return True

    def get_state(self) -> StateVector:
        """Retrieve current vehicle state from DDS topics.

        Returns:
            Current state vector with pose, velocity, and timestamp.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            return self._current_state

        # In real DDS mode, state is updated via subscriber callbacks
        return self._current_state

    def send_control(self, control: ControlInput) -> bool:
        """Publish control command via DDS topic.

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
            # Publish control message via DDS
            self._publishers["control"].write(control)
            return True
        except Exception as exc:
            logger.error("Failed to publish DDS control: %s", exc)
            return False

    def arm(self) -> bool:
        """Publish arm command via DDS topic.

        Returns:
            True if arm command was published successfully.

        Raises:
            RuntimeError: If not connected.
        """
        self._ensure_connected()

        if self._simulation:
            self._armed = True
            logger.info("DDS simulation: vehicle armed")
            return True

        try:
            self._publishers["arm"].write(True)
            self._armed = True
            return True
        except Exception as exc:
            logger.error("Failed to publish DDS arm command: %s", exc)
            return False

    def set_mode(self, mode: str) -> bool:
        """Publish mode change command via DDS topic.

        Args:
            mode: The desired mode string.

        Returns:
            True if mode change was published successfully.

        Raises:
            RuntimeError: If not connected.
            ValueError: If mode is empty.
        """
        self._ensure_connected()

        if not mode or not isinstance(mode, str):
            raise ValueError(f"Invalid DDS mode: {mode!r}")

        if self._simulation:
            self._current_mode = mode
            logger.info("DDS simulation: mode set to %s", mode)
            return True

        try:
            self._publishers["mode"].write(mode)
            self._current_mode = mode
            return True
        except Exception as exc:
            logger.error("Failed to publish DDS mode change: %s", exc)
            return False

    def get_telemetry(self) -> dict[str, Any]:
        """Retrieve telemetry data from DDS topics.

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
            "domain_id": self._domain_id,
        }

    def is_connected(self) -> bool:
        """Check if DDS connection is active.

        Returns:
            True if connected, False otherwise.
        """
        if self._simulation:
            return self._connected

        if self._participant is None:
            return False

        return self._connected

    def _ensure_connected(self) -> None:
        """Raise RuntimeError if not connected."""
        if not self._connected:
            raise RuntimeError("DDS bridge is not connected to a vehicle")

    def _setup_topics(self) -> None:
        """Create DDS topics, publishers, and subscribers for vehicle data."""
        if self._participant is None:
            return

        try:
            if self._dds_backend == "fastdds":

                # Create topics and data writers/readers
                # Topic names follow DDS naming conventions
                self._publishers["control"] = self._participant.create_publisher(
                    "ControlTopic", "ControlType"
                )
                self._publishers["arm"] = self._participant.create_publisher(
                    "ArmTopic", "ArmType"
                )
                self._publishers["mode"] = self._participant.create_publisher(
                    "ModeTopic", "ModeType"
                )
                self._subscribers["state"] = self._participant.create_subscriber(
                    "StateTopic", "StateType"
                )
                self._subscribers["telemetry"] = self._participant.create_subscriber(
                    "TelemetryTopic", "TelemetryType"
                )
            elif self._dds_backend == "cyclonedds":
                from cyclonedds.pub import DataWriter, Publisher  # type: ignore[import-not-found]
                from cyclonedds.sub import DataReader, Subscriber  # type: ignore[import-not-found]
                from cyclonedds.topic import Topic  # type: ignore[import-not-found]

                publisher = Publisher(self._participant)
                subscriber = Subscriber(self._participant)

                control_topic = Topic(self._participant, "ControlTopic", "ControlType")
                self._publishers["control"] = DataWriter(publisher, control_topic)

                state_topic = Topic(self._participant, "StateTopic", "StateType")
                self._subscribers["state"] = DataReader(subscriber, state_topic)
        except Exception as exc:
            logger.warning("Error setting up DDS topics: %s", exc)

    def _generate_simulated_telemetry(self) -> dict[str, Any]:
        """Generate simulated telemetry data for testing."""
        return {
            "timestamp": time.time(),
            "battery_voltage": 12.1,
            "battery_remaining": 78,
            "cpu_usage": 35.0,
            "memory_usage": 42.0,
            "mode": self._current_mode,
            "armed": self._armed,
            "domain_id": self._domain_id,
        }
