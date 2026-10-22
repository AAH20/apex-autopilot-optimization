"""Adversarial tests for the PolicyEngine governance gate.

Property-based tests assert invariants (unauthorized roles always denied,
critical risk always HARD_EMERGENCY-vetoed, high-value targets never allowed
outright with HITL on, auto-approve still respects auth/critical) across
generated assignments; directed tests pin veto authority, HITL approve/reject,
cycle budget, and unknown-request handling.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apex_autopilot_optimization.chaos.probes import (
    policy_critical_vetoed,
    policy_high_value_not_allowed,
    policy_unauthorized_denied,
)
from apex_autopilot_optimization.governance.policy_engine import (
    Decision,
    PolicyAction,
    PolicyEngine,
    PolicyEngineConfig,
    Role,
    WTAAssignment,
)
from apex_autopilot_optimization.messaging.veto_manager import (
    VETO_CLEAR,
    VETO_HARD_EMERGENCY,
    VetoManager,
)

_UNAUTHORIZED_FOR_WTA = st.sampled_from([Role.OPERATOR, Role.PILOT])
_AUTHORIZED_FOR_WTA = st.sampled_from([Role.SOLVER, Role.AUTONOMOUS_AGENT, Role.GOVERNANCE])


class FakeHITL:
    def __init__(self) -> None:
        self.submitted = []
        self.approved = []
        self.rejected = []

    def submit(self, request):
        self.submitted.append(request)
        return request

    def approve(self, request_id, approver="operator"):
        self.approved.append((request_id, approver))

    def reject(self, request_id, approver="operator", reason=""):
        self.rejected.append((request_id, approver, reason))

    def get_status(self, request_id):
        return "pending"


def make_assignment(
    assignment_id="wa-1",
    weapon_id="w1",
    target_id="t1",
    target_value=10.0,
    kill_probability=0.5,
) -> WTAAssignment:
    return WTAAssignment(
        assignment_id=assignment_id,
        weapon_id=weapon_id,
        target_id=target_id,
        target_value=target_value,
        kill_probability=kill_probability,
        context={"weapon_id": weapon_id, "target_id": target_id},
    )


def make_engine(*, hitl_enabled=True, clock_value=1000.0, **config_overrides):
    hitl = FakeHITL()
    veto_manager = VetoManager()
    config = PolicyEngineConfig(hitl_enabled=hitl_enabled, **config_overrides)
    clock = lambda: clock_value  # noqa: E731
    engine = PolicyEngine(veto_manager=veto_manager, hitl=hitl, config=config, clock=clock)
    return engine, hitl, veto_manager


# --------------------------------------------------------------------------- #
# Property-based
# --------------------------------------------------------------------------- #


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    role=_UNAUTHORIZED_FOR_WTA,
    target_value=st.floats(0.0, 1e4, allow_nan=False, allow_infinity=False),
    kill_probability=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
)
def test_unauthorized_role_always_denied(role, target_value, kill_probability) -> None:
    engine, hitl, veto_manager = make_engine()
    decision = engine.evaluate_assignment(
        make_assignment(target_value=target_value, kill_probability=kill_probability), role
    )
    allowed_roles = engine.policies[PolicyAction.WTA_ASSIGNMENT].allowed_roles
    violations = policy_unauthorized_denied(decision, allowed_roles)
    assert violations == [], violations
    assert decision.allowed is False
    assert decision.decision is Decision.DENIED
    assert hitl.submitted == []
    assert veto_manager.active() is not None


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    role=_AUTHORIZED_FOR_WTA,
    kill_probability=st.floats(0.9, 1.0, allow_nan=False, allow_infinity=False),
    target_value=st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False),
)
def test_critical_kill_prob_vetoed(role, kill_probability, target_value) -> None:
    """kill_prob >= 0.9 => CRITICAL risk => denied + HARD_EMERGENCY veto."""
    engine, hitl, veto_manager = make_engine()
    decision = engine.evaluate_assignment(
        make_assignment(kill_probability=kill_probability, target_value=target_value), role
    )
    assert decision.allowed is False
    assert decision.decision is Decision.DENIED
    violations = policy_critical_vetoed(decision)
    assert violations == [], violations
    veto = veto_manager.active()
    assert veto is not None
    assert veto.veto_type == VETO_HARD_EMERGENCY
    assert veto.severity == 5


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    role=_AUTHORIZED_FOR_WTA,
    target_value=st.floats(1001.0, 1e6, allow_nan=False, allow_infinity=False),
    kill_probability=st.floats(0.0, 0.5, allow_nan=False, allow_infinity=False),
)
def test_high_value_not_allowed_with_hitl(role, target_value, kill_probability) -> None:
    """Above-threshold target value must never be allowed outright (HITL on)."""
    engine, hitl, veto_manager = make_engine()
    decision = engine.evaluate_assignment(
        make_assignment(target_value=target_value, kill_probability=kill_probability), role
    )
    violations = policy_high_value_not_allowed(
        decision, target_value, engine.config.high_value_target_threshold, hitl_enabled=True
    )
    assert violations == [], violations
    # Must be held for approval or denied, never allowed outright.
    assert decision.decision in (Decision.PENDING_APPROVAL, Decision.DENIED)
    assert decision.allowed is False
    assert len(hitl.submitted) == 1


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    role=_AUTHORIZED_FOR_WTA,
    kill_probability=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
    target_value=st.floats(0.0, 999.0, allow_nan=False, allow_infinity=False),
)
def test_hitl_disabled_auto_approve_still_enforces_auth_and_critical(
    role, kill_probability, target_value
) -> None:
    """HITL disabled + auto-approve: sub-critical allowed, critical still denied."""
    engine, hitl, veto_manager = make_engine(hitl_enabled=False)
    decision = engine.evaluate_assignment(
        make_assignment(target_value=target_value, kill_probability=kill_probability), role
    )
    if kill_probability >= 0.9:
        # CRITICAL risk: deny_above_risk applies even with auto-approve.
        assert decision.allowed is False
        assert decision.decision is Decision.DENIED
        veto = veto_manager.active()
        assert veto is not None
        assert veto.veto_type == VETO_HARD_EMERGENCY
    else:
        # Sub-critical, sub-threshold: auto-approved, no HITL submission.
        assert decision.allowed is True
        assert decision.decision is Decision.ALLOWED
        assert hitl.submitted == []
        assert veto_manager.active() is None


# --------------------------------------------------------------------------- #
# Directed
# --------------------------------------------------------------------------- #


class TestDirected:
    def test_cycle_over_budget_flagged(self) -> None:
        engine, hitl, _ = make_engine(hitl_enabled=False)
        ticks = iter([0.0, 0.3])  # 300 ms > 100 ms budget
        engine._clock = lambda: next(ticks)
        # High-value target requires approval; HITL disabled -> auto-approve path.
        decision = engine.evaluate_assignment(make_assignment(target_value=5000.0), Role.SOLVER)
        assert decision.allowed is True
        assert decision.auto_approved is True
        assert decision.budget_exceeded is True
        assert decision.cycle_ms == 300.0
        assert hitl.submitted == []

    def test_hitl_disabled_auto_approves_high_value(self) -> None:
        engine, hitl, veto_manager = make_engine(hitl_enabled=False)
        decision = engine.evaluate_assignment(make_assignment(target_value=1500.0), Role.SOLVER)
        assert decision.allowed is True
        assert decision.auto_approved is True
        assert hitl.submitted == []
        assert veto_manager.active() is None

    def test_approve_releases_veto(self) -> None:
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(target_value=5000.0), Role.SOLVER)
        assert veto_manager.is_active()
        assert decision.request_id is not None
        result = engine.approve(decision.request_id, approver="operator-1")
        assert result.allowed is True
        assert result.decision is Decision.ALLOWED
        assert veto_manager.active() is None
        assert veto_manager.veto_type() == VETO_CLEAR

    def test_reject_keeps_veto(self) -> None:
        engine, hitl, veto_manager = make_engine()
        decision = engine.evaluate_assignment(make_assignment(target_value=5000.0), Role.SOLVER)
        assert decision.request_id is not None
        result = engine.reject(decision.request_id, approver="operator-1", reason="unsafe geometry")
        assert result.allowed is False
        assert result.decision is Decision.DENIED
        assert result.reason == "unsafe geometry"
        assert veto_manager.is_active()

    def test_unknown_request_raises(self) -> None:
        engine, _, _ = make_engine()
        with pytest.raises(KeyError):
            engine.approve("no-such-request", approver="op")
        with pytest.raises(KeyError):
            engine.reject("no-such-request", approver="op", reason="x")

    def test_veto_authority_chain(self) -> None:
        engine, _, veto_manager = make_engine()
        engine.evaluate_assignment(make_assignment(), Role.OPERATOR)
        assert veto_manager.is_active()
        veto = veto_manager.active()
        assert veto is not None
        assert veto.authority == "apex/governance"
        # governance clears anything
        assert engine.clear_veto("apex/governance") is True
        assert veto_manager.is_active() is False
        # re-issue, then lower authority cannot clear
        engine.evaluate_assignment(make_assignment(), Role.OPERATOR)
        assert engine.clear_veto("operator") is False
        assert veto_manager.is_active() is True

    def test_custom_veto_authority(self) -> None:
        engine, _, veto_manager = make_engine(veto_authority="apex/safety")
        engine.evaluate_assignment(make_assignment(), Role.OPERATOR)
        veto = veto_manager.active()
        assert veto is not None
        assert veto.authority == "apex/safety"

    def test_emergency_stop_operator_and_governance_only(self) -> None:
        engine, _, _ = make_engine()
        assert engine.evaluate_action(PolicyAction.EMERGENCY_STOP, Role.GOVERNANCE).allowed is True
        assert engine.evaluate_action(PolicyAction.EMERGENCY_STOP, Role.OPERATOR).allowed is True
        assert engine.evaluate_action(PolicyAction.EMERGENCY_STOP, Role.PILOT).allowed is False
