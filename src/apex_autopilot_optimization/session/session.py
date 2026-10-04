"""Session dataclass and status enum."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class SessionStatus(Enum):
    """Session lifecycle status."""

    ACTIVE = auto()
    EXPIRED = auto()
    INVALIDATED = auto()


@dataclass(slots=True)
class Session:
    """Represents a user session.

    Attributes:
        id: Unique session identifier.
        user_id: Identifier of the owning user.
        created_at: Unix timestamp of session creation.
        expires_at: Unix timestamp when the session expires.
        metadata: Arbitrary session metadata.
        status: Current session status.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    status: SessionStatus = SessionStatus.ACTIVE

    def is_active(self) -> bool:
        """Return True if the session is active and not expired."""
        return self.status == SessionStatus.ACTIVE and not self.is_expired()

    def is_expired(self) -> bool:
        """Return True if the session has passed its expiry time."""
        return self.status == SessionStatus.EXPIRED or (
            self.status == SessionStatus.ACTIVE and time.time() >= self.expires_at
        )

    def refresh(self, ttl_seconds: float) -> None:
        """Extend the session expiry by ttl_seconds from now."""
        self.expires_at = time.time() + ttl_seconds
        if self.status == SessionStatus.EXPIRED:
            self.status = SessionStatus.ACTIVE

    def invalidate(self) -> None:
        """Mark the session as invalidated."""
        self.status = SessionStatus.INVALIDATED
