"""Session store ABC and in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from apex_autopilot_optimization.session.session import Session


class SessionStore(ABC):
    """Abstract base class for session storage backends."""

    @abstractmethod
    def save(self, session: Session) -> None:
        """Save a session to the store."""
        ...

    @abstractmethod
    def get(self, session_id: str) -> Session | None:
        """Retrieve a session by ID, or None if not found."""
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete a session by ID."""
        ...

    @abstractmethod
    def list_all(self) -> list[Session]:
        """Return all sessions in the store."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all sessions from the store."""
        ...


class InMemorySessionStore(SessionStore):
    """In-memory session store implementation."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def save(self, session: Session) -> None:
        self._sessions[session.id] = session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_all(self) -> list[Session]:
        return list(self._sessions.values())

    def clear(self) -> None:
        self._sessions.clear()
