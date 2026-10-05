"""Tests for the data pipeline package."""

from __future__ import annotations

import json

import pytest

from apex_autopilot_optimization.data import (
    DataIngestor,
    DataProcessor,
    DataVersionManager,
    InMemoryDataStore,
)
from apex_autopilot_optimization.data.store import DataStore


class TestDataIngestorFlightLog:
    """Tests for flight log ingestion."""

    def test_ingest_csv_flight_log(self, tmp_path) -> None:
        log = tmp_path / "flight.csv"
        log.write_text("timestamp,altitude\n100,50.0\n200,60.0\n")
        ingestor = DataIngestor()
        records = ingestor.ingest_flight_log(log)
        assert len(records) == 2
        assert records[0]["timestamp"] == "100"
        assert records[1]["altitude"] == "60.0"

    def test_ingest_json_flight_log(self, tmp_path) -> None:
        log = tmp_path / "flight.json"
        log.write_text(json.dumps([{"timestamp": 1, "x": 10}, {"timestamp": 2, "x": 20}]))
        ingestor = DataIngestor()
        records = ingestor.ingest_flight_log(log)
        assert len(records) == 2
        assert records[0]["x"] == 10

    def test_ingest_flight_log_not_found(self) -> None:
        ingestor = DataIngestor()
        with pytest.raises(FileNotFoundError):
            ingestor.ingest_flight_log("/nonexistent/path.csv")

    def test_ingest_flight_log_unsupported_format(self, tmp_path) -> None:
        log = tmp_path / "flight.txt"
        log.write_text("raw data")
        ingestor = DataIngestor()
        with pytest.raises(ValueError, match="Unsupported flight log format"):
            ingestor.ingest_flight_log(log)

    def test_ingest_flight_log_malformed_json(self, tmp_path) -> None:
        log = tmp_path / "flight.json"
        log.write_text(json.dumps({"unexpected": "structure"}))
        ingestor = DataIngestor()
        with pytest.raises(ValueError, match="Unexpected JSON structure"):
            ingestor.ingest_flight_log(log)


class TestDataIngestorSensorData:
    """Tests for sensor data ingestion."""

    def test_ingest_sensor_data_success(self) -> None:
        ingestor = DataIngestor()
        data = [{"ax": 1.0, "ay": 2.0}, {"ax": 3.0, "ay": 4.0}]
        result = ingestor.ingest_sensor_data(data, "imu")
        assert len(result) == 2
        assert result[0]["ax"] == 1.0

    def test_ingest_sensor_data_unsupported_type(self) -> None:
        ingestor = DataIngestor()
        with pytest.raises(ValueError, match="Unsupported sensor type"):
            ingestor.ingest_sensor_data([{"x": 1}], "lidar")

    def test_ingest_sensor_data_empty(self) -> None:
        ingestor = DataIngestor()
        with pytest.raises(ValueError, match="must not be empty"):
            ingestor.ingest_sensor_data([], "gps")

    @pytest.mark.parametrize("sensor_type", ["imu", "gps", "barometer", "magnetometer", "airspeed"])
    def test_ingest_all_supported_sensor_types(self, sensor_type: str) -> None:
        ingestor = DataIngestor()
        result = ingestor.ingest_sensor_data([{"val": 1.0}], sensor_type)
        assert len(result) == 1


class TestDataIngestorMavlinkLog:
    """Tests for MAVLink log ingestion."""

    def test_ingest_mavlink_log(self, tmp_path) -> None:
        log = tmp_path / "mavlink.json"
        log.write_text(json.dumps([{"msg": "ATTITUDE", "roll": 0.1}]))
        ingestor = DataIngestor()
        records = ingestor.ingest_mavlink_log(log)
        assert len(records) == 1
        assert records[0]["msg"] == "ATTITUDE"

    def test_ingest_mavlink_log_not_found(self) -> None:
        ingestor = DataIngestor()
        with pytest.raises(FileNotFoundError):
            ingestor.ingest_mavlink_log("/nonexistent/mavlink.json")

    def test_ingest_mavlink_log_unsupported_format(self, tmp_path) -> None:
        log = tmp_path / "mavlink.bin"
        log.write_bytes(b"\x00\x01")
        ingestor = DataIngestor()
        with pytest.raises(ValueError, match="Unsupported MAVLink log format"):
            ingestor.ingest_mavlink_log(log)


