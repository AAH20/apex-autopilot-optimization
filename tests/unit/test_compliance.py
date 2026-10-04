"""Unit tests for compliance and governance module."""

import json
import time

import pytest

from apex_autopilot_optimization.compliance import (
    AuditTrail,
    ComplianceMonitor,
    ComplianceReport,
    ComplianceStandard,
    GovernancePolicy,
    generate_report,
    get_standard_requirements,
)


# ---------------------------------------------------------------------------
# AuditTrail tests
# ---------------------------------------------------------------------------


class TestAuditTrailLogging:
    """Audit trail event logging."""

    def test_log_event_stores_event(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1", "ip": "10.0.0.1"})
        assert trail.get_event_count() == 1

    def test_log_event_increments_count(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        trail.log_event("logout", {"user_id": "u1"})
        trail.log_event("data_access", {"user_id": "u2"})
        assert trail.get_event_count() == 3

    def test_log_event_stores_details(self):
        trail = AuditTrail()
        trail.log_event("config_change", {"field": "timeout", "old": 30, "new": 60})
        events = trail.get_events("config_change")
        assert len(events) == 1
        assert events[0]["details"]["field"] == "timeout"
        assert events[0]["details"]["old"] == 30
        assert events[0]["details"]["new"] == 60

    def test_log_event_records_timestamp(self):
        trail = AuditTrail()
        before = time.time()
        trail.log_event("login", {"user_id": "u1"})
        after = time.time()
        events = trail.get_events("login")
        assert before <= events[0]["timestamp"] <= after

    def test_log_event_records_event_type(self):
        trail = AuditTrail()
        trail.log_event("permission_grant", {"role": "admin"})
        events = trail.get_events("permission_grant")
        assert events[0]["event_type"] == "permission_grant"


class TestAuditTrailFiltering:
    """Audit trail filtering by type, time, and user."""

    def test_get_events_by_type(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        trail.log_event("login", {"user_id": "u2"})
        trail.log_event("logout", {"user_id": "u1"})
        login_events = trail.get_events("login")
        assert len(login_events) == 2
        assert all(e["event_type"] == "login" for e in login_events)

    def test_get_events_by_type_empty_when_no_match(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        assert trail.get_events("nonexistent") == []

    def test_get_events_by_time_range(self):
        trail = AuditTrail()
        t0 = time.time()
        trail.log_event("login", {"user_id": "u1"})
        time.sleep(0.01)
        t_mid = time.time()
        time.sleep(0.01)
        trail.log_event("logout", {"user_id": "u1"})
        t1 = time.time()

        events = trail.get_events_by_time(t0, t_mid)
        assert len(events) == 1
        assert events[0]["event_type"] == "login"

        events = trail.get_events_by_time(t_mid, t1)
        assert len(events) == 1
        assert events[0]["event_type"] == "logout"

    def test_get_events_by_time_inclusive_bounds(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        events = trail.get_events_by_time(0, time.time() + 10)
        assert len(events) == 1

    def test_get_events_by_user(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "alice"})
        trail.log_event("login", {"user_id": "bob"})
        trail.log_event("data_access", {"user_id": "alice"})
        alice_events = trail.get_events_by_user("alice")
        assert len(alice_events) == 2
        assert all(e["details"]["user_id"] == "alice" for e in alice_events)

    def test_get_events_by_user_empty_when_no_match(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "alice"})
        assert trail.get_events_by_user("charlie") == []


class TestAuditTrailExport:
    """Audit trail export."""

    def test_export_events_json(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        trail.log_event("logout", {"user_id": "u1"})
        exported = trail.export_events("json")
        data = json.loads(exported)
        assert len(data) == 2
        assert data[0]["event_type"] == "login"
        assert data[1]["event_type"] == "logout"

    def test_export_events_json_structure(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        exported = trail.export_events("json")
        data = json.loads(exported)
        assert "event_type" in data[0]
        assert "details" in data[0]
        assert "timestamp" in data[0]

    def test_export_events_empty(self):
        trail = AuditTrail()
        exported = trail.export_events("json")
        assert json.loads(exported) == []

    def test_export_events_csv(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        trail.log_event("logout", {"user_id": "u1"})
        exported = trail.export_events("csv")
        lines = exported.strip().split("\n")
        assert len(lines) == 3  # header + 2 events
        assert "event_type" in lines[0]
        assert "login" in lines[1]
        assert "logout" in lines[2]

    def test_export_events_invalid_format_raises(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        with pytest.raises(ValueError):
            trail.export_events("xml")


class TestAuditTrailClear:
    """Audit trail clear."""

    def test_clear_events_removes_all(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        trail.log_event("logout", {"user_id": "u1"})
        trail.clear_events()
        assert trail.get_event_count() == 0
        assert trail.get_events("login") == []

    def test_clear_events_allows_new_logging(self):
        trail = AuditTrail()
        trail.log_event("login", {"user_id": "u1"})
        trail.clear_events()
        trail.log_event("login", {"user_id": "u2"})
        assert trail.get_event_count() == 1
        events = trail.get_events("login")
        assert events[0]["details"]["user_id"] == "u2"


# ---------------------------------------------------------------------------
# ComplianceReport tests
# ---------------------------------------------------------------------------


class TestComplianceReport:
    """Compliance report generation and control status."""

    def test_generate_report_returns_report(self):
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
            {"id": "C2", "name": "Encryption", "status": "fail"},
        ]
        report = generate_report("SOC2", controls)
        assert isinstance(report, ComplianceReport)
        assert report.standard == "SOC2"
        assert len(report.controls) == 2
        assert report.status in ("compliant", "non_compliant")

    def test_generate_report_all_pass_is_compliant(self):
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
            {"id": "C2", "name": "Encryption", "status": "pass"},
        ]
        report = generate_report("SOC2", controls)
        assert report.status == "compliant"

    def test_generate_report_any_fail_is_non_compliant(self):
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
            {"id": "C2", "name": "Encryption", "status": "fail"},
        ]
        report = generate_report("SOC2", controls)
        assert report.status == "non_compliant"

    def test_generate_report_has_timestamp(self):
        controls = [{"id": "C1", "name": "Access Control", "status": "pass"}]
        before = time.time()
        report = generate_report("SOC2", controls)
        after = time.time()
        assert before <= report.timestamp <= after

    def test_get_control_status(self):
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
            {"id": "C2", "name": "Encryption", "status": "fail"},
        ]
        report = generate_report("SOC2", controls)
        assert report.get_control_status("C1") == "pass"
        assert report.get_control_status("C2") == "fail"

    def test_get_control_status_unknown_returns_none(self):
        controls = [{"id": "C1", "name": "Access Control", "status": "pass"}]
        report = generate_report("SOC2", controls)
        assert report.get_control_status("UNKNOWN") is None

    def test_get_remediation_for_failed_control(self):
        controls = [
            {
                "id": "C1",
                "name": "Access Control",
                "status": "fail",
                "remediation": "Enable MFA for all users",
            },
        ]
        report = generate_report("SOC2", controls)
        assert report.get_remediation("C1") == "Enable MFA for all users"

    def test_get_remediation_for_passing_control_returns_none(self):
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
        ]
        report = generate_report("SOC2", controls)
        assert report.get_remediation("C1") is None

    def test_get_remediation_unknown_control_returns_none(self):
        controls = [{"id": "C1", "name": "Access Control", "status": "pass"}]
        report = generate_report("SOC2", controls)
        assert report.get_remediation("UNKNOWN") is None


# ---------------------------------------------------------------------------
# ComplianceMonitor tests
# ---------------------------------------------------------------------------


class TestComplianceMonitor:
    """Compliance monitor checks, violations, and scoring."""

    def test_check_compliance_returns_report(self):
        monitor = ComplianceMonitor()
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
            {"id": "C2", "name": "Encryption", "status": "pass"},
        ]
        report = monitor.check_compliance("SOC2", controls)
        assert isinstance(report, ComplianceReport)
        assert report.standard == "SOC2"
        assert report.status == "compliant"

    def test_check_compliance_detects_violations(self):
        monitor = ComplianceMonitor()
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
            {"id": "C2", "name": "Encryption", "status": "fail"},
        ]
        monitor.check_compliance("SOC2", controls)
        violations = monitor.get_violations()
        assert len(violations) == 1
        assert violations[0]["control_id"] == "C2"

    def test_get_violations_empty_when_compliant(self):
        monitor = ComplianceMonitor()
        controls = [
            {"id": "C1", "name": "Access Control", "status": "pass"},
        ]
        monitor.check_compliance("SOC2", controls)
        assert monitor.get_violations() == []

    def test_get_remediation_plan(self):
        monitor = ComplianceMonitor()
        controls = [
            {
                "id": "C1",
                "name": "Access Control",
                "status": "fail",
                "remediation": "Enable MFA",
            },
        ]
        monitor.check_compliance("SOC2", controls)
        violations = monitor.get_violations()
        plan = monitor.get_remediation_plan(violations[0])
        assert plan is not None
        assert "remediation" in plan
        assert plan["remediation"] == "Enable MFA"

    def test_get_remediation_plan_without_remediation(self):
        monitor = ComplianceMonitor()
        controls = [
            {"id": "C1", "name": "Access Control", "status": "fail"},
        ]
        monitor.check_compliance("SOC2", controls)
        violations = monitor.get_violations()
        plan = monitor.get_remediation_plan(violations[0])
        assert plan is not None
        assert "remediation" in plan

    def test_track_control(self):
        monitor = ComplianceMonitor()
        monitor.track_control("C1", "pass")
        monitor.track_control("C2", "fail")
        score = monitor.get_compliance_score()
        assert score == 50.0

    def test_track_control_all_pass_score_100(self):
        monitor = ComplianceMonitor()
        monitor.track_control("C1", "pass")
        monitor.track_control("C2", "pass")
        assert monitor.get_compliance_score() == 100.0

    def test_track_control_no_controls_score_zero(self):
        monitor = ComplianceMonitor()
        assert monitor.get_compliance_score() == 0.0

    def test_track_control_updates_existing(self):
        monitor = ComplianceMonitor()
        monitor.track_control("C1", "fail")
        monitor.track_control("C1", "pass")
        assert monitor.get_compliance_score() == 100.0


# ---------------------------------------------------------------------------
# GovernancePolicy and ComplianceStandard tests
# ---------------------------------------------------------------------------


class TestGovernancePolicy:
    """Governance policy creation."""

    def test_governance_policy_creation(self):
        rules = [
            {"id": "R1", "action": "deny", "resource": "sensitive_data"},
            {"id": "R2", "action": "allow", "resource": "public_data"},
        ]
        policy = GovernancePolicy(
            name="Data Access Policy",
            description="Controls who can access what data",
            rules=rules,
            enforcement="strict",
        )
        assert policy.name == "Data Access Policy"
        assert policy.description == "Controls who can access what data"
        assert len(policy.rules) == 2
        assert policy.enforcement == "strict"

    def test_governance_policy_rules_content(self):
        rules = [{"id": "R1", "action": "deny", "resource": "sensitive_data"}]
        policy = GovernancePolicy(
            name="Test Policy",
            description="Test",
            rules=rules,
            enforcement="strict",
        )
        assert policy.rules[0]["action"] == "deny"
        assert policy.rules[0]["resource"] == "sensitive_data"


class TestComplianceStandard:
    """Compliance standard enum and requirements."""

    def test_standard_enum_values(self):
        assert ComplianceStandard.SOC2.value == "SOC2"
        assert ComplianceStandard.GDPR.value == "GDPR"
        assert ComplianceStandard.ISO27001.value == "ISO27001"
        assert ComplianceStandard.NIST_AI_RMF.value == "NIST_AI_RMF"
        assert ComplianceStandard.EU_AI_ACT.value == "EU_AI_ACT"

    def test_get_standard_requirements_soc2(self):
        reqs = get_standard_requirements(ComplianceStandard.SOC2)
        assert isinstance(reqs, list)
        assert len(reqs) > 0
        assert all(isinstance(r, dict) for r in reqs)

    def test_get_standard_requirements_gdpr(self):
        reqs = get_standard_requirements(ComplianceStandard.GDPR)
        assert isinstance(reqs, list)
        assert len(reqs) > 0

    def test_get_standard_requirements_iso27001(self):
        reqs = get_standard_requirements(ComplianceStandard.ISO27001)
        assert isinstance(reqs, list)
        assert len(reqs) > 0

    def test_get_standard_requirements_nist_ai_rmf(self):
        reqs = get_standard_requirements(ComplianceStandard.NIST_AI_RMF)
        assert isinstance(reqs, list)
        assert len(reqs) > 0

    def test_get_standard_requirements_eu_ai_act(self):
        reqs = get_standard_requirements(ComplianceStandard.EU_AI_ACT)
        assert isinstance(reqs, list)
        assert len(reqs) > 0

    def test_get_standard_requirements_have_ids(self):
        for standard in ComplianceStandard:
            reqs = get_standard_requirements(standard)
            assert all("id" in r for r in reqs), f"Missing id in {standard}"

    def test_get_standard_requirements_unique_per_standard(self):
        all_ids = set()
        for standard in ComplianceStandard:
            reqs = get_standard_requirements(standard)
            ids = [r["id"] for r in reqs]
            # IDs should be unique within a standard
            assert len(ids) == len(set(ids)), f"Duplicate ids in {standard}"
