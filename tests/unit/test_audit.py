"""Unit tests for audit logging module."""

import json
import time

import pytest

from apex_autopilot_optimization.audit import (
    AuditConfig,
    AuditEvent,
    AuditLevel,
    AuditLogger,
    AuditTrail,
)

# ---------------------------------------------------------------------------
# AuditLevel tests
# ---------------------------------------------------------------------------


class TestAuditLevel:
    """Audit level enumeration."""

    def test_audit_level_values(self):
        assert AuditLevel.DEBUG.value == "DEBUG"
        assert AuditLevel.INFO.value == "INFO"
        assert AuditLevel.WARNING.value == "WARNING"
        assert AuditLevel.ERROR.value == "ERROR"
        assert AuditLevel.CRITICAL.value == "CRITICAL"

    def test_audit_level_ordering(self):
        assert AuditLevel.DEBUG < AuditLevel.INFO
        assert AuditLevel.INFO < AuditLevel.WARNING
        assert AuditLevel.WARNING < AuditLevel.ERROR
        assert AuditLevel.ERROR < AuditLevel.CRITICAL

    def test_audit_level_from_value(self):
        assert AuditLevel("DEBUG") == AuditLevel.DEBUG
        assert AuditLevel("INFO") == AuditLevel.INFO
        assert AuditLevel("WARNING") == AuditLevel.WARNING
        assert AuditLevel("ERROR") == AuditLevel.ERROR
        assert AuditLevel("CRITICAL") == AuditLevel.CRITICAL


# ---------------------------------------------------------------------------
# AuditEvent tests
# ---------------------------------------------------------------------------


class TestAuditEvent:
    """Audit event creation."""

    def test_audit_event_creation(self):
        event = AuditEvent(
            id="evt-001",
            timestamp=1234567890.0,
            level=AuditLevel.INFO,
            actor="user1",
            action="login",
            resource="auth_system",
            outcome="success",
            details={"ip": "10.0.0.1"},
            trace_id="trace-abc",
        )
        assert event.id == "evt-001"
        assert event.timestamp == 1234567890.0
        assert event.level == AuditLevel.INFO
        assert event.actor == "user1"
        assert event.action == "login"
        assert event.resource == "auth_system"
        assert event.outcome == "success"
        assert event.details == {"ip": "10.0.0.1"}
        assert event.trace_id == "trace-abc"

    def test_audit_event_default_details(self):
        event = AuditEvent(
            id="evt-002",
            timestamp=1234567890.0,
            level=AuditLevel.WARNING,
            actor="user2",
            action="access_denied",
            resource="file_system",
            outcome="failure",
            details={},
            trace_id="trace-def",
        )
        assert event.details == {}


# ---------------------------------------------------------------------------
# AuditLogger tests
# ---------------------------------------------------------------------------


class TestAuditLoggerLog:
    """Audit logger log and get events."""

    def test_log_stores_event(self):
        logger = AuditLogger()
        event = AuditEvent(
            id="evt-001",
            timestamp=time.time(),
            level=AuditLevel.INFO,
            actor="user1",
            action="login",
            resource="auth",
            outcome="success",
            details={},
            trace_id="t1",
        )
        logger.log(event)
        assert logger.get_event_count() == 1

    def test_log_multiple_events(self):
        logger = AuditLogger()
        for i in range(5):
            logger.log(
                AuditEvent(
                    id=f"evt-{i}",
                    timestamp=time.time(),
                    level=AuditLevel.INFO,
                    actor="user1",
                    action="action",
                    resource="res",
                    outcome="success",
                    details={},
                    trace_id=f"t-{i}",
                )
            )
        assert logger.get_event_count() == 5

    def test_get_events_returns_all(self):
        logger = AuditLogger()
        logger.log(
            AuditEvent(
                id="e1",
                timestamp=time.time(),
                level=AuditLevel.INFO,
                actor="a1",
                action="act1",
                resource="r1",
                outcome="ok",
                details={},
                trace_id="t1",
            )
        )
        logger.log(
            AuditEvent(
                id="e2",
                timestamp=time.time(),
                level=AuditLevel.ERROR,
                actor="a2",
                action="act2",
                resource="r2",
                outcome="fail",
                details={},
                trace_id="t2",
            )
        )
        events = logger.get_events()
        assert len(events) == 2
        ids = {e.id for e in events}
        assert ids == {"e1", "e2"}


