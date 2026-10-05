"""Dataset version management."""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


class DataVersionManager:
    """Manage versions of datasets with metadata tracking.

    Each version is an immutable snapshot of the dataset at creation time.
    """

    def __init__(self) -> None:
        self._versions: dict[str, list[dict[str, Any]]] = {}

    def create_version(self, dataset_id: str, metadata: dict[str, Any] | None = None) -> int:
        """Create a new version for a dataset.

        Args:
            dataset_id: The dataset to version.
            metadata: Optional metadata to attach to this version.

        Returns:
            The new version number (1-based).
        """
        if dataset_id not in self._versions:
            self._versions[dataset_id] = []

        version_number = len(self._versions[dataset_id]) + 1
        version_entry = {
            "version": version_number,
            "dataset_id": dataset_id,
            "metadata": copy.deepcopy(metadata) if metadata else {},
        }
        self._versions[dataset_id].append(version_entry)
        logger.info("Created version %d for dataset %s", version_number, dataset_id)
        return version_number

    def get_version(self, dataset_id: str, version: int) -> dict[str, Any] | None:
        """Retrieve a specific version of a dataset.

        Args:
            dataset_id: The dataset ID.
            version: The version number (1-based).

        Returns:
            The version entry, or None if not found.
        """
        versions = self._versions.get(dataset_id, [])
        for entry in versions:
            if entry["version"] == version:
                return copy.deepcopy(entry)
        return None

    def list_versions(self, dataset_id: str) -> list[dict[str, Any]]:
        """List all versions of a dataset.

        Args:
            dataset_id: The dataset ID.

        Returns:
            List of version entries (empty if dataset has no versions).
        """
        return copy.deepcopy(self._versions.get(dataset_id, []))

    def get_latest_version(self, dataset_id: str) -> dict[str, Any] | None:
        """Get the latest version of a dataset.

        Args:
            dataset_id: The dataset ID.

        Returns:
            The latest version entry, or None if no versions exist.
        """
        versions = self._versions.get(dataset_id, [])
        if not versions:
            return None
        return copy.deepcopy(versions[-1])
