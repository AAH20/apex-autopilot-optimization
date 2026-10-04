"""Tests for session management."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.session import (
    InMemorySessionStore,
    Session,
    SessionConfig,
    SessionManager,
    SessionStatus,
    SessionStore,
)


class TestSessionCreation:
    """Tests for session creation."""

    def test_create_session_with_default_ttl(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1")
        assert session.user_id == "user-1"
        assert session.status == SessionStatus.ACTIVE
        assert session.is_active()
        assert not session.is_expired()

    def test_create_session_with_metadata(self) -> None:
        manager = SessionManager()
        metadata = {"ip": "192.168.1.1", "user_agent": "test"}
        session = manager.create_session("user-1", metadata=metadata)
        assert session.metadata == metadata

    def test_create_session_with_custom_ttl(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1", ttl=60.0)
        assert session.expires_at - session.created_at == pytest.approx(60.0)

    def test_create_session_generates_unique_ids(self) -> None:
        manager = SessionManager()
        s1 = manager.create_session("user-1")
        s2 = manager.create_session("user-1")
        assert s1.id != s2.id


class TestSessionRetrieval:
    """Tests for session retrieval."""

    def test_get_session_returns_created_session(self) -> None:
        manager = SessionManager()
        created = manager.create_session("user-1")
        retrieved = manager.get_session(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.user_id == "user-1"

    def test_get_session_returns_none_for_unknown_id(self) -> None:
        manager = SessionManager()
        assert manager.get_session("nonexistent") is None

    def test_get_session_returns_none_for_invalidated_session(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1")
        manager.invalidate_session(session.id)
        assert manager.get_session(session.id) is None


class TestSessionRefresh:
    """Tests for session refresh."""

    def test_refresh_session_extends_expiry(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1", ttl=10.0)
        old_expires = session.expires_at
        time.sleep(0.01)
        refreshed = manager.refresh_session(session.id)
        assert refreshed is not None
        assert refreshed.expires_at > old_expires

    def test_refresh_session_returns_none_for_unknown_id(self) -> None:
        manager = SessionManager()
        assert manager.refresh_session("nonexistent") is None

    def test_refresh_session_marks_active(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1", ttl=10.0)
        refreshed = manager.refresh_session(session.id)
        assert refreshed is not None
        assert refreshed.status == SessionStatus.ACTIVE
        assert refreshed.is_active()


class TestSessionInvalidation:
    """Tests for session invalidation."""

    def test_invalidate_session_marks_inactive(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1")
        result = manager.invalidate_session(session.id)
        assert result is True
        assert session.status == SessionStatus.INVALIDATED
        assert not session.is_active()

    def test_invalidate_session_returns_false_for_unknown_id(self) -> None:
        manager = SessionManager()
        assert manager.invalidate_session("nonexistent") is False

    def test_invalidate_session_removes_from_store(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1")
        manager.invalidate_session(session.id)
        assert manager.get_session(session.id) is None


class TestSessionExpiration:
    """Tests for session expiration."""

    def test_session_expires_after_ttl(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1", ttl=0.05)
        assert not session.is_expired()
        time.sleep(0.06)
        assert session.is_expired()

    def test_expired_session_is_not_active(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1", ttl=0.05)
        time.sleep(0.06)
        assert not session.is_active()

    def test_get_session_returns_none_for_expired_session(self) -> None:
        manager = SessionManager()
        session = manager.create_session("user-1", ttl=0.05)
        time.sleep(0.06)
        assert manager.get_session(session.id) is None


class TestSessionListing:
    """Tests for session listing by user."""

    def test_list_sessions_returns_only_user_sessions(self) -> None:
        manager = SessionManager()
        s1 = manager.create_session("user-1")
        s2 = manager.create_session("user-1")
        manager.create_session("user-2")
        sessions = manager.list_sessions("user-1")
        assert len(sessions) == 2
        assert all(s.user_id == "user-1" for s in sessions)
        assert s1 in sessions
        assert s2 in sessions

    def test_list_sessions_returns_empty_for_unknown_user(self) -> None:
        manager = SessionManager()
        manager.create_session("user-1")
        assert manager.list_sessions("user-2") == []

    def test_list_sessions_excludes_invalidated(self) -> None:
        manager = SessionManager()
        s1 = manager.create_session("user-1")
        manager.create_session("user-1")
        manager.invalidate_session(s1.id)
        sessions = manager.list_sessions("user-1")
        assert len(sessions) == 1


class TestSessionCleanup:
    """Tests for expired session cleanup."""

    def test_cleanup_expired_removes_expired_sessions(self) -> None:
        manager = SessionManager()
        manager.create_session("user-1", ttl=0.05)
        manager.create_session("user-1", ttl=3600.0)
        time.sleep(0.06)
        removed = manager.cleanup_expired()
        assert removed == 1
        assert manager.get_session_count() == 1

    def test_cleanup_expired_returns_zero_when_none_expired(self) -> None:
        manager = SessionManager()
        manager.create_session("user-1", ttl=3600.0)
        assert manager.cleanup_expired() == 0


class TestSessionCount:
    """Tests for session count."""

    def test_get_session_count_tracks_sessions(self) -> None:
        manager = SessionManager()
        assert manager.get_session_count() == 0
        manager.create_session("user-1")
        assert manager.get_session_count() == 1
        manager.create_session("user-2")
        assert manager.get_session_count() == 2

    def test_get_session_count_excludes_invalidated(self) -> None:
        manager = SessionManager()
        s1 = manager.create_session("user-1")
        manager.create_session("user-1")
        manager.invalidate_session(s1.id)
        assert manager.get_session_count() == 1


class TestSessionConfig:
    """Tests for session configuration."""

    def test_default_config_values(self) -> None:
        config = SessionConfig()
        assert config.default_ttl_seconds > 0
        assert config.max_sessions_per_user > 0
        assert config.cleanup_interval_seconds > 0
        assert isinstance(config.persistent, bool)

    def test_custom_config_values(self) -> None:
        config = SessionConfig(
            default_ttl_seconds=600,
            max_sessions_per_user=3,
            cleanup_interval_seconds=60,
            persistent=True,
        )
        assert config.default_ttl_seconds == 600
        assert config.max_sessions_per_user == 3
        assert config.cleanup_interval_seconds == 60
        assert config.persistent is True

    def test_manager_uses_config_ttl(self) -> None:
        config = SessionConfig(default_ttl_seconds=120)
        manager = SessionManager(config=config)
        session = manager.create_session("user-1")
        assert session.expires_at - session.created_at == pytest.approx(120.0)


class TestSessionStore:
    """Tests for session store CRUD operations."""

    def test_store_save_and_get(self) -> None:
        store = InMemorySessionStore()
        session = Session(
            id="s1",
            user_id="user-1",
            created_at=time.time(),
            expires_at=time.time() + 3600,
            metadata={},
            status=SessionStatus.ACTIVE,
        )
        store.save(session)
        retrieved = store.get("s1")
        assert retrieved is not None
        assert retrieved.id == "s1"

    def test_store_get_returns_none_for_unknown_id(self) -> None:
        store = InMemorySessionStore()
        assert store.get("nonexistent") is None

    def test_store_delete(self) -> None:
        store = InMemorySessionStore()
        session = Session(
            id="s1",
            user_id="user-1",
            created_at=time.time(),
            expires_at=time.time() + 3600,
            metadata={},
            status=SessionStatus.ACTIVE,
        )
        store.save(session)
        store.delete("s1")
        assert store.get("s1") is None

    def test_store_list_all(self) -> None:
        store = InMemorySessionStore()
        s1 = Session(
            id="s1",
            user_id="user-1",
            created_at=time.time(),
            expires_at=time.time() + 3600,
            metadata={},
            status=SessionStatus.ACTIVE,
        )
        s2 = Session(
            id="s2",
            user_id="user-2",
            created_at=time.time(),
            expires_at=time.time() + 3600,
            metadata={},
            status=SessionStatus.ACTIVE,
        )
        store.save(s1)
        store.save(s2)
        all_sessions = store.list_all()
        assert len(all_sessions) == 2
        assert s1 in all_sessions
        assert s2 in all_sessions

    def test_store_clear(self) -> None:
        store = InMemorySessionStore()
        session = Session(
            id="s1",
            user_id="user-1",
            created_at=time.time(),
            expires_at=time.time() + 3600,
            metadata={},
            status=SessionStatus.ACTIVE,
        )
        store.save(session)
        store.clear()
        assert store.list_all() == []

    def test_store_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            SessionStore()  # type: ignore[abstract]


class TestMaxSessionsPerUser:
    """Tests for max sessions per user enforcement."""

    def test_enforce_max_sessions_per_user(self) -> None:
        config = SessionConfig(max_sessions_per_user=2)
        manager = SessionManager(config=config)
        manager.create_session("user-1")
        manager.create_session("user-1")
        with pytest.raises(RuntimeError, match="Maximum sessions"):
            manager.create_session("user-1")

    def test_max_sessions_does_not_affect_other_users(self) -> None:
        config = SessionConfig(max_sessions_per_user=1)
        manager = SessionManager(config=config)
        manager.create_session("user-1")
        session = manager.create_session("user-2")
        assert session.user_id == "user-2"

    def test_max_sessions_allows_reuse_after_invalidation(self) -> None:
        config = SessionConfig(max_sessions_per_user=1)
        manager = SessionManager(config=config)
        s1 = manager.create_session("user-1")
        manager.invalidate_session(s1.id)
        s2 = manager.create_session("user-1")
        assert s2.user_id == "user-1"
        assert s2.id != s1.id
