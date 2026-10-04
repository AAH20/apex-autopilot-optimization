"""Session manager for creating, retrieving, and managing sessions."""

from __future__ import annotations

import time
from typing import Any

from apex_autopilot_optimization.session.config import SessionConfig
from apex_autopilot_optimization.session.session import Session, SessionStatus
from apex_autopilot_optimization.session.store import InMemorySessionStore, SessionStore


class SessionManager:
    """Manages user sessions with configurable TTL and per-user limits."""

    def __init__(
        self,
        config: SessionConfig | None = None,
        store: SessionStore | None = None,
    ) -> None:
        self._config = config or SessionConfig()
        self._store = store or InMemorySessionStore()

    def create_session(
        self,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        ttl: float | None = None,
    ) -> Session:
        """Create a new session for the given user.

        Args:
            user_id: The user identifier.
            metadata: Optional session metadata.
            ttl: Optional custom TTL in seconds (overrides config default).

        Returns:
            The newly created Session.

        Raises:
            RuntimeError: If the user already has the maximum allowed sessions.
        """
        active = [s for s in self.list_sessions(user_id) if s.is_active()]
        if len(active) >= self._config.max_sessions_per_user:
            raise RuntimeError(
                f"Maximum sessions ({self._config.max_sessions_per_user}) "
                f"reached for user {user_id}"
            )

        now = time.time()
        session = Session(
            user_id=user_id,
            created_at=now,
            expires_at=now + (ttl if ttl is not None else self._config.default_ttl_seconds),
            metadata=metadata or {},
            status=SessionStatus.ACTIVE,
        )
        self._store.save(session)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID.

        Returns None if the session does not exist, is expired, or is invalidated.
        """
        session = self._store.get(session_id)
        if session is None:
            return None
        if session.status == SessionStatus.INVALIDATED:
            return None
        if session.is_expired():
            session.status = SessionStatus.EXPIRED
            self._store.delete(session_id)
            return None
        return session

    def refresh_session(self, session_id: str, ttl: float | None = None) -> Session | None:
        """Refresh a session, extending its expiry time.

        Returns None if the session does not exist or is invalidated.
        """
        session = self._store.get(session_id)
        if session is None or session.status == SessionStatus.INVALIDATED:
            return None
        session.refresh(ttl if ttl is not None else self._config.default_ttl_seconds)
        self._store.save(session)
        return session

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session by ID.

        Returns True if the session was found and invalidated, False otherwise.
        """
        session = self._store.get(session_id)
        if session is None:
            return False
        session.invalidate()
        self._store.delete(session_id)
        return True

    def list_sessions(self, user_id: str) -> list[Session]:
        """Return all active sessions for the given user."""
        return [
            s
            for s in self._store.list_all()
            if s.user_id == user_id and s.status != SessionStatus.INVALIDATED
        ]

    def cleanup_expired(self) -> int:
        """Remove all expired sessions from the store.

        Returns the number of sessions removed.
        """
        expired = [s for s in self._store.list_all() if s.is_expired()]
        for session in expired:
            self._store.delete(session.id)
        return len(expired)

    def get_session_count(self) -> int:
        """Return the total number of sessions in the store."""
        return len(self._store.list_all())
