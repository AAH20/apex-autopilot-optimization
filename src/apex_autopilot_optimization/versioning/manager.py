"""High-level version management facade.

:class:`VersionManager` tracks the current application version and exposes the
migration registry operations so callers have a single entry point for version
bookkeeping.
"""

from __future__ import annotations

from apex_autopilot_optimization.versioning.migration import (
    Migration,
    MigrationManager,
)
from apex_autopilot_optimization.versioning.version import Version


class VersionManager:
    """Coordinates the current version with the migration registry."""

    def __init__(self, initial_version: Version | None = None) -> None:
        self._current_version = initial_version or Version(0, 1, 0)
        self._migrations = MigrationManager()

    @property
    def current_version(self) -> Version:
        """The version currently being tracked."""
        return self._current_version

    def bump_major(self) -> Version:
        """Bump the tracked version's major component and return it."""
        self._current_version = self._current_version.bump_major()
        return self._current_version

    def bump_minor(self) -> Version:
        """Bump the tracked version's minor component and return it."""
        self._current_version = self._current_version.bump_minor()
        return self._current_version

    def bump_patch(self) -> Version:
        """Bump the tracked version's patch component and return it."""
        self._current_version = self._current_version.bump_patch()
        return self._current_version

    def register_migration(self, migration: Migration) -> None:
        """Register a migration with the underlying manager."""
        self._migrations.register_migration(migration)

    def get_migration_path(
        self, from_version: Version, to_version: Version
    ) -> list[Migration]:
        """Return the migration path between two versions."""
        return self._migrations.get_migration_path(from_version, to_version)

    def migrate(self, from_version: Version, to_version: Version) -> list[Migration]:
        """Apply migrations from ``from_version`` to ``to_version``."""
        return self._migrations.migrate(from_version, to_version)

    def get_applied_migrations(self) -> list[Migration]:
        """Return applied migrations in order."""
        return self._migrations.get_applied_migrations()

    def rollback_migration(self, migration: Migration) -> None:
        """Roll back a previously applied migration."""
        self._migrations.rollback_migration(migration)
