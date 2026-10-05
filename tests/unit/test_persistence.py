"""Tests for the persistence layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from apex_autopilot_optimization.persistence import (
    CheckpointManager,
    Database,
    FileDataStore,
    Migration,
    MigrationManager,
    PlanningResultRepository,
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_db(path: Path) -> Database:
    db = Database()
    db.connect(str(path))
    return db


def _make_migration(version: int = 1, name: str = "test_migration") -> Migration:
    table_name = f"test_table_{version}"
    return Migration(
        version=version,
        name=name,
        up=f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, value TEXT);",
        down=f"DROP TABLE IF EXISTS {table_name};",
    )


# ── Database ────────────────────────────────────────────────────────────────


class TestDatabase:
    """Tests for Database class."""

    def test_connect_creates_connection(self, tmp_path: Path) -> None:
        db = Database()
        db.connect(str(tmp_path / "test.db"))
        assert db._connection is not None
        db.close()

    def test_connect_creates_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = Database()
        db.connect(str(db_path))
        assert db_path.exists()
        db.close()

    def test_execute_creates_table(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
        # Verify table exists by inserting
        db.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
        result = db.fetchone("SELECT name FROM users WHERE id = 1")
        assert result is not None
        assert result[0] == "Alice"
        db.close()

    def test_fetchall_returns_all_rows(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT);")
        db.execute("INSERT INTO items (val) VALUES (?)", ("a",))
        db.execute("INSERT INTO items (val) VALUES (?)", ("b",))
        db.execute("INSERT INTO items (val) VALUES (?)", ("c",))
        rows = db.fetchall("SELECT val FROM items ORDER BY id")
        assert len(rows) == 3
        assert [r[0] for r in rows] == ["a", "b", "c"]
        db.close()

    def test_fetchone_returns_single_row(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE single (id INTEGER PRIMARY KEY, data TEXT);")
        db.execute("INSERT INTO single (data) VALUES (?)", ("hello",))
        row = db.fetchone("SELECT data FROM single WHERE id = 1")
        assert row is not None
        assert row[0] == "hello"
        db.close()

    def test_fetchone_returns_none_when_no_match(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE empty (id INTEGER PRIMARY KEY);")
        row = db.fetchone("SELECT * FROM empty WHERE id = 999")
        assert row is None
        db.close()

    def test_fetchall_returns_empty_list_when_no_rows(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE no_rows (id INTEGER PRIMARY KEY);")
        rows = db.fetchall("SELECT * FROM no_rows")
        assert rows == []
        db.close()

    def test_transaction_commits_on_success(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE tx (id INTEGER PRIMARY KEY, val TEXT);")
        with db.transaction():
            db.execute("INSERT INTO tx (val) VALUES (?)", ("committed",))
        # Verify data persists after transaction
        row = db.fetchone("SELECT val FROM tx WHERE id = 1")
        assert row is not None
        assert row[0] == "committed"
        db.close()

    def test_transaction_rolls_back_on_exception(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE tx (id INTEGER PRIMARY KEY, val TEXT);")
        with pytest.raises(ValueError, match="force rollback"), db.transaction():
            db.execute("INSERT INTO tx (val) VALUES (?)", ("should_not_exist",))
            raise ValueError("force rollback")
        # Verify data was rolled back
        rows = db.fetchall("SELECT * FROM tx")
        assert rows == []
        db.close()

    def test_close_closes_connection(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.close()
        assert db._connection is None

    def test_execute_with_params(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        db.execute("CREATE TABLE params (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);")
        db.execute("INSERT INTO params (name, age) VALUES (?, ?)", ("Bob", 30))
        row = db.fetchone("SELECT name, age FROM params WHERE id = 1")
        assert row is not None
        assert row[0] == "Bob"
        assert row[1] == 30
        db.close()


# ── Repository ──────────────────────────────────────────────────────────────


class TestPlanningResultRepository:
    """Tests for PlanningResultRepository CRUD operations."""

    def _make_repo(self, tmp_path: Path) -> PlanningResultRepository:
        db = _make_db(tmp_path / "repo.db")
        db.execute(
            "CREATE TABLE planning_results ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "success INTEGER, "
            "cost REAL, "
            "message TEXT);"
        )
        return PlanningResultRepository(db)

    def test_save_and_get(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        entity = {"success": True, "cost": 42.0, "message": "Path found"}
        entity_id = repo.save(entity)
        assert entity_id is not None
        result = repo.get(entity_id)
        assert result is not None
        assert result["success"] == 1  # SQLite stores bool as int
        assert result["cost"] == 42.0
        assert result["message"] == "Path found"

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        result = repo.get(9999)
        assert result is None

    def test_list_all(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        repo.save({"success": True, "cost": 1.0, "message": "first"})
        repo.save({"success": False, "cost": 2.0, "message": "second"})
        repo.save({"success": True, "cost": 3.0, "message": "third"})
        results = repo.list_all()
        assert len(results) == 3

    def test_list_all_empty(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        results = repo.list_all()
        assert results == []

    def test_update(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        entity_id = repo.save({"success": True, "cost": 10.0, "message": "original"})
        repo.update({"id": entity_id, "success": False, "cost": 20.0, "message": "updated"})
        result = repo.get(entity_id)
        assert result is not None
        assert result["success"] == 0
        assert result["cost"] == 20.0
        assert result["message"] == "updated"

    def test_delete(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        entity_id = repo.save({"success": True, "cost": 5.0, "message": "to_delete"})
        repo.delete(entity_id)
        result = repo.get(entity_id)
        assert result is None

    def test_delete_nonexistent_does_not_raise(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        repo.delete(9999)  # Should not raise

    def test_save_returns_incrementing_ids(self, tmp_path: Path) -> None:
        repo = self._make_repo(tmp_path)
        id1 = repo.save({"success": True, "cost": 1.0, "message": "a"})
        id2 = repo.save({"success": True, "cost": 2.0, "message": "b"})
        id3 = repo.save({"success": True, "cost": 3.0, "message": "c"})
        assert id1 != id2
        assert id2 != id3


# ── Migration ───────────────────────────────────────────────────────────────


class TestMigration:
    """Tests for Migration dataclass."""

    def test_migration_creation(self) -> None:
        m = Migration(
            version=1,
            name="create_users",
            up="CREATE TABLE users (id INTEGER);",
            down="DROP TABLE users;",
        )
        assert m.version == 1
        assert m.name == "create_users"
        assert "CREATE TABLE" in m.up
        assert "DROP TABLE" in m.down


class TestMigrationManager:
    """Tests for MigrationManager."""

    def _make_manager(self, tmp_path: Path) -> MigrationManager:
        db = _make_db(tmp_path / "migrations.db")
        return MigrationManager(db)

    def test_apply_migration(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        migration = _make_migration(1, "create_test")
        mgr.apply_migration(migration)
        # Verify table was created
        result = mgr.db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table_1'"
        )
        assert result is not None

    def test_get_applied_migrations(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        m1 = _make_migration(1, "first")
        m2 = _make_migration(2, "second")
        mgr.apply_migration(m1)
        mgr.apply_migration(m2)
        applied = mgr.get_applied_migrations()
        assert len(applied) == 2
        assert applied[0]["version"] == 1
        assert applied[1]["version"] == 2

    def test_get_pending_migrations(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        m1 = _make_migration(1, "first")
        m2 = _make_migration(2, "second")
        m3 = _make_migration(3, "third")
        mgr.apply_migration(m1)
        pending = mgr.get_pending_migrations([m1, m2, m3])
        assert len(pending) == 2
        assert pending[0].version == 2
        assert pending[1].version == 3

    def test_rollback_migration(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        migration = _make_migration(1, "to_rollback")
        mgr.apply_migration(migration)
        # Verify table exists
        result = mgr.db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table_1'"
        )
        assert result is not None
        # Rollback
        mgr.rollback_migration(migration)
        # Verify table is gone
        result = mgr.db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table_1'"
        )
        assert result is None

    def test_rollback_removes_from_applied(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        migration = _make_migration(1, "to_rollback")
        mgr.apply_migration(migration)
        mgr.rollback_migration(migration)
        applied = mgr.get_applied_migrations()
        assert len(applied) == 0

    def test_apply_migration_records_version(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        migration = _make_migration(42, "versioned")
        mgr.apply_migration(migration)
        applied = mgr.get_applied_migrations()
        assert len(applied) == 1
        assert applied[0]["version"] == 42
        assert applied[0]["name"] == "versioned"


# ── DataStore ───────────────────────────────────────────────────────────────


class TestFileDataStore:
    """Tests for FileDataStore implementation."""

    def _make_store(self, tmp_path: Path) -> FileDataStore:
        return FileDataStore(str(tmp_path / "store.json"))

    def test_save_and_get(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.save("key1", {"data": "value1"})
        result = store.get("key1")
        assert result == {"data": "value1"}

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        result = store.get("nonexistent")
        assert result is None

    def test_delete(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.save("key1", "value1")
        store.delete("key1")
        result = store.get("key1")
        assert result is None

    def test_delete_nonexistent_does_not_raise(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.delete("nonexistent")  # Should not raise

    def test_list_keys(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.save("a", 1)
        store.save("b", 2)
        store.save("c", 3)
        keys = store.list_keys()
        assert set(keys) == {"a", "b", "c"}

    def test_list_keys_empty(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        keys = store.list_keys()
        assert keys == []

    def test_clear(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.save("a", 1)
        store.save("b", 2)
        store.clear()
        keys = store.list_keys()
        assert keys == []

    def test_overwrite_existing_key(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.save("key", "old_value")
        store.save("key", "new_value")
        result = store.get("key")
        assert result == "new_value"

    def test_persists_to_file(self, tmp_path: Path) -> None:
        store_path = str(tmp_path / "persist.json")
        store = FileDataStore(store_path)
        store.save("persistent", {"nested": [1, 2, 3]})
        # Create new store instance pointing to same file
        store2 = FileDataStore(store_path)
        result = store2.get("persistent")
        assert result == {"nested": [1, 2, 3]}

    def test_save_various_types(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.save("str", "hello")
        store.save("int", 42)
        store.save("float", 3.14)
        store.save("bool", True)
        store.save("list", [1, 2, 3])
        store.save("dict", {"a": 1})
        store.save("none", None)
        assert store.get("str") == "hello"
        assert store.get("int") == 42
        assert store.get("float") == 3.14
        assert store.get("bool") is True
        assert store.get("list") == [1, 2, 3]
        assert store.get("dict") == {"a": 1}
        assert store.get("none") is None


# ── CheckpointManager ────────────────────────────────────────────────────────


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def _make_manager(self, tmp_path: Path) -> CheckpointManager:
        return CheckpointManager(str(tmp_path / "checkpoints"))

    def test_save_and_load_checkpoint(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        data = {"state": "running", "progress": 0.5, "data": [1, 2, 3]}
        mgr.save_checkpoint("checkpoint1", data)
        loaded = mgr.load_checkpoint("checkpoint1")
        assert loaded == data

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        result = mgr.load_checkpoint("nonexistent")
        assert result is None

    def test_list_checkpoints(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        mgr.save_checkpoint("cp1", {"step": 1})
        mgr.save_checkpoint("cp2", {"step": 2})
        mgr.save_checkpoint("cp3", {"step": 3})
        checkpoints = mgr.list_checkpoints()
        assert set(checkpoints) == {"cp1", "cp2", "cp3"}

    def test_list_checkpoints_empty(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        checkpoints = mgr.list_checkpoints()
        assert checkpoints == []

    def test_delete_checkpoint(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        mgr.save_checkpoint("to_delete", {"data": "value"})
        mgr.delete_checkpoint("to_delete")
        result = mgr.load_checkpoint("to_delete")
        assert result is None

    def test_delete_nonexistent_does_not_raise(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        mgr.delete_checkpoint("nonexistent")  # Should not raise

    def test_get_latest_checkpoint(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        mgr.save_checkpoint("old", {"step": 1})
        mgr.save_checkpoint("middle", {"step": 2})
        mgr.save_checkpoint("new", {"step": 3})
        latest = mgr.get_latest_checkpoint()
        assert latest is not None
        assert latest[0] == "new"
        assert latest[1]["step"] == 3

    def test_get_latest_checkpoint_empty(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        latest = mgr.get_latest_checkpoint()
        assert latest is None

    def test_get_latest_after_delete(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        mgr.save_checkpoint("first", {"step": 1})
        mgr.save_checkpoint("second", {"step": 2})
        mgr.delete_checkpoint("second")
        latest = mgr.get_latest_checkpoint()
        assert latest is not None
        assert latest[0] == "first"

    def test_overwrite_checkpoint(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        mgr.save_checkpoint("cp", {"version": 1})
        mgr.save_checkpoint("cp", {"version": 2})
        loaded = mgr.load_checkpoint("cp")
        assert loaded == {"version": 2}

    def test_checkpoint_with_complex_data(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        data = {
            "trajectory": [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]],
            "metadata": {"algorithm": "RRT", "iterations": 500},
            "success": True,
            "cost": 42.5,
        }
        mgr.save_checkpoint("complex", data)
        loaded = mgr.load_checkpoint("complex")
        assert loaded == data


# ── Package exports ─────────────────────────────────────────────────────────


class TestPackageExports:
    """Tests that all expected symbols are exported from the package."""

    def test_database_exported(self) -> None:
        from apex_autopilot_optimization.persistence import Database as DB

        assert DB is not None

    def test_repository_exported(self) -> None:
        from apex_autopilot_optimization.persistence import Repository as Repo

        assert Repo is not None

    def test_migration_exported(self) -> None:
        from apex_autopilot_optimization.persistence import Migration as Mig

        assert Mig is not None

    def test_datastore_exported(self) -> None:
        from apex_autopilot_optimization.persistence import DataStore as DS

        assert DS is not None

    def test_checkpoint_manager_exported(self) -> None:
        from apex_autopilot_optimization.persistence import CheckpointManager as CM

        assert CM is not None
