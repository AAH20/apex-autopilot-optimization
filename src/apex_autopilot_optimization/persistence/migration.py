"""Database migration support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apex_autopilot_optimization.persistence.database import Database


@dataclass
class Migration:
    """A single database migration."""

    version: int
    name: str
    up: str
    down: str


class MigrationManager:
    """Manages database migrations."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._ensure_migration_table()

    def _ensure_migration_table(self) -> None:
        """Create the migrations tracking table if it doesn't exist."""
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "version INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )

    def apply_migration(self, migration: Migration) -> None:
        """Apply a migration and record it."""
        self.db.execute(migration.up)
        self.db.execute(
            "INSERT INTO _migrations (version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )

    def rollback_migration(self, migration: Migration) -> None:
        """Rollback a migration and remove its record."""
        self.db.execute(migration.down)
        self.db.execute("DELETE FROM _migrations WHERE version = ?", (migration.version,))

    def get_applied_migrations(self) -> list[dict[str, Any]]:
        """Get all applied migrations."""
        rows = self.db.fetchall("SELECT version, name FROM _migrations ORDER BY version")
        return [{"version": row[0], "name": row[1]} for row in rows]

    def get_pending_migrations(self, migrations: list[Migration]) -> list[Migration]:
        """Get migrations that haven't been applied yet."""
        applied = {m["version"] for m in self.get_applied_migrations()}
        return [m for m in migrations if m.version not in applied]
