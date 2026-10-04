"""Versioning and migration support for apex-autopilot-optimization.

Exposes semantic version primitives, schema version tracking, migration
registration/execution, and deprecation policy evaluation.
"""

from apex_autopilot_optimization.versioning.deprecation import (
    DeprecationPolicy,
    get_deprecation_warning,
    is_deprecated,
    is_removed,
)
from apex_autopilot_optimization.versioning.manager import VersionManager
from apex_autopilot_optimization.versioning.migration import (
    Migration,
    MigrationManager,
)
from apex_autopilot_optimization.versioning.schema import (
    SchemaVersion,
    get_current_schema,
    get_schema_history,
    is_schema_compatible,
    register_schema_version,
)
from apex_autopilot_optimization.versioning.version import Version

__all__ = [
    "DeprecationPolicy",
    "Migration",
    "MigrationManager",
    "SchemaVersion",
    "Version",
    "VersionManager",
    "get_current_schema",
    "get_deprecation_warning",
    "get_schema_history",
    "is_deprecated",
    "is_removed",
    "is_schema_compatible",
    "register_schema_version",
]
