"""Tests for the digital twin subsystem."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.twin import (
    DigitalTwin,
    TwinActuator,
    TwinAsset,
    TwinSensor,
    TwinSyncManager,
    TwinSyncMode,
)


class TestTwinAsset:
    """Tests for TwinAsset dataclass."""

    def test_asset_fields(self) -> None:
        asset = TwinAsset(
            id="a1",
            type="motor",
            state={"rpm": 100},
            metadata={"location": "front-left"},
            created_at=1.0,
            updated_at=2.0,
        )
        assert asset.id == "a1"
        assert asset.type == "motor"
        assert asset.state == {"rpm": 100}
        assert asset.metadata == {"location": "front-left"}
        assert asset.created_at == 1.0
        assert asset.updated_at == 2.0


class TestTwinSensor:
    """Tests for TwinSensor dataclass."""

    def test_sensor_fields(self) -> None:
        sensor = TwinSensor(
            id="s1",
            asset_id="a1",
            sensor_type="temperature",
            value=72.5,
            timestamp=123.0,
        )
        assert sensor.id == "s1"
        assert sensor.asset_id == "a1"
        assert sensor.sensor_type == "temperature"
        assert sensor.value == 72.5
        assert sensor.timestamp == 123.0


class TestTwinActuator:
    """Tests for TwinActuator dataclass."""

    def test_actuator_fields(self) -> None:
        actuator = TwinActuator(
            id="act1",
            asset_id="a1",
            actuator_type="servo",
            state="engaged",
            timestamp=456.0,
        )
        assert actuator.id == "act1"
        assert actuator.asset_id == "a1"
        assert actuator.actuator_type == "servo"
        assert actuator.state == "engaged"
        assert actuator.timestamp == 456.0


class TestDigitalTwinAssetCRUD:
    """Tests for DigitalTwin asset CRUD operations."""

    def test_create_asset(self) -> None:
        twin = DigitalTwin()
        asset = twin.create_asset("motor", {"rpm": 0})
        assert asset.id
        assert asset.type == "motor"
        assert asset.state == {"rpm": 0}

    def test_get_asset(self) -> None:
        twin = DigitalTwin()
        created = twin.create_asset("motor", {"rpm": 0})
        fetched = twin.get_asset(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.type == "motor"

    def test_get_asset_not_found(self) -> None:
        twin = DigitalTwin()
        assert twin.get_asset("nonexistent") is None

    def test_update_asset(self) -> None:
        twin = DigitalTwin()
        created = twin.create_asset("motor", {"rpm": 0})
        updated = twin.update_asset(created.id, {"rpm": 5000})
        assert updated is not None
        assert updated.state == {"rpm": 5000}

    def test_update_asset_not_found(self) -> None:
        twin = DigitalTwin()
        assert twin.update_asset("nonexistent", {"rpm": 1}) is None

    def test_delete_asset(self) -> None:
        twin = DigitalTwin()
        created = twin.create_asset("motor", {})
        assert twin.delete_asset(created.id) is True
        assert twin.get_asset(created.id) is None

    def test_delete_asset_not_found(self) -> None:
        twin = DigitalTwin()
        assert twin.delete_asset("nonexistent") is False

    def test_list_assets(self) -> None:
        twin = DigitalTwin()
        twin.create_asset("motor", {})
        twin.create_asset("battery", {})
        assets = twin.list_assets()
        assert len(assets) == 2
        types = {a.type for a in assets}
        assert types == {"motor", "battery"}

    def test_list_assets_empty(self) -> None:
        twin = DigitalTwin()
        assert twin.list_assets() == []


class TestDigitalTwinAssetState:
    """Tests for DigitalTwin asset state get/set."""

    def test_get_asset_state(self) -> None:
        twin = DigitalTwin()
        created = twin.create_asset("motor", {"rpm": 100, "temp": 40})
        state = twin.get_asset_state(created.id)
        assert state == {"rpm": 100, "temp": 40}

    def test_get_asset_state_not_found(self) -> None:
        twin = DigitalTwin()
        assert twin.get_asset_state("nonexistent") is None

    def test_set_asset_state(self) -> None:
        twin = DigitalTwin()
        created = twin.create_asset("motor", {"rpm": 0})
        twin.set_asset_state(created.id, {"rpm": 3000})
        assert twin.get_asset_state(created.id) == {"rpm": 3000}

    def test_set_asset_state_not_found(self) -> None:
        twin = DigitalTwin()
        assert twin.set_asset_state("nonexistent", {"rpm": 1}) is False

    def test_set_asset_state_updates_timestamp(self) -> None:
        twin = DigitalTwin()
        created = twin.create_asset("motor", {"rpm": 0})
        old_updated = created.updated_at
        time.sleep(0.01)
        twin.set_asset_state(created.id, {"rpm": 2000})
        refetched = twin.get_asset(created.id)
        assert refetched is not None
        assert refetched.updated_at > old_updated


class TestTwinSyncManager:
    """Tests for TwinSyncManager."""

    def test_sync_to_twin(self) -> None:
        twin = DigitalTwin()
        twin.create_asset("motor", {"rpm": 0})
        mgr = TwinSyncManager(twin)
        mgr.sync_to_twin({"motor": {"rpm": 1500}})
        state = twin.get_asset_state("motor")
        assert state is not None
        assert state["rpm"] == 1500

    def test_sync_from_twin(self) -> None:
        twin = DigitalTwin()
        twin.create_asset("motor", {"rpm": 2500})
        mgr = TwinSyncManager(twin)
        real_state = mgr.sync_from_twin()
        assert real_state["motor"]["rpm"] == 2500

    def test_drift_detection(self) -> None:
        twin = DigitalTwin()
        twin.create_asset("motor", {"rpm": 1000})
        mgr = TwinSyncManager(twin)
        mgr.sync_to_twin({"motor": {"rpm": 1000}})
        drift = mgr.get_drift()
        assert drift == pytest.approx(0.0)

    def test_drift_nonzero(self) -> None:
        twin = DigitalTwin()
        twin.create_asset("motor", {"rpm": 1000})
        mgr = TwinSyncManager(twin)
        mgr.sync_to_twin({"motor": {"rpm": 1000}})
        twin.set_asset_state("motor", {"rpm": 1100})
        drift = mgr.get_drift()
        assert drift == pytest.approx(100.0)

    def test_calibrate(self) -> None:
        twin = DigitalTwin()
        twin.create_asset("motor", {"rpm": 1000})
        mgr = TwinSyncManager(twin)
        mgr.sync_to_twin({"motor": {"rpm": 1000}})
        twin.set_asset_state("motor", {"rpm": 1200})
        mgr.calibrate()
        drift = mgr.get_drift()
        assert drift == pytest.approx(0.0)

    def test_get_sync_mode_default(self) -> None:
        twin = DigitalTwin()
        mgr = TwinSyncManager(twin)
        assert mgr.get_sync_mode() == TwinSyncMode.OPEN_LOOP

    def test_set_sync_mode(self) -> None:
        twin = DigitalTwin()
        mgr = TwinSyncManager(twin)
        mgr.set_sync_mode(TwinSyncMode.CLOSED_LOOP)
        assert mgr.get_sync_mode() == TwinSyncMode.CLOSED_LOOP

    def test_sync_mode_enum_values(self) -> None:
        assert TwinSyncMode.OPEN_LOOP is not None
        assert TwinSyncMode.CLOSED_LOOP is not None
        assert TwinSyncMode.CALIBRATED is not None
        assert TwinSyncMode.MIRRORED is not None
        modes = {
            TwinSyncMode.OPEN_LOOP,
            TwinSyncMode.CLOSED_LOOP,
            TwinSyncMode.CALIBRATED,
            TwinSyncMode.MIRRORED,
        }
        assert len(modes) == 4
