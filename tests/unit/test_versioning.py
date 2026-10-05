"""Tests for the versioning and migration package.

Covers semantic version parsing/formatting/comparison, schema version
tracking, migration execution/rollback, and deprecation policy evaluation.
"""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.versioning import (
    DeprecationPolicy,
    Migration,
    MigrationManager,
    SchemaVersion,
    Version,
    VersionManager,
)
from apex_autopilot_optimization.versioning.deprecation import (
    get_deprecation_warning,
    is_deprecated,
    is_removed,
)
from apex_autopilot_optimization.versioning.schema import (
    clear_schema_registry,
    get_current_schema,
    get_schema_history,
    is_schema_compatible,
    register_schema_version,
)


@pytest.fixture(autouse=True)
def _clean_schema_registry():
    """Ensure the global schema registry does not leak between tests."""
    clear_schema_registry()
    yield
    clear_schema_registry()


# ---------------------------------------------------------------------------
# Version creation from string
# ---------------------------------------------------------------------------


class TestVersionFromString:
    def test_from_string_basic(self):
        assert Version.from_string("1.2.3") == Version(1, 2, 3)

    def test_from_string_zero(self):
        assert Version.from_string("0.1.0") == Version(0, 1, 0)

    def test_from_string_leading_v(self):
        assert Version.from_string("v2.5.9") == Version(2, 5, 9)

    def test_from_string_prerelease(self):
        version = Version.from_string("1.2.3-alpha.1")
        assert version.prerelease == "alpha.1"
        assert version == Version(1, 2, 3, "alpha.1")

    def test_from_string_build_metadata_ignored(self):
        assert Version.from_string("1.2.3+build.5") == Version(1, 2, 3)

    def test_from_string_prerelease_and_build(self):
        assert Version.from_string("1.2.3-rc.1+build.7") == Version(1, 2, 3, "rc.1")

    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError):
            Version.from_string("not-a-version")

    def test_from_string_too_few_parts_raises(self):
        with pytest.raises(ValueError):
            Version.from_string("1.2")


# ---------------------------------------------------------------------------
# Version to string
# ---------------------------------------------------------------------------


class TestVersionToString:
    def test_to_string_basic(self):
        assert Version(1, 2, 3).to_string() == "1.2.3"

    def test_to_string_prerelease(self):
        assert Version(1, 2, 3, "beta.2").to_string() == "1.2.3-beta.2"

    def test_to_string_roundtrip(self):
        assert Version.from_string(Version(3, 4, 5, "rc.1").to_string()) == Version(3, 4, 5, "rc.1")


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


class TestVersionComparison:
    def test_compare_equal(self):
        assert Version(1, 2, 3).compare(Version(1, 2, 3)) == 0

    def test_compare_major(self):
        assert Version(2, 0, 0).compare(Version(1, 9, 9)) == 1
        assert Version(1, 9, 9).compare(Version(2, 0, 0)) == -1

    def test_compare_minor(self):
        assert Version(1, 3, 0).compare(Version(1, 2, 9)) == 1

    def test_compare_patch(self):
        assert Version(1, 2, 4).compare(Version(1, 2, 3)) == 1

    def test_prerelease_is_lower_than_release(self):
        assert Version(1, 2, 3, "alpha").compare(Version(1, 2, 3)) == -1
        assert Version(1, 2, 3).compare(Version(1, 2, 3, "alpha")) == 1

    def test_prerelease_ordering_lexical(self):
        assert Version(1, 0, 0, "alpha").compare(Version(1, 0, 0, "beta")) == -1

    def test_prerelease_ordering_numeric(self):
        assert Version(1, 0, 0, "alpha.1").compare(Version(1, 0, 0, "alpha.2")) == -1

    def test_prerelease_fewer_fields_is_lower(self):
        assert Version(1, 0, 0, "alpha").compare(Version(1, 0, 0, "alpha.1")) == -1

    def test_compare_with_non_version_raises(self):
        with pytest.raises(TypeError):
            Version(1, 0, 0).compare("1.0.0")


# ---------------------------------------------------------------------------
# Version compatibility
# ---------------------------------------------------------------------------


class TestVersionCompatibility:
    def test_same_major_compatible(self):
        assert Version(1, 2, 3).is_compatible(Version(1, 9, 0)) is True

    def test_different_major_incompatible(self):
        assert Version(1, 2, 3).is_compatible(Version(2, 0, 0)) is False

    def test_zero_major_same_minor_compatible(self):
        assert Version(0, 3, 1).is_compatible(Version(0, 3, 9)) is True

    def test_zero_major_different_minor_incompatible(self):
        assert Version(0, 3, 1).is_compatible(Version(0, 4, 0)) is False