class TestAuditLoggerFiltering:
    """Audit logger filtering by actor, resource, level, time."""

    def _make_logger(self):
        logger = AuditLogger()
        logger.log(
            AuditEvent(
                id="e1",
                timestamp=1000.0,
                level=AuditLevel.INFO,
                actor="alice",
                action="read",
                resource="file_a",
                outcome="success",
                details={},
                trace_id="t1",
            )
        )
        logger.log(
            AuditEvent(
                id="e2",
                timestamp=2000.0,
                level=AuditLevel.ERROR,
                actor="bob",
                action="write",
                resource="file_b",
                outcome="failure",
                details={},
                trace_id="t2",
            )
        )
        logger.log(
            AuditEvent(
                id="e3",
                timestamp=3000.0,
                level=AuditLevel.WARNING,
                actor="alice",
                action="delete",
                resource="file_a",
                outcome="denied",
                details={},
                trace_id="t3",
            )
        )
        return logger

    def test_get_events_by_actor(self):
        logger = self._make_logger()
        events = logger.get_events_by_actor("alice")
        assert len(events) == 2
        assert all(e.actor == "alice" for e in events)

    def test_get_events_by_actor_no_match(self):
        logger = self._make_logger()
        assert logger.get_events_by_actor("charlie") == []

    def test_get_events_by_resource(self):
        logger = self._make_logger()
        events = logger.get_events_by_resource("file_a")
        assert len(events) == 2
        assert all(e.resource == "file_a" for e in events)

    def test_get_events_by_resource_no_match(self):
        logger = self._make_logger()
        assert logger.get_events_by_resource("file_z") == []

    def test_get_events_by_level(self):
        logger = self._make_logger()
        events = logger.get_events_by_level(AuditLevel.ERROR)
        assert len(events) == 1
        assert events[0].level == AuditLevel.ERROR

    def test_get_events_by_level_no_match(self):
        logger = self._make_logger()
        assert logger.get_events_by_level(AuditLevel.CRITICAL) == []

    def test_get_events_by_time_range(self):
        logger = self._make_logger()
        events = logger.get_events_by_time_range(1500.0, 2500.0)
        assert len(events) == 1
        assert events[0].id == "e2"

    def test_get_events_by_time_range_inclusive(self):
        logger = self._make_logger()
        events = logger.get_events_by_time_range(1000.0, 3000.0)
        assert len(events) == 3

    def test_get_events_by_time_range_empty(self):
        logger = self._make_logger()
        assert logger.get_events_by_time_range(5000.0, 6000.0) == []


class TestAuditLoggerExport:
    """Audit logger export, count, clear."""

    def test_export_events_json(self):
        logger = AuditLogger()
        logger.log(
            AuditEvent(
                id="e1",
                timestamp=1000.0,
                level=AuditLevel.INFO,
                actor="alice",
                action="read",
                resource="file_a",
                outcome="success",
                details={"key": "val"},
                trace_id="t1",
            )
        )
        exported = logger.export_events("json")
        data = json.loads(exported)
        assert len(data) == 1
        assert data[0]["id"] == "e1"
        assert data[0]["actor"] == "alice"

    def test_export_events_csv(self):
        logger = AuditLogger()
        logger.log(
            AuditEvent(
                id="e1",
                timestamp=1000.0,
                level=AuditLevel.INFO,
                actor="alice",
                action="read",
                resource="file_a",
                outcome="success",
                details={},
                trace_id="t1",
            )
        )
        exported = logger.export_events("csv")
        lines = exported.strip().split("\n")
        assert len(lines) == 2  # header + 1 event
        assert "id" in lines[0]
        assert "e1" in lines[1]

    def test_export_events_invalid_format(self):
        logger = AuditLogger()
        with pytest.raises(ValueError):
            logger.export_events("xml")

    def test_get_event_count(self):
        logger = AuditLogger()
        assert logger.get_event_count() == 0
        logger.log(
            AuditEvent(
                id="e1",
                timestamp=time.time(),
                level=AuditLevel.INFO,
                actor="a",
                action="act",
                resource="r",
                outcome="ok",
                details={},
                trace_id="t",
            )
        )
        assert logger.get_event_count() == 1

    def test_clear_events(self):
        logger = AuditLogger()
        logger.log(
            AuditEvent(
                id="e1",
                timestamp=time.time(),
                level=AuditLevel.INFO,
                actor="a",
                action="act",
                resource="r",
                outcome="ok",
                details={},
                trace_id="t",
            )
        )
        logger.clear_events()
        assert logger.get_event_count() == 0
        assert logger.get_events() == []


