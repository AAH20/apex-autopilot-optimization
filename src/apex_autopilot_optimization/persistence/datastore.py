"""Key-value data store with JSON file persistence."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class DataStore(ABC):
    """Abstract base class for key-value data stores."""

    @abstractmethod
    def save(self, key: str, value: Any) -> None:
        """Save a value under a key."""
        ...

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Get a value by key."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a key-value pair."""
        ...

    @abstractmethod
    def list_keys(self) -> list[str]:
        """List all keys."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all data."""
        ...


class FileDataStore(DataStore):
    """JSON file-based key-value data store."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load data from file if it exists."""
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                self._data = json.load(f)

    def _flush(self) -> None:
        """Write data to file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def save(self, key: str, value: Any) -> None:
        """Save a value under a key."""
        self._data[key] = value
        self._flush()

    def get(self, key: str) -> Any | None:
        """Get a value by key."""
        return self._data.get(key)

    def delete(self, key: str) -> None:
        """Delete a key-value pair."""
        if key in self._data:
            del self._data[key]
            self._flush()

    def list_keys(self) -> list[str]:
        """List all keys."""
        return list(self._data.keys())

    def clear(self) -> None:
        """Clear all data."""
        self._data.clear()
        self._flush()
