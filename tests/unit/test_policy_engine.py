"""Unit tests for ``governance.policy_engine.PolicyEngine``.

Covers policy evaluation (allowed actions per role, risk thresholds,
approval requirements), veto emission (CLEAR / SOFT_HOLD /
HARD_EMERGENCY) via the veto manager on policy violation, HITL workflow
integration (submit / approve / reject), and the auto-approve bypass for
sub-100 ms autonomous cycles when HITL is disabled.

RED-GREEN-REFACTOR: these tests are written before the implementation.
"""

import sys
from pathlib import Path

# sys.path bootstrap must precede the package imports below.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
for _path in (_SRC, _REPO_ROOT):
    _sp = str(_path)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import pytest  # noqa: E402

from apex_autopilot_optimization.governance.policy_engine import (  # noqa: E402
    ActionPolicy,
    Decision,
    PolicyAction,
    PolicyEngine,
    PolicyEngineConfig,
    RiskLevel,
    Role,
    VetoType,
    WTAAssignment,
)
from apex_autopilot_optimization.messaging.veto_manager import (  # noqa: E402
    VETO_CLEAR,
    VETO_HARD_EMERGENCY,
    VETO_SOFT_HOLD,
    VetoManager,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeHITL:
    """Stand-in for HITLAdapter/ApprovalWorkflow: records submit/approve/reject."""

    def __init__(self) -> None:
        self.submitted: list = []
        self.approved: list[tuple[str, str]] = []
        self.rejected: list[tuple[str, str, str]] = []

    def submit(self, request: object) -> object:
        self.submitted.append(request)
        return request

    def approve(self, request_id: str, approver: str = "operator") -> None:
        self.approved.append((request_id, approver))

    def reject(self, request_id: str, approver: str = "operator", reason: str = "") -> None:
        self.rejected.append((request_id, approver, reason))

    def get_status(self, request_id: str) -> str:
        return "pending"


def make_assignment(
    assignment_id: str = "wa-1",
    weapon_id: str = "w1",
    target_id: str = "t1",
    target_value: float = 10.0,
    kill_probability: float = 0.5,
) -> WTAAssignment:
    return WTAAssignment(
        assignment_id=assignment_id,
        weapon_id=weapon_id,
        target_id=target_id,
        target_value=target_value,
        kill_probability=kill_probability,
        context={"weapon_id": weapon_id, "target_id": target_id},
    )


def make_engine(
    *,
    hitl_enabled: bool = True,
    hitl: FakeHITL | None = None,
    clock_value: float = 1000.0,
    **config_overrides,
) -> tuple[PolicyEngine, FakeHITL, VetoManager]:
    hitl = hitl or FakeHITL()
    veto_manager = VetoManager()
    config = PolicyEngineConfig(hitl_enabled=hitl_enabled, **config_overrides)
    clock = lambda: clock_value  # noqa: E731
    engine = PolicyEngine(
        veto_manager=veto_manager,
        hitl=hitl,
        config=config,
        clock=clock,
    )
    return engine, hitl, veto_manager


# ---------------------------------------------------------------------------
# Veto type codes
# ---------------------------------------------------------------------------


class TestVetoTypeCodes:
    def test_veto_type_codes_match_contract(self):
        assert VetoType.CLEAR is VetoType(VETO_CLEAR)
        assert VetoType.SOFT_HOLD is VetoType(VETO_SOFT_HOLD)
        assert VetoType.HARD_EMERGENCY is VetoType(VETO_HARD_EMERGENCY)
        assert int(VetoType.CLEAR) == 0
        assert int(VetoType.SOFT_HOLD) == 1
        assert int(VetoType.HARD_EMERGENCY) == 2


# ---------------------------------------------------------------------------
# Default policies (agent-exec actions per role, risk, approval)
# ---------------------------------------------------------------------------


class TestDefaultPolicies:
    def test_every_agent_action_has_a_default_policy(self):
        engine, _, _ = make_engine()
        for action in PolicyAction:
            assert action in engine.policies

    def test_arm_policy(self):
        engine, _, _ = make_engine()
        policy = engine.policies[PolicyAction.ARM]
        assert Role.OPERATOR in policy.allowed_roles
        assert Role.PILOT in policy.allowed_roles
        assert Role.AUTONOMOUS_AGENT in policy.allowed_roles
        assert Role.SOLVER not in policy.allowed_roles
        assert policy.risk_threshold is RiskLevel.HIGH
        assert policy.requires_approval is True

    def test_send_control_needs_no_approval(self):
        engine, _, _ = make_engine()
        policy = engine.policies[PolicyAction.SEND_CONTROL]
        assert policy.requires_approval is False
        assert policy.risk_threshold is RiskLevel.LOW

    def test_emergency_stop_is_operator_and_governance_only(self):
        engine, _, _ = make_engine()
        policy = engine.policies[PolicyAction.EMERGENCY_STOP]
        assert policy.allowed_roles == frozenset({Role.OPERATOR, Role.GOVERNANCE})
        assert policy.requires_approval is False

    def test_wta_assignment_requires_approval_at_high_risk(self):
        engine, _, _ = make_engine()
        policy = engine.policies[PolicyAction.WTA_ASSIGNMENT]
        assert Role.SOLVER in policy.allowed_roles
        assert policy.requires_approval is True
        assert policy.risk_threshold is RiskLevel.HIGH
        assert policy.deny_above_risk is RiskLevel.CRITICAL

    def test_custom_config_replaces_default_policies(self):
        custom = {
            PolicyAction.SEND_CONTROL: ActionPolicy(
                allowed_roles=frozenset({Role.GOVERNANCE}),
                risk_threshold=RiskLevel.CRITICAL,
                requires_approval=True,
            )
        }
        engine, _, _ = make_engine(default_policies=custom)
        assert engine.policies[PolicyAction.SEND_CONTROL].allowed_roles == (
            frozenset({Role.GOVERNANCE})
        )
        # Untouched actions keep their defaults.
        assert engine.policies[PolicyAction.ARM].requires_approval is True


# ---------------------------------------------------------------------------
# Policy evaluation: role authorization
# ---------------------------------------------------------------------------


class TestRoleAuthorization:
    def test_solver_wta_assignment_is_authorized_and_allowed(self):
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(target_value=10.0), Role.SOLVER)

        assert decision.allowed is True
        assert decision.decision is Decision.ALLOWED
        assert decision.violations == []
        assert decision.veto is None
        assert hitl.submitted == []
        assert veto_manager.active() is None

    def test_operator_wta_assignment_is_not_authorized(self):
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(), Role.OPERATOR)

        assert decision.allowed is False
        assert decision.decision is Decision.DENIED
        assert any("not authorized" in v for v in decision.violations)
        assert hitl.submitted == []
        veto = veto_manager.active()
        assert veto is not None
        assert veto.veto_type == VETO_SOFT_HOLD
        assert veto.authority == "apex/governance"
        assert veto.reason

    def test_governance_can_issue_emergency_stop_but_pilot_cannot(self):
        engine, _, _ = make_engine()
        allowed_governance = engine.evaluate_action(PolicyAction.EMERGENCY_STOP, Role.GOVERNANCE)
        allowed_operator = engine.evaluate_action(PolicyAction.EMERGENCY_STOP, Role.OPERATOR)
        denied_pilot = engine.evaluate_action(PolicyAction.EMERGENCY_STOP, Role.PILOT)

        assert allowed_governance.allowed is True
        assert allowed_operator.allowed is True
        assert denied_pilot.allowed is False
        assert denied_pilot.decision is Decision.DENIED

    def test_disallowed_action_emits_no_hitl_submission(self):
        engine, hitl, _ = make_engine()
        engine.evaluate_assignment(make_assignment(), Role.OPERATOR)
        assert hitl.submitted == []


