"""Backup metadata structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BackupMetadata:
    """Metadata describing a single backup.

    Attributes:
        name: Backup name (used as the file stem).
        timestamp: Unix timestamp of creation time.
        size_bytes: Size of the stored backup file in bytes.
        checksum: Hex SHA-256 of the stored backup file bytes.
        version: Backup format version string.
    """

    name: str
    timestamp: float
    size_bytes: int
    checksum: str
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for JSON storage."""
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> BackupMetadata:
        """Deserialize from a plain dictionary."""
        return cls(
            name=str(raw["name"]),
            timestamp=float(raw["timestamp"]),
            size_bytes=int(raw["size_bytes"]),
            checksum=str(raw["checksum"]),
            version=str(raw.get("version", "1.0.0")),
        )
