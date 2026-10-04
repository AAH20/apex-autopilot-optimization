"""Simulation integration for autopilot optimization.

Provides the abstract interface, configuration, result types, and
runner for integrating external simulation backends (Gazebo, AirSim,
jMAVSim, SITL, HITL) with the optimization framework.
"""

from apex_autopilot_optimization.simulation.config import SimulationConfig
from apex_autopilot_optimization.simulation.interface import (
    SimulationBackend,
    SimulationInterface,
)
from apex_autopilot_optimization.simulation.result import SimulationResult
from apex_autopilot_optimization.simulation.runner import SimulationRunner

__all__ = [
    "SimulationInterface",
    "SimulationConfig",
    "SimulationResult",
    "SimulationRunner",
    "SimulationBackend",
]
