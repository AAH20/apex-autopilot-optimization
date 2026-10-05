"""Tests for backup, restore, and disaster recovery."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from apex_autopilot_optimization.backup import (
    BackupConfig,
    BackupManager,
    BackupMetadata,
    DRPlan,
    RestoreManager,
    get_dr_plan,
    validate_dr_plan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(tmp_path: Path, **overrides: object) -> BackupConfig:
    defaults: dict[str, object] = {
        "backup_dir": str(tmp_path / "backups"),
        "max_backups": 5,
        "compression": False,
        "encryption": False,
        "retention_days": 30,
    }
    defaults.update(overrides)
    return BackupConfig(**defaults)  # type: ignore[arg-type]


def _make_manager(tmp_path: Path, **overrides: object) -> BackupManager:
    return BackupManager(_config(tmp_path, **overrides))


# ---------------------------------------------------------------------------
# Backup creation
# ---------------------------------------------------------------------------


class TestBackupCreation:
    def test_create_backup_writes_file(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", {"state": [1, 2, 3]})

        backup_dir = tmp_path / "backups"
        assert backup_dir.is_dir()
        assert (backup_dir / "b1.bak").is_file()
        assert (backup_dir / "b1.meta.json").is_file()

    def test_create_backup_returns_metadata(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        meta = mgr.create_backup("b1", "payload")

        assert isinstance(meta, BackupMetadata)
        assert meta.name == "b1"
        assert meta.timestamp > 0
        assert meta.size_bytes > 0
        assert len(meta.checksum) == 64  # sha256 hex
        assert meta.version

    def test_create_backup_accepts_bytes(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        meta = mgr.create_backup("b1", b"\x00\x01\x02raw-bytes")
        assert meta.size_bytes > 0

    def test_create_backup_overwrites_existing(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "first")
        mgr.create_backup("b1", "second")

        assert mgr.restore_backup("b1") == "second"
        assert len(mgr.list_backups()) == 1

    def test_create_backup_rejects_empty_name(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        with pytest.raises(ValueError, match="name"):
            mgr.create_backup("", "data")


# ---------------------------------------------------------------------------
# Backup restore
# ---------------------------------------------------------------------------


class TestBackupRestore:
    def test_restore_roundtrip_str(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "hello world")
        assert mgr.restore_backup("b1") == "hello world"

    def test_restore_roundtrip_dict(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        payload = {"ekf_state": [0.0] * 12, "covariance": [[1.0]], "label": "checkpoint"}
        mgr.create_backup("b1", payload)
        assert mgr.restore_backup("b1") == payload

    def test_restore_roundtrip_bytes(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", b"\xde\xad\xbe\xef")
        assert mgr.restore_backup("b1") == b"\xde\xad\xbe\xef"

    def test_restore_missing_raises(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.restore_backup("nope")


# ---------------------------------------------------------------------------
# Backup listing
# ---------------------------------------------------------------------------


class TestBackupListing:
    def test_list_backups_empty(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        assert mgr.list_backups() == []

    def test_list_backups_multiple(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        for name in ("a", "b", "c"):
            mgr.create_backup(name, "x")

        assert sorted(mgr.list_backups()) == ["a", "b", "c"]

    def test_list_backups_sorted_by_timestamp(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("first", "x")
        time.sleep(0.01)
        mgr.create_backup("second", "x")

        assert mgr.list_backups() == ["first", "second"]


# ---------------------------------------------------------------------------
# Backup deletion
# ---------------------------------------------------------------------------


class TestBackupDeletion:
    def test_delete_backup(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "data")
        mgr.delete_backup("b1")

        assert mgr.list_backups() == []
        assert not (tmp_path / "backups" / "b1.bak").exists()
        assert not (tmp_path / "backups" / "b1.meta.json").exists()

    def test_delete_missing_raises(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.delete_backup("nope")

    def test_delete_one_keeps_others(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("a", "1")
        mgr.create_backup("b", "2")
        mgr.delete_backup("a")

        assert mgr.list_backups() == ["b"]


# ---------------------------------------------------------------------------
# Backup info
# ---------------------------------------------------------------------------


class TestBackupInfo:
    def test_get_backup_info(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        created = mgr.create_backup("b1", "payload")
        info = mgr.get_backup_info("b1")

        assert isinstance(info, BackupMetadata)
        assert info.name == "b1"
        assert info.size_bytes == created.size_bytes
        assert info.checksum == created.checksum

    def test_get_backup_info_missing_raises(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.get_backup_info("nope")


# ---------------------------------------------------------------------------
# Backup verification
# ---------------------------------------------------------------------------


class TestBackupVerification:
    def test_verify_backup_valid(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "data")
        assert mgr.verify_backup("b1") is True

    def test_verify_backup_corrupted(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "data")

        # Corrupt the payload after creation.
        bak = tmp_path / "backups" / "b1.bak"
        bak.write_bytes(bak.read_bytes() + b"tampered")

        assert mgr.verify_backup("b1") is False

    def test_verify_backup_missing_raises(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.verify_backup("nope")


# ---------------------------------------------------------------------------
# Backup config
# ---------------------------------------------------------------------------


class TestBackupConfig:
    def test_config_stores_fields(self, tmp_path: Path) -> None:
        cfg = _config(
            tmp_path,
            max_backups=3,
            compression=True,
            encryption=True,
            retention_days=7,
        )
        assert cfg.backup_dir == str(tmp_path / "backups")
        assert cfg.max_backups == 3
        assert cfg.compression is True
        assert cfg.encryption is True
        assert cfg.retention_days == 7

    def test_config_rejects_invalid_values(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            _config(tmp_path, max_backups=0)
        with pytest.raises(ValueError):
            _config(tmp_path, retention_days=0)


# ---------------------------------------------------------------------------
# Backup metadata
# ---------------------------------------------------------------------------


class TestBackupMetadata:
    def test_metadata_fields(self) -> None:
        meta = BackupMetadata(
            name="b1",
            timestamp=123.456,
            size_bytes=42,
            checksum="abc123",
            version="1.0.0",
        )
        assert meta.name == "b1"
        assert meta.timestamp == 123.456
        assert meta.size_bytes == 42
        assert meta.checksum == "abc123"
        assert meta.version == "1.0.0"

    def test_metadata_serializes_to_json(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "data")

        raw = json.loads((tmp_path / "backups" / "b1.meta.json").read_text())
        assert raw["name"] == "b1"
        assert raw["size_bytes"] > 0
        assert len(raw["checksum"]) == 64
        assert raw["version"]


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------


class TestBackupCompression:
    def test_compressed_backup_roundtrip(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, compression=True)
        payload = "compressible " * 500
        mgr.create_backup("b1", payload)
        assert mgr.restore_backup("b1") == payload

    def test_compressed_file_smaller_than_plaintext(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, compression=True)
        payload = "compressible " * 500
        mgr.create_backup("b1", payload)

        stored = (tmp_path / "backups" / "b1.bak").stat().st_size
        assert stored < len(payload)


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------


class TestBackupEncryption:
    def test_encrypted_backup_roundtrip(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, encryption=True)
        mgr.create_backup("b1", "secret state")
        assert mgr.restore_backup("b1") == "secret state"

    def test_encrypted_file_differs_from_plaintext(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, encryption=True)
        payload = "secret state"
        mgr.create_backup("b1", payload)

        stored = (tmp_path / "backups" / "b1.bak").read_bytes()
        assert payload.encode() not in stored

    def test_encrypted_backup_fails_without_key(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, encryption=True)
        mgr.create_backup("b1", "secret state")

        # A manager with a different key cannot restore the payload.
        other = BackupManager(_config(tmp_path, encryption=True, key="different-key"))
        with pytest.raises(ValueError):
            other.restore_backup("b1")


# ---------------------------------------------------------------------------
# Retention policy
# ---------------------------------------------------------------------------


class TestRetentionPolicy:
    def test_max_backups_enforced(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, max_backups=3)
        for i in range(5):
            mgr.create_backup(f"b{i}", "x")

        assert mgr.list_backups() == ["b2", "b3", "b4"]

    def test_retention_days_enforced(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, retention_days=1)
        mgr.create_backup("old", "x")

        # Backdate the old backup's metadata beyond the retention window.
        meta_path = tmp_path / "backups" / "old.meta.json"
        meta = json.loads(meta_path.read_text())
        meta["timestamp"] = time.time() - 2 * 24 * 3600
        meta_path.write_text(json.dumps(meta))

        mgr.create_backup("new", "x")

        assert mgr.list_backups() == ["new"]

    def test_retention_keeps_recent_backups(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path, retention_days=30)
        mgr.create_backup("b1", "x")
        mgr.create_backup("b2", "x")

        assert sorted(mgr.list_backups()) == ["b1", "b2"]


# ---------------------------------------------------------------------------
# RestoreManager
# ---------------------------------------------------------------------------


class TestRestoreManager:
    def test_restore_manager_roundtrip(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", {"k": "v"})

        restorer = RestoreManager(_config(tmp_path))
        assert restorer.restore_backup("b1") == {"k": "v"}

    def test_restore_manager_latest(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "older")
        time.sleep(0.01)
        mgr.create_backup("b2", "newer")

        restorer = RestoreManager(_config(tmp_path))
        assert restorer.restore_latest() == "newer"

    def test_restore_manager_latest_empty_raises(self, tmp_path: Path) -> None:
        restorer = RestoreManager(_config(tmp_path))
        with pytest.raises(FileNotFoundError):
            restorer.restore_latest()

    def test_restore_manager_to_file(self, tmp_path: Path) -> None:
        mgr = _make_manager(tmp_path)
        mgr.create_backup("b1", "file-content")

        dest = tmp_path / "restored.txt"
        restorer = RestoreManager(_config(tmp_path))
        restorer.restore_to_file("b1", str(dest))

        assert dest.read_text() == "file-content"


# ---------------------------------------------------------------------------
# DR plan
# ---------------------------------------------------------------------------


class TestDRPlan:
    def test_get_dr_plan_critical(self) -> None:
        plan = get_dr_plan("critical")
        assert isinstance(plan, DRPlan)
        assert plan.rto_seconds > 0
        assert plan.rpo_seconds > 0
        assert plan.backup_schedule
        assert len(plan.recovery_steps) > 0

    def test_get_dr_plan_standard(self) -> None:
        plan = get_dr_plan("standard")
        assert isinstance(plan, DRPlan)
        # Higher tiers have stricter (smaller) RTO targets.
        assert plan.rto_seconds <= get_dr_plan("basic").rto_seconds

    def test_get_dr_plan_basic(self) -> None:
        plan = get_dr_plan("basic")
        assert isinstance(plan, DRPlan)

    def test_get_dr_plan_invalid_tier_raises(self) -> None:
        with pytest.raises(ValueError):
            get_dr_plan("platinum")

    def test_validate_dr_plan_valid(self) -> None:
        plan = get_dr_plan("critical")
        assert validate_dr_plan(plan) is True

    def test_validate_dr_plan_invalid(self) -> None:
        bad = DRPlan(
            rto_seconds=0,
            rpo_seconds=0,
            backup_schedule="",
            recovery_steps=[],
        )
        assert validate_dr_plan(bad) is False

    def test_validate_dr_plan_missing_steps(self) -> None:
        bad = DRPlan(
            rto_seconds=10,
            rpo_seconds=5,
            backup_schedule="hourly",
            recovery_steps=[],
        )
        assert validate_dr_plan(bad) is False
