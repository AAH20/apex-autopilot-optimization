"""Asset, sensor, and actuator dataclasses for the digital twin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TwinAsset:
    """A digital twin representation of a physical asset."""

    id: str
    type: str
    state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class TwinSensor:
    """A sensor reading associated with a twin asset."""

    id: str
    asset_id: str
    sensor_type: str
    value: float
    timestamp: float


@dataclass
class TwinActuator:
    """An actuator state associated with a twin asset."""

    id: str
    asset_id: str
    actuator_type: str
    state: str
    timestamp: float
