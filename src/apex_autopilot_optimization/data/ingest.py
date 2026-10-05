"""Data ingestion for flight logs, sensor data, and MAVLink logs."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

SUPPORTED_SENSOR_TYPES = frozenset({"imu", "gps", "barometer", "magnetometer", "airspeed"})


class DataIngestor:
    """Ingest flight logs, sensor data, and MAVLink logs.

    Tracks ingestion counts and per-source statistics for observability.
    """

    def __init__(self) -> None:
        self._ingested_count: int = 0
        self._stats: dict[str, int] = {
            "flight_logs": 0,
            "sensor_data": 0,
            "mavlink_logs": 0,
            "errors": 0,
        }

    def ingest_flight_log(self, path: str | Path) -> list[dict[str, Any]]:
        """Ingest a flight log file (CSV or JSON).

        Args:
            path: Path to the flight log file.

        Returns:
            List of records parsed from the file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is unsupported or malformed.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Flight log not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            records = self._parse_csv(file_path)
        elif suffix == ".json":
            records = self._parse_json(file_path)
        else:
            raise ValueError(f"Unsupported flight log format: {suffix!r}")

        self._ingested_count += len(records)
        self._stats["flight_logs"] += 1
        logger.info("Ingested flight log %s (%d records)", file_path, len(records))
        return records

    def ingest_sensor_data(
        self, data: list[dict[str, Any]], sensor_type: str
    ) -> list[dict[str, Any]]:
        """Ingest sensor data records.

        Args:
            data: List of sensor reading dictionaries.
            sensor_type: Type of sensor (e.g. ``"imu"``, ``"gps"``).

        Returns:
            The validated sensor records.

        Raises:
            ValueError: If ``sensor_type`` is not supported or data is empty.
        """
        if sensor_type not in SUPPORTED_SENSOR_TYPES:
            raise ValueError(
                f"Unsupported sensor type: {sensor_type!r}. "
                f"Supported: {sorted(SUPPORTED_SENSOR_TYPES)}"
            )
        if not data:
            raise ValueError("Sensor data must not be empty")

        self._ingested_count += len(data)
        self._stats["sensor_data"] += 1
        logger.info("Ingested %d %s records", len(data), sensor_type)
        return list(data)

    def ingest_mavlink_log(self, path: str | Path) -> list[dict[str, Any]]:
        """Ingest a MAVLink log file (JSON format).

        Args:
            path: Path to the MAVLink log file.

        Returns:
            List of MAVLink message records.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is unsupported or malformed.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"MAVLink log not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix != ".json":
            raise ValueError(f"Unsupported MAVLink log format: {suffix!r}")

        records = self._parse_json(file_path)
        self._ingested_count += len(records)
        self._stats["mavlink_logs"] += 1
        logger.info("Ingested MAVLink log %s (%d records)", file_path, len(records))
        return records

    def get_ingested_count(self) -> int:
        """Return the total number of ingested records."""
        return self._ingested_count

    def get_ingestion_stats(self) -> dict[str, int]:
        """Return ingestion statistics."""
        return dict(self._stats)

    @staticmethod
    def _parse_csv(path: Path) -> list[dict[str, Any]]:
        """Parse a CSV file into a list of record dictionaries."""
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]

    @staticmethod
    def _parse_json(path: Path) -> list[dict[str, Any]]:
        """Parse a JSON file into a list of record dictionaries."""
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            return cast(list[dict[str, Any]], payload)
        if isinstance(payload, dict) and "records" in payload:
            return cast(list[dict[str, Any]], payload["records"])
        raise ValueError(f"Unexpected JSON structure in {path}")
