"""Data storage ABC and in-memory implementation."""

from __future__ import annotations

import copy
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class DataStore(ABC):
    """Abstract base class for dataset storage backends."""

    @abstractmethod
    def save(self, dataset_id: str, data: Any) -> None:
        """Save data under a dataset ID."""
        ...

    @abstractmethod
    def get(self, dataset_id: str) -> Any | None:
        """Retrieve data by dataset ID, or None if not found."""
        ...

    @abstractmethod
    def list_datasets(self) -> list[str]:
        """List all dataset IDs in the store."""
        ...

    @abstractmethod
    def delete(self, dataset_id: str) -> bool:
        """Delete a dataset by ID. Returns True if it existed."""
        ...

    @abstractmethod
    def get_dataset_info(self, dataset_id: str) -> dict[str, Any] | None:
        """Return metadata about a dataset, or None if not found."""
        ...


class InMemoryDataStore(DataStore):
    """In-memory dataset store with deep-copy isolation."""

    def __init__(self) -> None:
        self._datasets: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def save(self, dataset_id: str, data: Any) -> None:
        """Save data under a dataset ID (deep-copied for isolation)."""
        self._datasets[dataset_id] = copy.deepcopy(data)
        self._metadata[dataset_id] = {
            "dataset_id": dataset_id,
            "size": len(data) if hasattr(data, "__len__") else 0,
        }
        logger.info("Saved dataset %s", dataset_id)

    def get(self, dataset_id: str) -> Any | None:
        """Retrieve data by dataset ID (deep-copied for isolation)."""
        data = self._datasets.get(dataset_id)
        return copy.deepcopy(data) if data is not None else None

    def list_datasets(self) -> list[str]:
        """List all dataset IDs in the store."""
        return list(self._datasets.keys())

    def delete(self, dataset_id: str) -> bool:
        """Delete a dataset by ID. Returns True if it existed."""
        existed = dataset_id in self._datasets
        if existed:
            del self._datasets[dataset_id]
            del self._metadata[dataset_id]
            logger.info("Deleted dataset %s", dataset_id)
        return existed

    def get_dataset_info(self, dataset_id: str) -> dict[str, Any] | None:
        """Return metadata about a dataset, or None if not found."""
        info = self._metadata.get(dataset_id)
        return dict(info) if info is not None else None