# ---------------------------------------------------------------------------
# Veto emission on policy violation
# ---------------------------------------------------------------------------


class TestVetoEmission:
    def test_policy_violation_emits_soft_hold_veto(self):
        engine, _, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(), Role.OPERATOR)

        assert decision.veto is not None
        assert decision.veto.veto_type == VETO_SOFT_HOLD
        assert veto_manager.active() is decision.veto
        assert veto_manager.veto_type() == VETO_SOFT_HOLD

    def test_critical_risk_emits_hard_emergency_veto(self):
        engine, _, veto_manager = make_engine()
        decision = engine.evaluate_assignment(
            make_assignment(target_value=10.0, kill_probability=0.95), Role.SOLVER
        )

        assert decision.allowed is False
        assert decision.decision is Decision.DENIED
        assert any("critical" in v.lower() or "deny" in v.lower() for v in decision.violations)
        veto = veto_manager.active()
        assert veto is not None
        assert veto.veto_type == VETO_HARD_EMERGENCY
        assert veto.severity == 5

    def test_allowed_assignment_emits_no_veto(self):
        engine, _, veto_manager = make_engine()
        engine.evaluate_assignment(make_assignment(target_value=10.0), Role.SOLVER)

        assert veto_manager.active() is None
        assert veto_manager.veto_type() == VETO_CLEAR


