"""Unit tests for the human-in-the-loop (HITL) approval and override system.

Covers approval status enumeration, approval request creation, the approval
workflow (submit/approve/reject/escalate), pending/status/audit-trail queries,
human overrides (request/list/count), and HITL configuration.
"""

import time

import pytest

from apex_autopilot_optimization.hitl import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalWorkflow,
    HITLConfig,
    HumanOverride,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_request(**overrides) -> ApprovalRequest:
    kwargs = {
        "id": "req-001",
        "action": "arm_motors",
        "requester": "autopilot",
        "context": {"altitude_m": 120, "battery_pct": 87},
        "priority": "high",
        "created_at": 1000.0,
        "expires_at": 1060.0,
    }
    kwargs.update(overrides)
    return ApprovalRequest(**kwargs)


@pytest.fixture
def workflow() -> ApprovalWorkflow:
    return ApprovalWorkflow()


@pytest.fixture
def submitted(workflow) -> ApprovalRequest:
    return workflow.submit(make_request())


# ---------------------------------------------------------------------------
# ApprovalStatus enumeration
# ---------------------------------------------------------------------------


class TestApprovalStatus:
    def test_status_values_are_unique_strings(self):
        values = [s.value for s in ApprovalStatus]
        assert len(values) == len(set(values))
        assert all(isinstance(v, str) for v in values)

    def test_status_has_exactly_five_members(self):
        assert len(ApprovalStatus) == 5

    def test_status_lookup_by_value(self):
        assert ApprovalStatus("pending") is ApprovalStatus.PENDING
        assert ApprovalStatus("approved") is ApprovalStatus.APPROVED
        assert ApprovalStatus("rejected") is ApprovalStatus.REJECTED
        assert ApprovalStatus("expired") is ApprovalStatus.EXPIRED
        assert ApprovalStatus("escalated") is ApprovalStatus.ESCALATED

    def test_invalid_status_value_raises(self):
        with pytest.raises(ValueError):
            ApprovalStatus("bogus")


# ---------------------------------------------------------------------------
# ApprovalRequest creation
# ---------------------------------------------------------------------------


class TestApprovalRequest:
    def test_creation_with_required_fields(self):
        req = make_request()
        assert req.id == "req-001"
        assert req.action == "arm_motors"
        assert req.requester == "autopilot"
        assert req.context == {"altitude_m": 120, "battery_pct": 87}
        assert req.priority == "high"
        assert req.created_at == 1000.0
        assert req.expires_at == 1060.0

    def test_creation_without_expiry(self):
        req = make_request(expires_at=None)
        assert req.expires_at is None

    def test_requests_with_differing_ids_are_not_equal(self):
        assert make_request(id="a") != make_request(id="b")

    def test_request_equality_same_id(self):
        assert make_request(id="same") == make_request(id="same")


# ---------------------------------------------------------------------------
# ApprovalWorkflow: submit / approve / reject / escalate
# ---------------------------------------------------------------------------


class TestApprovalWorkflowTransitions:
    def test_submit_returns_request_and_marks_pending(self, workflow, submitted):
        assert isinstance(submitted, ApprovalRequest)
        assert workflow.get_status(submitted.id) is ApprovalStatus.PENDING

    def test_submit_assigns_id_when_empty(self, workflow):
        req = workflow.submit(make_request(id=""))
        assert req.id  # non-empty id assigned

    def test_approve_moves_request_to_approved(self, workflow, submitted):
        workflow.approve(submitted.id, approver="operator-1")
        assert workflow.get_status(submitted.id) is ApprovalStatus.APPROVED

    def test_reject_moves_request_to_rejected(self, workflow, submitted):
        workflow.reject(submitted.id, approver="operator-1", reason="unsafe wind")
        assert workflow.get_status(submitted.id) is ApprovalStatus.REJECTED

    def test_escalate_moves_request_to_escalated(self, workflow, submitted):
        workflow.escalate(submitted.id, reason="no operator available")
        assert workflow.get_status(submitted.id) is ApprovalStatus.ESCALATED

    def test_approve_unknown_request_raises(self, workflow):
        with pytest.raises(KeyError):
            workflow.approve("does-not-exist", approver="op")

    def test_reject_unknown_request_raises(self, workflow):
        with pytest.raises(KeyError):
            workflow.reject("does-not-exist", approver="op", reason="x")

    def test_escalate_unknown_request_raises(self, workflow):
        with pytest.raises(KeyError):
            workflow.escalate("does-not-exist", reason="x")

    def test_double_transition_raises(self, workflow, submitted):
        workflow.approve(submitted.id, approver="op")
        with pytest.raises(RuntimeError):
            workflow.reject(submitted.id, approver="op", reason="too late")


# ---------------------------------------------------------------------------
# ApprovalWorkflow: pending / status / audit trail
# ---------------------------------------------------------------------------


