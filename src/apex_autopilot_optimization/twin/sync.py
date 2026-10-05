"""Sync manager for keeping the digital twin aligned with real-world state."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from apex_autopilot_optimization.twin.asset import TwinActuator, TwinSensor
from apex_autopilot_optimization.twin.twin import DigitalTwin


class TwinSyncMode(Enum):
    """Synchronization mode for the digital twin."""

    OPEN_LOOP = "open_loop"
    CLOSED_LOOP = "closed_loop"
    CALIBRATED = "calibrated"
    MIRRORED = "mirrored"


class TwinSyncManager:
    """Manages synchronization between real-world state and the digital twin."""

    def __init__(self, twin: DigitalTwin) -> None:
        self._twin = twin
        self._mode = TwinSyncMode.OPEN_LOOP
        self._last_real_state: dict[str, dict[str, Any]] = {}
        self._sensors: dict[str, TwinSensor] = {}
        self._actuators: dict[str, TwinActuator] = {}

    def sync_to_twin(self, real_state: dict[str, dict[str, Any]]) -> None:
        """Push real-world state into the twin, creating assets as needed."""
        self._last_real_state = {k: dict(v) for k, v in real_state.items()}
        for key, state in real_state.items():
            existing = self._twin.get_asset(key)
            if existing is None:
                # Try to find by type
                for asset in self._twin.list_assets():
                    if asset.type == key:
                        existing = asset
                        break
            if existing is None:
                self._twin.create_asset(key, state)
            else:
                self._twin.set_asset_state(existing.id, state)

    def sync_from_twin(self) -> dict[str, dict[str, Any]]:
        """Pull current twin state out as a real-world state dict keyed by asset type."""
        result: dict[str, dict[str, Any]] = {}
        for asset in self._twin.list_assets():
            result[asset.type] = dict(asset.state)
        return result

    def get_drift(self) -> float:
        """Compute total absolute drift between last synced real state and current twin state."""
        drift = 0.0
        for asset_id, real_state in self._last_real_state.items():
            twin_state = self._twin.get_asset_state(asset_id)
            if twin_state is None:
                continue
            all_keys = set(real_state) | set(twin_state)
            for key in all_keys:
                rv = real_state.get(key, 0)
                tv = twin_state.get(key, 0)
                if isinstance(rv, int | float) and isinstance(tv, int | float):
                    drift += abs(float(rv) - float(tv))
        return drift

    def calibrate(self) -> None:
        """Reset the drift baseline by re-syncing from current twin state."""
        self._last_real_state = self.sync_from_twin()

    def get_sync_mode(self) -> TwinSyncMode:
        """Return the current sync mode."""
        return self._mode

    def set_sync_mode(self, mode: TwinSyncMode) -> None:
        """Set the sync mode."""
        self._mode = mode

    def create_sensor(self, asset_id: str, sensor_type: str, value: float) -> TwinSensor:
        """Create and register a sensor for a twin asset."""
        sensor = TwinSensor(
            id=uuid.uuid4().hex[:12],
            asset_id=asset_id,
            sensor_type=sensor_type,
            value=value,
            timestamp=time.time(),
        )
        self._sensors[sensor.id] = sensor
        return sensor

    def create_actuator(self, asset_id: str, actuator_type: str, state: str) -> TwinActuator:
        """Create and register an actuator for a twin asset."""
        actuator = TwinActuator(
            id=uuid.uuid4().hex[:12],
            asset_id=asset_id,
            actuator_type=actuator_type,
            state=state,
            timestamp=time.time(),
        )
        self._actuators[actuator.id] = actuator
        return actuator
