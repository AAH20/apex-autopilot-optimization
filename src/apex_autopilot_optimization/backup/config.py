"""Backup configuration for apex-autopilot-optimization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackupConfig:
    """Configuration for backup and restore operations.

    Attributes:
        backup_dir: Directory where backup files are stored.
        max_backups: Maximum number of backups to retain (oldest deleted first).
        compression: Whether to compress backup payloads with gzip.
        encryption: Whether to encrypt backup payloads (XOR stream with key).
        retention_days: Delete backups older than this many days.
        key: Encryption key used when encryption is enabled.
    """

    backup_dir: str
    max_backups: int = 5
    compression: bool = False
    encryption: bool = False
    retention_days: int = 30
    key: str = "apex-default-backup-key"

    def __post_init__(self) -> None:
        if self.max_backups <= 0:
            raise ValueError(f"max_backups must be positive, got {self.max_backups}")
        if self.retention_days <= 0:
            raise ValueError(f"retention_days must be positive, got {self.retention_days}")
        if not self.backup_dir:
            raise ValueError("backup_dir must be a non-empty path")
