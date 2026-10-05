"""Data processing: synchronization, cleaning, transformation, and validation."""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_TRANSFORMS = frozenset({"normalize", "resample", "filter", "aggregate"})


class DataProcessor:
    """Process ingested autopilot data.

    Provides timestamp synchronization, data cleaning, transformation,
    and validation with processing statistics tracking.
    """

    def __init__(self) -> None:
        self._stats: dict[str, int] = {
            "sync_operations": 0,
            "clean_operations": 0,
            "transform_operations": 0,
            "validate_operations": 0,
            "records_removed": 0,
            "records_transformed": 0,
        }

    def sync(self, timestamps: list[float]) -> list[float]:
        """Synchronize and sort timestamps, removing duplicates.

        Args:
            timestamps: Unsorted list of timestamps.

        Returns:
            Sorted list of unique timestamps.
        """
        synced = sorted(set(timestamps))
        self._stats["sync_operations"] += 1
        logger.info("Synchronized %d timestamps -> %d unique", len(timestamps), len(synced))
        return synced

    def clean(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove records with missing or invalid values.

        A record is dropped if it is empty or any of its values is None
        or NaN (for float fields).

        Args:
            data: List of record dictionaries.

        Returns:
            Cleaned list of records.
        """
        original_count = len(data)
        cleaned: list[dict[str, Any]] = []
        for record in data:
            if not record:
                continue
            if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in record.values()):
                continue
            cleaned.append(record)

        removed = original_count - len(cleaned)
        self._stats["clean_operations"] += 1
        self._stats["records_removed"] += removed
        logger.info("Cleaned %d records -> %d (removed %d)", original_count, len(cleaned), removed)
        return cleaned

    def transform(self, data: list[dict[str, Any]], transform_type: str) -> list[dict[str, Any]]:
        """Apply a transformation to the data.

        Args:
            data: List of record dictionaries.
            transform_type: One of ``"normalize"``, ``"resample"``,
                ``"filter"``, or ``"aggregate"``.

        Returns:
            Transformed list of records.

        Raises:
            ValueError: If ``transform_type`` is not supported.
        """
        if transform_type not in SUPPORTED_TRANSFORMS:
            raise ValueError(
                f"Unsupported transform: {transform_type!r}. "
                f"Supported: {sorted(SUPPORTED_TRANSFORMS)}"
            )

        if transform_type == "normalize":
            result = self._normalize(data)
        elif transform_type == "resample":
            result = self._resample(data)
        elif transform_type == "filter":
            result = self._filter(data)
        else:
            result = self._aggregate(data)

        self._stats["transform_operations"] += 1
        self._stats["records_transformed"] += len(result)
        logger.info(
            "Applied %s transform: %d -> %d records",
            transform_type,
            len(data),
            len(result),
        )
        return result

    def validate(self, data: list[dict[str, Any]]) -> bool:
        """Validate that all records have consistent keys and non-empty values.

        Args:
            data: List of record dictionaries.

        Returns:
            True if all records are valid, False otherwise.
        """
        self._stats["validate_operations"] += 1
        if not data:
            logger.warning("Validation failed: empty dataset")
            return False

        expected_keys: set[str] | None = None
        for record in data:
            if not record:
                logger.warning("Validation failed: empty record")
                return False
            keys = set(record.keys())
            if expected_keys is None:
                expected_keys = keys
            elif keys != expected_keys:
                logger.warning("Validation failed: inconsistent keys")
                return False

        logger.info("Validation passed for %d records", len(data))
        return True

    def get_processing_stats(self) -> dict[str, int]:
        """Return processing statistics."""
        return dict(self._stats)

    @staticmethod
    def _normalize(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize numeric fields to [0, 1] range per column."""
        if not data:
            return []
        numeric_keys = [k for k in data[0] if all(isinstance(r.get(k), int | float) for r in data)]
        if not numeric_keys:
            return list(data)

        result: list[dict[str, Any]] = []
        for record in data:
            new_record = dict(record)
            for key in numeric_keys:
                values = [r[key] for r in data]
                min_val = min(values)
                max_val = max(values)
                range_val = max_val - min_val
                if range_val == 0:
                    new_record[key] = 0.0
                else:
                    new_record[key] = (record[key] - min_val) / range_val
            result.append(new_record)
        return result

    @staticmethod
    def _resample(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Downsample by taking every other record."""
        return data[::2]

    @staticmethod
    def _filter(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out records where any numeric value is negative."""
        return [
            record
            for record in data
            if not any(isinstance(v, int | float) and v < 0 for v in record.values())
        ]

    @staticmethod
    def _aggregate(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Aggregate numeric fields into a single summary record."""
        if not data:
            return []
        summary: dict[str, Any] = {}
        for key in data[0]:
            values = [r[key] for r in data if isinstance(r.get(key), int | float)]
            if values:
                summary[key] = sum(values) / len(values)
            else:
                summary[key] = data[0][key]
        return [summary]
