"""Schema version tracking.

Maintains an in-process registry of :class:`SchemaVersion` records so callers
can discover the current version of a named schema, walk its history, and test
whether a candidate version is compatible with what is currently registered.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from apex_autopilot_optimization.versioning.version import Version


@dataclass(frozen=True)
class SchemaVersion:
    """A single version of a named schema.

    Attributes:
        schema: Logical schema name (e.g. ``"config"``).
        version: Version of the schema at ``created_at``.
        created_at: POSIX timestamp when this schema version was introduced.
    """

    schema: str
    version: Version
    created_at: float = field(default_factory=time.time)


# schema name -> ordered (by version) list of SchemaVersion records.
_REGISTRY: dict[str, list[SchemaVersion]] = {}


def register_schema_version(schema_version: SchemaVersion) -> None:
    """Record a schema version, replacing any duplicate of the same version."""
    history = _REGISTRY.setdefault(schema_version.schema, [])
    history[:] = [sv for sv in history if sv.version != schema_version.version]
    history.append(schema_version)
    history.sort(key=lambda sv: sv.version.to_string())


def get_current_schema(schema: str) -> Version | None:
    """Return the latest registered version for ``schema`` or ``None``."""
    history = _REGISTRY.get(schema)
    if not history:
        return None
    # History is kept sorted ascending by version.
    return history[-1].version


def get_schema_history(schema: str) -> list[SchemaVersion]:
    """Return every registered version of ``schema``, oldest first."""
    return list(_REGISTRY.get(schema, []))


def is_schema_compatible(schema: str, version: Version) -> bool:
    """Return whether ``version`` is compatible with the current schema version.

    An unknown schema is never compatible.
    """
    current = get_current_schema(schema)
    if current is None:
        return False
    return current.is_compatible(version)


def clear_schema_registry() -> None:
    """Remove all registered schema versions (primarily for tests)."""
    _REGISTRY.clear()