# ---------------------------------------------------------------------------
# Version prerelease
# ---------------------------------------------------------------------------


class TestVersionPrerelease:
    def test_is_prerelease_true(self):
        assert Version(1, 0, 0, "rc.1").is_prerelease() is True

    def test_is_prerelease_false_when_none(self):
        assert Version(1, 0, 0).is_prerelease() is False

    def test_is_prerelease_false_when_empty(self):
        assert Version(1, 0, 0, "").is_prerelease() is False


# ---------------------------------------------------------------------------
# Version bumps
# ---------------------------------------------------------------------------


class TestVersionBumps:
    def test_bump_major(self):
        assert Version(1, 2, 3).bump_major() == Version(2, 0, 0)

    def test_bump_minor(self):
        assert Version(1, 2, 3).bump_minor() == Version(1, 3, 0)

    def test_bump_patch(self):
        assert Version(1, 2, 3).bump_patch() == Version(1, 2, 4)

    def test_bump_clears_prerelease(self):
        assert Version(1, 2, 3, "rc.1").bump_minor() == Version(1, 3, 0)

    def test_bump_does_not_mutate(self):
        original = Version(1, 2, 3)
        original.bump_major()
        assert original == Version(1, 2, 3)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_schema_version_creation(self):
        sv = SchemaVersion(schema="config", version=Version(1, 0, 0), created_at=123.0)
        assert sv.schema == "config"
        assert sv.version == Version(1, 0, 0)
        assert sv.created_at == 123.0

    def test_schema_version_default_created_at(self):
        sv = SchemaVersion(schema="config", version=Version(1, 0, 0))
        assert isinstance(sv.created_at, float)
        assert sv.created_at > 0

    def test_get_current_schema_returns_latest(self):
        register_schema_version(SchemaVersion("config", Version(1, 0, 0)))
        register_schema_version(SchemaVersion("config", Version(1, 2, 0)))
        assert get_current_schema("config") == Version(1, 2, 0)

    def test_get_current_schema_unknown_returns_none(self):
        assert get_current_schema("does-not-exist") is None

    def test_get_schema_history_sorted(self):
        register_schema_version(SchemaVersion("config", Version(1, 2, 0)))
        register_schema_version(SchemaVersion("config", Version(1, 0, 0)))
        register_schema_version(SchemaVersion("config", Version(1, 1, 0)))
        history = get_schema_history("config")
        assert [sv.version for sv in history] == [
            Version(1, 0, 0),
            Version(1, 1, 0),
            Version(1, 2, 0),
        ]

    def test_get_schema_history_unknown_is_empty(self):
        assert get_schema_history("nope") == []

    def test_is_schema_compatible_true(self):
        register_schema_version(SchemaVersion("config", Version(1, 3, 0)))
        assert is_schema_compatible("config", Version(1, 0, 0)) is True

    def test_is_schema_compatible_false_different_major(self):
        register_schema_version(SchemaVersion("config", Version(1, 3, 0)))
        assert is_schema_compatible("config", Version(2, 0, 0)) is False

    def test_is_schema_compatible_unknown_schema_false(self):
        assert is_schema_compatible("missing", Version(1, 0, 0)) is False


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigrationManager:
    @staticmethod
    def _make_chain():
        events: list[str] = []

        def make(step: str):
            def fn() -> None:
                events.append(step)

            return fn

        m1 = Migration(
            from_version=Version(1, 0, 0),
            to_version=Version(1, 1, 0),
            name="add-field",
            up=make("up-1.0->1.1"),
            down=make("down-1.0->1.1"),
        )
        m2 = Migration(
            from_version=Version(1, 1, 0),
            to_version=Version(1, 2, 0),
            name="rename-field",
            up=make("up-1.1->1.2"),
            down=make("down-1.1->1.2"),
        )
        return m1, m2, events

    def test_migration_registration(self):
        manager = MigrationManager()
        m1, _, _ = self._make_chain()
        manager.register_migration(m1)
        assert manager.get_migration_path(Version(1, 0, 0), Version(1, 1, 0)) == [m1]

    def test_duplicate_registration_raises(self):
        manager = MigrationManager()
        m1, _, _ = self._make_chain()
        manager.register_migration(m1)
        with pytest.raises(ValueError):
            manager.register_migration(m1)

    def test_migration_path_chained(self):
        manager = MigrationManager()
        m1, m2, _ = self._make_chain()
        manager.register_migration(m1)
        manager.register_migration(m2)
        assert manager.get_migration_path(Version(1, 0, 0), Version(1, 2, 0)) == [m1, m2]

    def test_migration_path_same_version_is_empty(self):
        manager = MigrationManager()
        assert manager.get_migration_path(Version(1, 0, 0), Version(1, 0, 0)) == []

    def test_migration_path_missing_returns_empty(self):
        manager = MigrationManager()
        m1, _, _ = self._make_chain()
        manager.register_migration(m1)
        assert manager.get_migration_path(Version(1, 0, 0), Version(9, 9, 9)) == []

    def test_migration_execution(self):
        manager = MigrationManager()
        m1, m2, events = self._make_chain()
        manager.register_migration(m1)
        manager.register_migration(m2)
        applied = manager.migrate(Version(1, 0, 0), Version(1, 2, 0))
        assert events == ["up-1.0->1.1", "up-1.1->1.2"]
        assert applied == [m1, m2]

    def test_migration_execution_no_path_raises(self):
        manager = MigrationManager()
        with pytest.raises(ValueError):
            manager.migrate(Version(1, 0, 0), Version(2, 0, 0))

    def test_get_applied_migrations(self):
        manager = MigrationManager()
        m1, m2, _ = self._make_chain()
        manager.register_migration(m1)
        manager.register_migration(m2)
        assert manager.get_applied_migrations() == []
        manager.migrate(Version(1, 0, 0), Version(1, 1, 0))
        assert manager.get_applied_migrations() == [m1]

    def test_migration_rollback(self):
        manager = MigrationManager()
        m1, _, events = self._make_chain()
        manager.register_migration(m1)
        manager.migrate(Version(1, 0, 0), Version(1, 1, 0))
        manager.rollback_migration(m1)
        assert events == ["up-1.0->1.1", "down-1.0->1.1"]
        assert manager.get_applied_migrations() == []

    def test_rollback_unapplied_raises(self):
        manager = MigrationManager()
        m1, _, _ = self._make_chain()
        manager.register_migration(m1)
        with pytest.raises(ValueError):
            manager.rollback_migration(m1)