class TestApprovalWorkflowQueries:
    def test_get_pending_only_returns_pending(self, workflow):
        r1 = workflow.submit(make_request(id="r1"))
        r2 = workflow.submit(make_request(id="r2"))
        workflow.approve(r2.id, approver="op")
        pending = workflow.get_pending()
        assert [r.id for r in pending] == [r1.id]

    def test_get_pending_empty_when_nothing_submitted(self, workflow):
        assert workflow.get_pending() == []

    def test_get_status_unknown_request_raises(self, workflow):
        with pytest.raises(KeyError):
            workflow.get_status("nope")

    def test_get_audit_trail_records_each_transition(self, workflow, submitted):
        trail = workflow.get_audit_trail(submitted.id)
        assert len(trail) == 1  # submit
        workflow.approve(submitted.id, approver="op")
        trail = workflow.get_audit_trail(submitted.id)
        assert len(trail) == 2
        assert trail[-1]["new_status"] == ApprovalStatus.APPROVED.value
        assert trail[-1]["actor"] == "op"

    def test_get_audit_trail_unknown_request_raises(self, workflow):
        with pytest.raises(KeyError):
            workflow.get_audit_trail("nope")

    def test_expired_request_detected_via_status(self, workflow):
        req = workflow.submit(make_request(created_at=time.time() - 120, expires_at=time.time() - 60))
        assert workflow.get_status(req.id) is ApprovalStatus.EXPIRED

    def test_unexpired_request_stays_pending(self, workflow):
        req = workflow.submit(make_request(created_at=time.time(), expires_at=time.time() + 300))
        assert workflow.get_status(req.id) is ApprovalStatus.PENDING

    def test_no_expiry_never_expires(self, workflow):
        req = workflow.submit(make_request(created_at=time.time() - 100000, expires_at=None))
        assert workflow.get_status(req.id) is ApprovalStatus.PENDING


# ---------------------------------------------------------------------------
# HumanOverride
# ---------------------------------------------------------------------------


class TestHumanOverride:
    def test_request_override_creates_and_stores(self, workflow):
        ov = workflow.request_override("land_now", "operator-9", "GPS drift detected")
        assert isinstance(ov, HumanOverride)
        assert ov.original_decision == "land_now"
        assert ov.override_decision != ov.original_decision
        assert ov.operator == "operator-9"
        assert ov.reason == "GPS drift detected"
        assert ov.timestamp > 0

    def test_get_override_roundtrip(self, workflow):
        ov = workflow.request_override("takeoff", "op", "manual control")
        fetched = workflow.get_override(ov.id)
        assert fetched == ov

    def test_get_override_unknown_raises(self, workflow):
        with pytest.raises(KeyError):
            workflow.get_override("no-such-override")

    def test_list_overrides_returns_all_in_order(self, workflow):
        ov1 = workflow.request_override("a", "op1", "r1")
        ov2 = workflow.request_override("b", "op2", "r2")
        overrides = workflow.list_overrides()
        assert [o.id for o in overrides] == [ov1.id, ov2.id]

    def test_get_override_count(self, workflow):
        assert workflow.get_override_count() == 0
        workflow.request_override("a", "op", "r")
        workflow.request_override("b", "op", "r")
        assert workflow.get_override_count() == 2


# ---------------------------------------------------------------------------
# HITLConfig
# ---------------------------------------------------------------------------


class TestHITLConfig:
    def test_defaults(self):
        cfg = HITLConfig()
        assert cfg.enabled is True
        assert cfg.auto_approve_low_risk is False
        assert cfg.require_dual_approval is False
        assert cfg.approval_timeout_seconds > 0
        assert cfg.max_pending_approvals > 0

    def test_custom_values(self):
        cfg = HITLConfig(
            enabled=False,
            auto_approve_low_risk=True,
            require_dual_approval=True,
            approval_timeout_seconds=12.5,
            max_pending_approvals=3,
        )
        assert cfg.enabled is False
        assert cfg.auto_approve_low_risk is True
        assert cfg.require_dual_approval is True
        assert cfg.approval_timeout_seconds == 12.5
        assert cfg.max_pending_approvals == 3

    def test_config_gates_workflow_behavior(self):
        cfg = HITLConfig(enabled=False)
        wf = ApprovalWorkflow(config=cfg)
        req = wf.submit(make_request())
        # Disabled HITL: requests are not held pending.
        assert wf.get_status(req.id) is not ApprovalStatus.PENDING

    def test_max_pending_approvals_enforced(self):
        cfg = HITLConfig(max_pending_approvals=1)
        wf = ApprovalWorkflow(config=cfg)
        wf.submit(make_request(id="r1"))
        with pytest.raises(RuntimeError):
            wf.submit(make_request(id="r2"))