# ---------------------------------------------------------------------------
# HITL integration: high-value target engagement needs approval
# ---------------------------------------------------------------------------


class TestHITLHighValueApproval:
    def test_high_value_target_engagement_pending_approval_when_hitl_enabled(self):
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(
            make_assignment(target_value=5000.0, kill_probability=0.8), Role.SOLVER
        )

        assert decision.allowed is False
        assert decision.decision is Decision.PENDING_APPROVAL
        assert decision.request_id is not None
        assert decision.auto_approved is False
        assert decision.cycle_ms < 100.0
        assert not decision.budget_exceeded

        assert len(hitl.submitted) == 1
        request = hitl.submitted[0]
        assert request.action == "wta_assignment"
        assert request.context["target_value"] == 5000.0
        assert request.priority == "high"

        veto = veto_manager.active()
        assert veto is not None
        assert veto.veto_type == VETO_SOFT_HOLD
        assert "approval" in veto.reason

    def test_below_threshold_target_engagement_is_allowed_without_approval(self):
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(target_value=10.0), Role.SOLVER)

        assert decision.allowed is True
        assert decision.decision is Decision.ALLOWED
        assert decision.request_id is None
        assert hitl.submitted == []
        assert veto_manager.active() is None

    def test_medium_risk_kill_probability_does_not_require_approval(self):
        engine, hitl, _ = make_engine()
        decision = engine.evaluate_assignment(
            make_assignment(target_value=10.0, kill_probability=0.6), Role.SOLVER
        )
        assert decision.allowed is True
        assert hitl.submitted == []


class TestHITLIntegration:
    def test_approve_grants_assignment_and_releases_veto(self):
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(target_value=5000.0), Role.SOLVER)
        assert veto_manager.is_active()

        result = engine.approve(decision.request_id, approver="operator-1")

        assert result.allowed is True
        assert result.decision is Decision.ALLOWED
        assert hitl.approved == [(decision.request_id, "operator-1")]
        assert veto_manager.active() is None  # CLEAR veto released the latch
        assert veto_manager.veto_type() == VETO_CLEAR

    def test_reject_denies_assignment_and_keeps_veto(self):
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(target_value=5000.0), Role.SOLVER)

        result = engine.reject(decision.request_id, approver="operator-1", reason="unsafe geometry")

        assert result.allowed is False
        assert result.decision is Decision.DENIED
        assert result.reason == "unsafe geometry"
        assert hitl.rejected == [(decision.request_id, "operator-1", "unsafe geometry")]
        assert veto_manager.is_active()  # SOFT_HOLD stays latched

    def test_approve_unknown_request_raises(self):
        engine, _, _ = make_engine()
        with pytest.raises(KeyError):
            engine.approve("no-such-request", approver="op")

    def test_reject_unknown_request_raises(self):
        engine, _, _ = make_engine()
        with pytest.raises(KeyError):
            engine.reject("no-such-request", approver="op", reason="x")