class TestDataIngestorStats:
    """Tests for ingestion statistics."""

    def test_get_ingested_count(self) -> None:
        ingestor = DataIngestor()
        assert ingestor.get_ingested_count() == 0
        ingestor.ingest_sensor_data([{"a": 1}, {"a": 2}], "imu")
        assert ingestor.get_ingested_count() == 2

    def test_get_ingestion_stats(self) -> None:
        ingestor = DataIngestor()
        ingestor.ingest_sensor_data([{"a": 1}], "gps")
        stats = ingestor.get_ingestion_stats()
        assert stats["sensor_data"] == 1
        assert stats["flight_logs"] == 0
        assert stats["mavlink_logs"] == 0
        assert stats["errors"] == 0

    def test_stats_accumulate(self) -> None:
        ingestor = DataIngestor()
        ingestor.ingest_sensor_data([{"a": 1}], "imu")
        ingestor.ingest_sensor_data([{"b": 2}], "gps")
        stats = ingestor.get_ingestion_stats()
        assert stats["sensor_data"] == 2
        assert ingestor.get_ingested_count() == 2


class TestDataProcessorSync:
    """Tests for timestamp synchronization."""

    def test_sync_sorts_timestamps(self) -> None:
        processor = DataProcessor()
        result = processor.sync([3.0, 1.0, 2.0])
        assert result == [1.0, 2.0, 3.0]

    def test_sync_removes_duplicates(self) -> None:
        processor = DataProcessor()
        result = processor.sync([1.0, 1.0, 2.0, 2.0])
        assert result == [1.0, 2.0]

    def test_sync_empty(self) -> None:
        processor = DataProcessor()
        assert processor.sync([]) == []


class TestDataProcessorClean:
    """Tests for data cleaning."""

    def test_clean_removes_none_values(self) -> None:
        processor = DataProcessor()
        data = [{"a": 1, "b": 2}, {"a": None, "b": 3}]
        result = processor.clean(data)
        assert len(result) == 1
        assert result[0]["a"] == 1

    def test_clean_removes_nan_values(self) -> None:
        processor = DataProcessor()
        data = [{"a": 1.0}, {"a": float("nan")}]
        result = processor.clean(data)
        assert len(result) == 1

    def test_clean_removes_empty_records(self) -> None:
        processor = DataProcessor()
        data = [{"a": 1}, {}, {"b": 2}]
        result = processor.clean(data)
        assert len(result) == 2

    def test_clean_empty_input(self) -> None:
        processor = DataProcessor()
        assert processor.clean([]) == []


class TestDataProcessorTransform:
    """Tests for data transformation."""

    def test_transform_normalize(self) -> None:
        processor = DataProcessor()
        data = [{"x": 0.0}, {"x": 50.0}, {"x": 100.0}]
        result = processor.transform(data, "normalize")
        assert result[0]["x"] == pytest.approx(0.0)
        assert result[1]["x"] == pytest.approx(0.5)
        assert result[2]["x"] == pytest.approx(1.0)

    def test_transform_resample(self) -> None:
        processor = DataProcessor()
        data = [{"i": i} for i in range(10)]
        result = processor.transform(data, "resample")
        assert len(result) == 5
        assert result[0]["i"] == 0
        assert result[1]["i"] == 2

    def test_transform_filter(self) -> None:
        processor = DataProcessor()
        data = [{"x": 1, "y": -2}, {"x": 3, "y": 4}]
        result = processor.transform(data, "filter")
        assert len(result) == 1
        assert result[0]["x"] == 3

    def test_transform_aggregate(self) -> None:
        processor = DataProcessor()
        data = [{"x": 10.0}, {"x": 20.0}, {"x": 30.0}]
        result = processor.transform(data, "aggregate")
        assert len(result) == 1
        assert result[0]["x"] == pytest.approx(20.0)

    def test_transform_unsupported_type(self) -> None:
        processor = DataProcessor()
        with pytest.raises(ValueError, match="Unsupported transform"):
            processor.transform([{"a": 1}], "unknown")


class TestDataProcessorValidate:
    """Tests for data validation."""

    def test_validate_consistent_keys(self) -> None:
        processor = DataProcessor()
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        assert processor.validate(data) is True

    def test_validate_inconsistent_keys(self) -> None:
        processor = DataProcessor()
        data = [{"a": 1}, {"b": 2}]
        assert processor.validate(data) is False

    def test_validate_empty_data(self) -> None:
        processor = DataProcessor()
        assert processor.validate([]) is False

    def test_validate_empty_record(self) -> None:
        processor = DataProcessor()
        assert processor.validate([{}]) is False


