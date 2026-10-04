"""Migration registration, path discovery, execution, and rollback.

Provides :class:`Migration`, a named forward/backward transformation between two
versions, and :class:`MigrationManager`, which stores migrations, finds the
ordered chain connecting two versions, applies them, and rolls them back.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from apex_autopilot_optimization.versioning.version import Version


@dataclass
class Migration:
    """A single forward/backward transformation between two versions.

    Attributes:
        from_version: Version the migration upgrades from.
        to_version: Version the migration upgrades to.
        name: Human-readable migration name.
        up: Callable performing the forward migration.
        down: Callable performing the rollback.
    """

    from_version: Version
    to_version: Version
    name: str
    up: Callable[[], None]
    down: Callable[[], None]


class MigrationManager:
    """Registers and applies an ordered graph of :class:`Migration` objects."""

    def __init__(self) -> None:
        self._migrations: list[Migration] = []
        self._applied: list[Migration] = []

    def register_migration(self, migration: Migration) -> None:
        """Register a migration.

        Raises:
            ValueError: If an equivalent ``from_version -> to_version``
                migration is already registered.
        """
        for existing in self._migrations:
            if (
                existing.from_version == migration.from_version
                and existing.to_version == migration.to_version
            ):
                raise ValueError(
                    f"Migration {existing.name!r} already registered for "
                    f"{migration.from_version.to_string()} -> "
                    f"{migration.to_version.to_string()}"
                )
        self._migrations.append(migration)

    def get_migration_path(
        self, from_version: Version, to_version: Version
    ) -> list[Migration]:
        """Return the ordered migrations connecting two versions.

        Performs a breadth-first search over registered migrations. Returns an
        empty list when ``from_version == to_version`` or when no path exists.
        """
        if from_version == to_version:
            return []

        adjacency: dict[Version, list[Migration]] = {}
        for migration in self._migrations:
            adjacency.setdefault(migration.from_version, []).append(migration)

        queue: deque[tuple[Version, list[Migration]]] = deque([(from_version, [])])
        visited: set[Version] = {from_version}
        while queue:
            current, path = queue.popleft()
            for migration in adjacency.get(current, []):
                next_version = migration.to_version
                if next_version == to_version:
                    return path + [migration]
                if next_version not in visited:
                    visited.add(next_version)
                    queue.append((next_version, path + [migration]))
        return []

    def migrate(self, from_version: Version, to_version: Version) -> list[Migration]:
        """Apply every migration on the path from ``from_version`` to ``to_version``.

        Returns the list of applied migrations.

        Raises:
            ValueError: If no migration path exists.
        """
        path = self.get_migration_path(from_version, to_version)
        if not path:
            raise ValueError(
                f"No migration path from {from_version.to_string()} "
                f"to {to_version.to_string()}"
            )
        for migration in path:
            migration.up()
            self._applied.append(migration)
        return path

    def get_applied_migrations(self) -> list[Migration]:
        """Return migrations that have been applied, in application order."""
        return list(self._applied)

    def rollback_migration(self, migration: Migration) -> None:
        """Roll back a previously applied migration.

        Raises:
            ValueError: If ``migration`` has not been applied.
        """
        if migration not in self._applied:
            raise ValueError(
                f"Migration {migration.name!r} has not been applied; cannot roll back"
            )
        migration.down()
        self._applied.remove(migration)
