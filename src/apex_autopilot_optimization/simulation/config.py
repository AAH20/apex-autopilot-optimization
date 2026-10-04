"""Simulation configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Configuration for a simulation session.

    Attributes:
        backend: Simulation backend name (e.g., 'gazebo', 'airsim').
        connection_string: URI or address for the simulation backend.
        lockstep: Whether to run in lockstep mode (synchronous stepping).
        time_scale: Simulation time scale factor (1.0 = real-time).
        vehicle_type: Type of vehicle (e.g., 'multirotor', 'fixed_wing').
        model: Vehicle model name (e.g., 'iris', 'standard_vtol').
    """

    backend: str = ""
    connection_string: str = ""
    lockstep: bool = False
    time_scale: float = 1.0
    vehicle_type: str = ""
    model: str = ""
