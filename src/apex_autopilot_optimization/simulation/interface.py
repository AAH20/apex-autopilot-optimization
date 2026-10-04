"""Simulation interface ABC and backend enumeration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any


class SimulationBackend(Enum):
    """Supported simulation backends."""

    GAZEBO = auto()
    AIRSIM = auto()
    JMASIM = auto()
    SITL = auto()
    HITL = auto()


class SimulationInterface(ABC):
    """Abstract base class for simulation backends.

    Defines the contract that all simulation adapters must implement
    to integrate with the autopilot optimization framework.
    """

    @abstractmethod
    def connect(self, connection_string: str) -> bool:
        """Connect to the simulation backend.

        Args:
            connection_string: URI or address for the simulation.

        Returns:
            True if connection succeeded, False otherwise.
        """
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the simulation backend.

        Returns:
            True if disconnection succeeded, False otherwise.
        """
        ...

    @abstractmethod
    def get_state(self) -> Any:
        """Get the current vehicle state from the simulation.

        Returns:
            The current state representation.
        """
        ...

    @abstractmethod
    def send_control(self, control: Any) -> bool:
        """Send a control input to the simulation.

        Args:
            control: The control input to apply.

        Returns:
            True if the control was accepted, False otherwise.
        """
        ...

    @abstractmethod
    def arm(self) -> bool:
        """Arm the vehicle in the simulation.

        Returns:
            True if arming succeeded, False otherwise.
        """
        ...

    @abstractmethod
    def set_mode(self, mode: str) -> bool:
        """Set the flight/operation mode.

        Args:
            mode: The mode string (e.g., 'GUIDED', 'OFFBOARD').

        Returns:
            True if mode change succeeded, False otherwise.
        """
        ...

    @abstractmethod
    def reset(self) -> bool:
        """Reset the simulation to initial state.

        Returns:
            True if reset succeeded, False otherwise.
        """
        ...

    @abstractmethod
    def step(self, dt: float) -> bool:
        """Advance the simulation by a time step.

        Args:
            dt: Time delta in seconds.

        Returns:
            True if the step succeeded, False otherwise.
        """
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the simulation is currently connected."""
        ...

    @property
    @abstractmethod
    def time_scale(self) -> float:
        """Current simulation time scale factor."""
        ...
