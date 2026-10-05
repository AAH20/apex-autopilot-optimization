"""Backup and restore manager for apex-autopilot-optimization.

Stores named backups as ``<name>.bak`` payload files plus ``<name>.meta.json``
metadata sidecars inside the configured backup directory. Supports optional
gzip compression, XOR-stream encryption, retention policies, and integrity
verification via SHA-256 checksums.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from apex_autopilot_optimization.backup.config import BackupConfig
from apex_autopilot_optimization.backup.metadata import BackupMetadata

_BACKUP_VERSION = "1.0.0"

# Payload type tags so restore can distinguish str / bytes / JSON unambiguously.
_TAG_STR = b"\x00"
_TAG_BYTES = b"\x01"
_TAG_JSON = b"\x02"


def _xor_stream(data: bytes, key: str) -> bytes:
    """XOR data with a repeating key (symmetric, stdlib-only)."""
    key_bytes = key.encode("utf-8")
    if not key_bytes:
        return data
    return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))


class BackupManager:
    """Create, restore, list, delete, and verify named backups."""

    def __init__(self, config: BackupConfig) -> None:
        self.config = config
        self._dir = Path(config.backup_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------

    def _bak_path(self, name: str) -> Path:
        return self._dir / f"{name}.bak"

    def _meta_path(self, name: str) -> Path:
        return self._dir / f"{name}.meta.json"

    # -- public API ----------------------------------------------------------

    def create_backup(self, name: str, data: Any) -> BackupMetadata:
        """Create (or overwrite) a backup with the given name.

        Args:
            name: Backup name; must be non-empty.
            data: Payload to store. ``str``/``bytes`` are stored raw;
                anything else is JSON-serialized.

        Returns:
            The BackupMetadata for the stored backup.
        """
        if not name:
            raise ValueError("backup name must be non-empty")

        plaintext = self._serialize(data)
        raw = plaintext
        if self.config.compression:
            raw = gzip.compress(raw)
        if self.config.encryption:
            raw = _xor_stream(raw, self.config.key)

        bak_path = self._bak_path(name)
        bak_path.write_bytes(raw)

        # Checksum covers the plaintext payload so that both file corruption
        # and a wrong decryption key are detected on restore/verify.
        meta = BackupMetadata(
            name=name,
            timestamp=time.time(),
            size_bytes=len(raw),
            checksum=hashlib.sha256(plaintext).hexdigest(),
            version=_BACKUP_VERSION,
        )
        self._meta_path(name).write_text(json.dumps(meta.to_dict(), indent=2))

        self._enforce_retention()
        return meta

    def _decode(self, name: str) -> bytes:
        """Load a backup, verify its integrity, and return the plaintext bytes.

        Raises:
            FileNotFoundError: If the backup does not exist.
            ValueError: If the file is corrupted or the decryption key is wrong.
        """
        bak_path = self._bak_path(name)
        if not bak_path.is_file():
            raise FileNotFoundError(f"backup not found: {name}")

        raw = bak_path.read_bytes()
        if self.config.encryption:
            raw = _xor_stream(raw, self.config.key)
        if self.config.compression:
            raw = gzip.decompress(raw)

        meta = self.get_backup_info(name)
        if hashlib.sha256(raw).hexdigest() != meta.checksum:
            raise ValueError(
                f"backup {name!r} failed integrity check (wrong key or corrupted file)"
            )
        return raw

    def restore_backup(self, name: str) -> Any:
        """Restore a backup payload, reversing encryption/compression."""
        return self._deserialize(self._decode(name))

    def list_backups(self) -> list[str]:
        """Return backup names sorted by creation timestamp (oldest first)."""
        metas = []
        for meta_file in self._dir.glob("*.meta.json"):
            try:
                meta = BackupMetadata.from_dict(json.loads(meta_file.read_text()))
            except (ValueError, KeyError, OSError):
                continue
            metas.append(meta)
        metas.sort(key=lambda m: m.timestamp)
        return [m.name for m in metas]

    def delete_backup(self, name: str) -> None:
        """Delete a backup and its metadata sidecar."""
        bak_path = self._bak_path(name)
        if not bak_path.is_file():
            raise FileNotFoundError(f"backup not found: {name}")
        bak_path.unlink()
        self._meta_path(name).unlink(missing_ok=True)

    def get_backup_info(self, name: str) -> BackupMetadata:
        """Return the stored metadata for a backup."""
        meta_path = self._meta_path(name)
        if not meta_path.is_file():
            raise FileNotFoundError(f"backup not found: {name}")
        return BackupMetadata.from_dict(json.loads(meta_path.read_text()))

    def verify_backup(self, name: str) -> bool:
        """Verify a backup's integrity by recomputing its SHA-256 checksum."""
        bak_path = self._bak_path(name)
        if not bak_path.is_file():
            raise FileNotFoundError(f"backup not found: {name}")
        try:
            meta = self.get_backup_info(name)
        except FileNotFoundError:
            return False
        digest = hashlib.sha256(bak_path.read_bytes()).hexdigest()
        return digest == meta.checksum

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _serialize(data: Any) -> bytes:
        if isinstance(data, bytes):
            return _TAG_BYTES + data
        if isinstance(data, str):
            return _TAG_STR + data.encode("utf-8")
        return _TAG_JSON + json.dumps(data).encode("utf-8")

    @staticmethod
    def _deserialize(raw: bytes) -> Any:
        if raw.startswith(_TAG_BYTES):
            return raw[1:]
        if raw.startswith(_TAG_STR):
            return raw[1:].decode("utf-8")
        if raw.startswith(_TAG_JSON):
            return json.loads(raw[1:].decode("utf-8"))
        # Legacy untagged payload: try JSON, then UTF-8, else raw bytes.
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw

    def _enforce_retention(self) -> None:
        """Apply max_backups and retention_days policies."""
        names = self.list_backups()

        # Age-based retention.
        cutoff = time.time() - self.config.retention_days * 86400
        for name in names:
            try:
                meta = self.get_backup_info(name)
            except FileNotFoundError:
                continue
            if meta.timestamp < cutoff:
                self.delete_backup(name)

        # Count-based retention (oldest first).
        names = self.list_backups()
        while len(names) > self.config.max_backups:
            self.delete_backup(names.pop(0))


class RestoreManager:
    """Read-only restore helpers over an existing backup directory."""

    def __init__(self, config: BackupConfig) -> None:
        self.config = config
        self._manager = BackupManager(config)

    def restore_backup(self, name: str) -> Any:
        """Restore a named backup."""
        return self._manager.restore_backup(name)

    def restore_latest(self) -> Any:
        """Restore the most recently created backup."""
        names = self._manager.list_backups()
        if not names:
            raise FileNotFoundError("no backups available")
        return self._manager.restore_backup(names[-1])

    def restore_to_file(self, name: str, dest: str) -> None:
        """Restore a backup and write the raw payload to a file."""
        data = self._manager.restore_backup(name)
        if isinstance(data, bytes):
            Path(dest).write_bytes(data)
        elif isinstance(data, str):
            Path(dest).write_text(data, encoding="utf-8")
        else:
            Path(dest).write_text(json.dumps(data), encoding="utf-8")
