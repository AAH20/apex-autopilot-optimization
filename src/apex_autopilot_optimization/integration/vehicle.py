"""Abstract vehicle interface for external system integration.

Defines the contract that all vehicle bridge implementations must fulfill,
providing a uniform API for connecting to, controlling, and monitoring
autonomous vehicles regardless of the underlying communication protocol.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from apex_autopilot_optimization.core.types import ControlInput, StateVector


class VehicleInterface(ABC):
    """Abstract base class for vehicle communication bridges.

    All concrete vehicle interface implementations must inherit from this
    class and implement every abstract method. The interface provides a
    protocol-agnostic API for vehicle control, state monitoring, and
    telemetry retrieval.

    Implementations are responsible for:
    - Connection lifecycle management (connect/disconnect)
    - Protocol-specific message serialization/deserialization
    - State estimation and telemetry aggregation
    - Safety checks and mode management
    """

    @abstractmethod
    def connect(self, connection_string: str) -> bool:
        """Establish connection to the vehicle.

        Args:
            connection_string: Protocol-specific connection descriptor.
                Examples:
                - MAVLink: "udp:127.0.0.1:14550", "serial:/dev/ttyUSB0:57600"
                - ROS2: "ros2://namespace/vehicle_01"
                - DDS: "dds://domain_id/participant_name"

        Returns:
            True if connection was established successfully, False otherwise.

        Raises:
            ConnectionError: If the connection string is malformed or
                the vehicle is unreachable.
        """

    @abstractmethod
    def disconnect(self) -> bool:
        """Terminate the connection to the vehicle.

        Returns:
            True if disconnection was successful, False otherwise.
        """

    @abstractmethod
    def get_state(self) -> StateVector:
        """Retrieve the current vehicle state.

        Returns:
            The current state vector including pose, velocity, and timestamp.

        Raises:
            RuntimeError: If not connected to the vehicle.
        """

    @abstractmethod
    def send_control(self, control: ControlInput) -> bool:
        """Send a control input to the vehicle.

        Args:
            control: The control input to apply (throttle, rates, etc.).

        Returns:
            True if the control command was accepted, False otherwise.

        Raises:
            RuntimeError: If not connected to the vehicle.
        """

    @abstractmethod
    def arm(self) -> bool:
        """Arm the vehicle for flight/operation.

        Returns:
            True if arming was successful, False otherwise.

        Raises:
            RuntimeError: If not connected to the vehicle.
        """

    @abstractmethod
    def set_mode(self, mode: str) -> bool:
        """Set the vehicle operating mode.

        Args:
            mode: The desired mode string (e.g., "GUIDED", "LOITER",
                "AUTO", "RTL" for MAVLink; custom modes for other protocols).

        Returns:
            True if mode change was accepted, False otherwise.

        Raises:
            RuntimeError: If not connected to the vehicle.
            ValueError: If the mode string is not recognized.
        """

    @abstractmethod
    def get_telemetry(self) -> dict[str, Any]:
        """Retrieve current telemetry data from the vehicle.

        Returns:
            Dictionary containing telemetry fields such as battery voltage,
            GPS coordinates, signal strength, error counts, etc.

        Raises:
            RuntimeError: If not connected to the vehicle.
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the vehicle connection is active.

        Returns:
            True if connected, False otherwise.
        """
