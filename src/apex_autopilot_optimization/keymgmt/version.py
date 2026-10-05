"""Key version and status definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KeyStatus(Enum):
    """Status of a key version."""

    ACTIVE = "active"
    RETIRED = "retired"
    EXPIRED = "expired"


@dataclass
class KeyVersion:
    """Represents a version of a cryptographic key."""

    key_id: str
    created_at: float
    expires_at: float | None
    status: KeyStatus
    key_data: bytes
