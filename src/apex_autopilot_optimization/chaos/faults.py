"""Fault type definitions for chaos engineering."""

from __future__ import annotations

from enum import Enum, auto


class FaultType(Enum):
    """Types of faults that can be injected into the system."""

    NETWORK_DELAY = auto()
    NETWORK_DROP = auto()
    CPU_SPIKE = auto()
    MEMORY_PRESSURE = auto()
    SENSOR_NOISE = auto()
    SENSOR_DROPOUT = auto()
    ACTUATOR_FAILURE = auto()
    COMMUNICATION_ERROR = auto()
    CLOCK_DRIFT = auto()
    PACKET_LOSS = auto()