# ---------------------------------------------------------------------------
# VersionManager facade
# ---------------------------------------------------------------------------


class TestVersionManager:
    def test_version_manager_delegates_migrations(self):
        events: list[str] = []
        manager = VersionManager()
        migration = Migration(
            from_version=Version(1, 0, 0),
            to_version=Version(2, 0, 0),
            name="big-bump",
            up=lambda: events.append("up"),
            down=lambda: events.append("down"),
        )
        manager.register_migration(migration)
        manager.migrate(Version(1, 0, 0), Version(2, 0, 0))
        assert events == ["up"]

    def test_version_manager_tracks_current_version(self):
        manager = VersionManager(initial_version=Version(1, 0, 0))
        assert manager.current_version == Version(1, 0, 0)

    def test_version_manager_bumps(self):
        manager = VersionManager(initial_version=Version(1, 2, 3))
        manager.bump_minor()
        assert manager.current_version == Version(1, 3, 0)


# ---------------------------------------------------------------------------
# Deprecation policy
# ---------------------------------------------------------------------------


class TestDeprecationPolicy:
    def test_policy_creation(self):
        policy = DeprecationPolicy(
            deprecated_in=Version(1, 2, 0),
            removal_version=Version(2, 0, 0),
            message="use new_api instead",
        )
        assert policy.deprecated_in == Version(1, 2, 0)
        assert policy.removal_version == Version(2, 0, 0)
        assert policy.message == "use new_api instead"

    def test_is_deprecated_within_window(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "msg")
        assert is_deprecated(Version(1, 5, 0), policy) is True

    def test_is_deprecated_at_deprecation_point(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "msg")
        assert is_deprecated(Version(1, 2, 0), policy) is True

    def test_is_deprecated_before_window(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "msg")
        assert is_deprecated(Version(1, 1, 0), policy) is False

    def test_is_deprecated_after_removal(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "msg")
        assert is_deprecated(Version(2, 0, 0), policy) is False

    def test_is_removed_at_removal_version(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "msg")
        assert is_removed(Version(2, 0, 0), policy) is True

    def test_is_removed_after_removal_version(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "msg")
        assert is_removed(Version(2, 1, 0), policy) is True

    def test_is_removed_before_removal_version(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "msg")
        assert is_removed(Version(1, 9, 0), policy) is False

    def test_get_deprecation_warning_when_deprecated(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "use new_api")
        warning = get_deprecation_warning(Version(1, 5, 0), policy)
        assert warning is not None
        assert "use new_api" in warning

    def test_get_deprecation_warning_when_not_deprecated(self):
        policy = DeprecationPolicy(Version(1, 2, 0), Version(2, 0, 0), "use new_api")
        assert get_deprecation_warning(Version(1, 0, 0), policy) is None