class TestDataProcessorStats:
    """Tests for processing statistics."""

    def test_get_processing_stats(self) -> None:
        processor = DataProcessor()
        processor.sync([2.0, 1.0])
        processor.clean([{"a": 1}, {"a": None}])
        processor.transform([{"x": 1.0}], "normalize")
        processor.validate([{"a": 1}])
        stats = processor.get_processing_stats()
        assert stats["sync_operations"] == 1
        assert stats["clean_operations"] == 1
        assert stats["transform_operations"] == 1
        assert stats["validate_operations"] == 1
        assert stats["records_removed"] == 1


class TestInMemoryDataStore:
    """Tests for the in-memory data store."""

    def test_save_and_get(self) -> None:
        store = InMemoryDataStore()
        store.save("ds1", [{"a": 1}])
        result = store.get("ds1")
        assert result == [{"a": 1}]

    def test_get_nonexistent(self) -> None:
        store = InMemoryDataStore()
        assert store.get("nonexistent") is None

    def test_list_datasets(self) -> None:
        store = InMemoryDataStore()
        store.save("ds1", [1, 2])
        store.save("ds2", [3, 4])
        assert set(store.list_datasets()) == {"ds1", "ds2"}

    def test_delete(self) -> None:
        store = InMemoryDataStore()
        store.save("ds1", [1])
        assert store.delete("ds1") is True
        assert store.get("ds1") is None

    def test_delete_nonexistent(self) -> None:
        store = InMemoryDataStore()
        assert store.delete("nonexistent") is False

    def test_get_dataset_info(self) -> None:
        store = InMemoryDataStore()
        store.save("ds1", [1, 2, 3])
        info = store.get_dataset_info("ds1")
        assert info is not None
        assert info["dataset_id"] == "ds1"
        assert info["size"] == 3

    def test_get_dataset_info_nonexistent(self) -> None:
        store = InMemoryDataStore()
        assert store.get_dataset_info("nonexistent") is None

    def test_deep_copy_isolation(self) -> None:
        store = InMemoryDataStore()
        original = [{"a": 1}]
        store.save("ds1", original)
        original[0]["a"] = 999
        result = store.get("ds1")
        assert result[0]["a"] == 1

    def test_store_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            DataStore()  # type: ignore[abstract]


class TestDataVersionManager:
    """Tests for dataset version management."""

    def test_create_version(self) -> None:
        manager = DataVersionManager()
        v = manager.create_version("ds1", {"source": "test"})
        assert v == 1

    def test_create_multiple_versions(self) -> None:
        manager = DataVersionManager()
        v1 = manager.create_version("ds1")
        v2 = manager.create_version("ds1")
        v3 = manager.create_version("ds1")
        assert v1 == 1
        assert v2 == 2
        assert v3 == 3

    def test_get_version(self) -> None:
        manager = DataVersionManager()
        manager.create_version("ds1", {"key": "value"})
        entry = manager.get_version("ds1", 1)
        assert entry is not None
        assert entry["version"] == 1
        assert entry["metadata"]["key"] == "value"

    def test_get_version_nonexistent(self) -> None:
        manager = DataVersionManager()
        assert manager.get_version("ds1", 99) is None

    def test_list_versions(self) -> None:
        manager = DataVersionManager()
        manager.create_version("ds1")
        manager.create_version("ds1")
        versions = manager.list_versions("ds1")
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2

    def test_list_versions_empty(self) -> None:
        manager = DataVersionManager()
        assert manager.list_versions("nonexistent") == []

    def test_get_latest_version(self) -> None:
        manager = DataVersionManager()
        manager.create_version("ds1", {"n": 1})
        manager.create_version("ds1", {"n": 2})
        latest = manager.get_latest_version("ds1")
        assert latest is not None
        assert latest["version"] == 2
        assert latest["metadata"]["n"] == 2

    def test_get_latest_version_empty(self) -> None:
        manager = DataVersionManager()
        assert manager.get_latest_version("nonexistent") is None

    def test_versions_are_isolated(self) -> None:
        manager = DataVersionManager()
        manager.create_version("ds1", {"data": [1, 2, 3]})
        entry = manager.get_version("ds1", 1)
        entry["metadata"]["data"].append(4)
        fresh = manager.get_version("ds1", 1)
        assert fresh is not None
        assert len(fresh["metadata"]["data"]) == 3

    def test_multiple_datasets_independent(self) -> None:
        manager = DataVersionManager()
        manager.create_version("ds1")
        manager.create_version("ds1")
        manager.create_version("ds2")
        assert len(manager.list_versions("ds1")) == 2
        assert len(manager.list_versions("ds2")) == 1