# ---------------------------------------------------------------------------
# AuditTrail tests
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """Audit trail append, get trail, size, integrity, chain hash."""

    def _make_event(self, eid, resource="res1", actor="user1"):
        return AuditEvent(
            id=eid,
            timestamp=time.time(),
            level=AuditLevel.INFO,
            actor=actor,
            action="act",
            resource=resource,
            outcome="success",
            details={},
            trace_id=f"trace-{eid}",
        )

    def test_append_increments_size(self):
        trail = AuditTrail()
        trail.append(self._make_event("e1"))
        assert trail.get_trail_size() == 1
        trail.append(self._make_event("e2"))
        assert trail.get_trail_size() == 2

    def test_get_trail_by_resource(self):
        trail = AuditTrail()
        trail.append(self._make_event("e1", resource="file_a"))
        trail.append(self._make_event("e2", resource="file_b"))
        trail.append(self._make_event("e3", resource="file_a"))
        events = trail.get_trail("file_a")
        assert len(events) == 2
        assert all(e.resource == "file_a" for e in events)

    def test_get_trail_by_actor(self):
        trail = AuditTrail()
        trail.append(self._make_event("e1", actor="alice"))
        trail.append(self._make_event("e2", actor="bob"))
        trail.append(self._make_event("e3", actor="alice"))
        events = trail.get_trail_by_actor("alice")
        assert len(events) == 2
        assert all(e.actor == "alice" for e in events)

    def test_get_trail_size_empty(self):
        trail = AuditTrail()
        assert trail.get_trail_size() == 0

    def test_verify_integrity_passes_on_clean_trail(self):
        trail = AuditTrail()
        trail.append(self._make_event("e1"))
        trail.append(self._make_event("e2"))
        assert trail.verify_integrity() is True

    def test_get_chain_hash_stable(self):
        trail = AuditTrail()
        trail.append(self._make_event("e1"))
        trail.append(self._make_event("e2"))
        h1 = trail.get_chain_hash()
        h2 = trail.get_chain_hash()
        assert h1 == h2

    def test_get_chain_hash_changes_with_new_event(self):
        trail = AuditTrail()
        trail.append(self._make_event("e1"))
        h1 = trail.get_chain_hash()
        trail.append(self._make_event("e2"))
        h2 = trail.get_chain_hash()
        assert h1 != h2

    def test_verify_integrity_detects_tampering(self):
        trail = AuditTrail()
        trail.append(self._make_event("e1"))
        trail.append(self._make_event("e2"))
        # Tamper with internal state
        trail._events[0]._details = {"tampered": True}
        assert trail.verify_integrity() is False


# ---------------------------------------------------------------------------
# AuditConfig tests
# ---------------------------------------------------------------------------


class TestAuditConfig:
    """Audit config dataclass."""

    def test_audit_config_creation(self):
        config = AuditConfig(
            enabled=True,
            persistent=False,
            storage_path="/tmp/audit.log",
            max_events=10000,
            retention_days=90,
            tamper_evident=True,
        )
        assert config.enabled is True
        assert config.persistent is False
        assert config.storage_path == "/tmp/audit.log"
        assert config.max_events == 10000
        assert config.retention_days == 90
        assert config.tamper_evident is True

    def test_audit_config_defaults(self):
        config = AuditConfig()
        assert isinstance(config.enabled, bool)
        assert isinstance(config.persistent, bool)
        assert isinstance(config.max_events, int)
        assert isinstance(config.retention_days, int)
        assert isinstance(config.tamper_evident, bool)
