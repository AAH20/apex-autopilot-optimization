"""Model versioning primitives for the MLOps layer.

Defines the :class:`ModelStage` lifecycle enum and the :class:`ModelVersion`
dataclass that records where a model artifact lives, which lifecycle stage it
occupies, and arbitrary metadata attached at registration time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelStage(str, Enum):
    """Lifecycle stage of a registered model version.

    Subclasses :class:`str` so that stages serialize directly to JSON and can be
    compared against their lowercase string values.
    """

    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


@dataclass
class ModelVersion:
    """A single registered version of a model artifact.

    Attributes:
        name: Logical model name (e.g. ``"planner"``).
        version: Version identifier (e.g. ``"1.0.0"``).
        path: Filesystem path to the serialized model artifact.
        stage: Current :class:`ModelStage`; defaults to ``STAGING``.
        metadata: Free-form metadata captured at registration time.
        created_at: POSIX timestamp of registration; defaults to now.
    """

    name: str
    version: str
    path: str
    stage: ModelStage = ModelStage.STAGING
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