# ---------------------------------------------------------------------------
# Auto-approve bypass: HITL disabled, sub-100 ms autonomous cycles
# ---------------------------------------------------------------------------


class TestAutoApproveBypass:
    def test_hitl_disabled_auto_approves_high_value_target(self):
        engine, hitl, veto_manager = make_engine(hitl_enabled=False)
        decision = engine.evaluate_assignment(make_assignment(target_value=5000.0), Role.SOLVER)

        assert decision.allowed is True
        assert decision.decision is Decision.ALLOWED
        assert decision.auto_approved is True
        assert decision.cycle_ms < 100.0
        assert not decision.budget_exceeded
        assert hitl.submitted == []
        assert veto_manager.active() is None

    def test_hitl_disabled_still_enforces_role_authorization(self):
        engine, hitl, _ = make_engine(hitl_enabled=False)
        decision = engine.evaluate_assignment(make_assignment(), Role.OPERATOR)

        assert decision.allowed is False
        assert decision.decision is Decision.DENIED
        assert hitl.submitted == []

    def test_hitl_disabled_still_denies_critical_risk(self):
        engine, _, veto_manager = make_engine(hitl_enabled=False)
        decision = engine.evaluate_assignment(
            make_assignment(target_value=10.0, kill_probability=0.95), Role.SOLVER
        )

        assert decision.allowed is False
        assert decision.decision is Decision.DENIED
        assert veto_manager.active() is not None
        assert veto_manager.active().veto_type == VETO_HARD_EMERGENCY

    def test_cycle_over_budget_is_flagged_but_still_auto_approves(self):
        engine, hitl, _ = make_engine(hitl_enabled=False)
        # Fake clock that advances during the call (start -> end).
        ticks = iter([0.0, 0.3])
        engine._clock = lambda: next(ticks)  # noqa: SLF001
        decision = engine.evaluate_assignment(make_assignment(target_value=5000.0), Role.SOLVER)

        assert decision.allowed is True
        assert decision.auto_approved is True
        assert decision.cycle_ms == 300.0
        assert decision.budget_exceeded is True
        assert hitl.submitted == []


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_custom_high_value_threshold(self):
        engine, hitl, _ = make_engine(
            hitl_enabled=True,
            high_value_target_threshold=100.0,
        )
        low_value = engine.evaluate_assignment(make_assignment(target_value=50.0), Role.SOLVER)
        high_value = engine.evaluate_assignment(make_assignment(target_value=150.0), Role.SOLVER)

        assert low_value.allowed is True
        assert low_value.decision is Decision.ALLOWED
        assert high_value.allowed is False
        assert high_value.decision is Decision.PENDING_APPROVAL
        assert len(hitl.submitted) == 1

    def test_custom_veto_authority(self):
        engine, _, veto_manager = make_engine(veto_authority="apex/safety")
        engine.evaluate_assignment(make_assignment(), Role.OPERATOR)
        veto = veto_manager.active()
        assert veto is not None
        assert veto.authority == "apex/safety"

    def test_clear_veto_authority_chain(self):
        engine, _, veto_manager = make_engine()
        engine.evaluate_assignment(make_assignment(), Role.OPERATOR)
        assert veto_manager.is_active()

        assert engine.clear_veto("apex/governance") is True
        assert veto_manager.is_active() is False

        engine.evaluate_assignment(make_assignment(), Role.OPERATOR)
        assert engine.clear_veto("operator") is False
        assert veto_manager.is_active() is True
