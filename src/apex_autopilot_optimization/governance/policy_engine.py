"""Agent-execution policy engine for the WTA/governance layer.

The :class:`PolicyEngine` is the governance gate between the solver (WTA
assignments) and the setpoints published to AAS. It:

1. Defines agent-exec policies -- allowed actions per role, risk
   thresholds, and approval requirements (see :class:`ActionPolicy` and
   :data:`_DEFAULT_POLICIES`).
2. Evaluates solver WTA assignments against policy before they become
   setpoints. High-value target engagement (target value above the
   configured threshold) requires human approval when HITL is enabled.
3. Emits :class:`Veto` messages (``CLEAN``/``SOFT_HOLD``/
   ``HARD_EMERGENCY``, mirroring ``apex_control_msgs/Veto``) through a
   :class:`VetoManager` on policy violation.
4. Integrates with the HITL approval workflow (``submit``/``approve``/
   ``reject``) via a duck-typed :class:`HITLWorkflow` port -- typically
   the ``HITLAdapter``/``ApprovalWorkflow``.
5. Auto-approves sub-100 ms autonomous cycles when HITL is disabled.

The engine depends only on injected collaborators (veto manager, HITL
workflow, clock), so it is straightforward to unit test without ROS2 or
MAVLink.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any, Protocol, runtime_checkable

from ..messaging.veto_manager import (
    VETO_CLEAR,
    VETO_HARD_EMERGENCY,
    VETO_SOFT_HOLD,
    Veto,
    VetoManager,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VETO_AUTHORITY: str = "apex/governance"
DEFAULT_DRONE_ID: int = 0  # 0 = fleet-wide veto
AUTO_APPROVE_CYCLE_BUDGET_MS: float = 100.0  # <100 ms autonomous-cycle budget
HIGH_VALUE_TARGET_THRESHOLD: float = 1_000.0  # target value needing approval
HIGH_KILL_PROBABILITY: float = 0.9  # kill probability treated as critical risk

# Severity per veto type (1=INFO ... 5=CRITICAL, mirroring Veto.msg).
_SEVERITY_BY_VETO_TYPE: dict[int, int] = {
    VETO_CLEAR: 1,
    VETO_SOFT_HOLD: 3,
    VETO_HARD_EMERGENCY: 5,
}

# Actions that are allowed/denied outright and never submitted for
# approval, even when HITL is enabled (e.g. emergency stop).
_IMMEDIATE_ACTIONS: frozenset[PolicyAction] = frozenset()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(StrEnum):
    """Principal roles that may request agent-exec actions."""

    OPERATOR = "operator"
    PILOT = "pilot"
    AUTONOMOUS_AGENT = "autonomous_agent"
    SOLVER = "solver"
    GOVERNANCE = "governance"


class PolicyAction(StrEnum):
    """Agent-exec actions governed by policy."""

    ARM = "arm"
    DISARM = "disarm"
    SET_MODE = "set_mode"
    SEND_CONTROL = "send_control"
    TAKEOFF = "takeoff"
    LAND = "land"
    ENGAGE_TARGET = "engage_target"
    WTA_ASSIGNMENT = "wta_assignment"
    EMERGENCY_STOP = "emergency_stop"


_IMMEDIATE_ACTIONS = frozenset({PolicyAction.EMERGENCY_STOP})


class RiskLevel(IntEnum):
    """Risk ordering: higher is more dangerous."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class VetoType(IntEnum):
    """Veto type codes mirroring apex_control_msgs/Veto."""

    CLEAR = VETO_CLEAR  # 0 - release the veto latch
    SOFT_HOLD = VETO_SOFT_HOLD  # 1 - hold last safe state, no new setpoints
    HARD_EMERGENCY = VETO_HARD_EMERGENCY  # 2 - cancel goals, LAND, disarm


class Decision(StrEnum):
    """Outcome of a policy evaluation."""

    ALLOWED = "allowed"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"


# ---------------------------------------------------------------------------
# Policy / assignment / decision dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionPolicy:
    """Policy for a single agent-exec action.

    Attributes:
        allowed_roles: Principals allowed to request the action.
        risk_threshold: Risk at or above this level requires approval when
            HITL is enabled.
        requires_approval: Whether the action needs human approval at all.
        max_target_value: Maximum target value permitted (``None`` =
            unchecked).
        deny_above_risk: Risk at or above this level is a hard denial
            regardless of HITL state (``None`` = unchecked).
    """

    allowed_roles: frozenset[Role]
    risk_threshold: RiskLevel = RiskLevel.MEDIUM
    requires_approval: bool = False
    max_target_value: float | None = None
    deny_above_risk: RiskLevel | None = None


@dataclass(frozen=True)
class WTAAssignment:
    """A solver-produced Weapon-Target Assignment awaiting setpoint conversion."""

    assignment_id: str
    weapon_id: str
    target_id: str
    target_value: float = 0.0
    kill_probability: float = 0.0
    engagement_type: str = "strike"
    priority: float = 1.0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    """Result of evaluating an action or assignment against policy."""

    allowed: bool
    decision: Decision
    action: PolicyAction
    role: Role
    violations: list[str]
    veto: Veto | None = None
    request_id: str | None = None
    cycle_ms: float = 0.0
    auto_approved: bool = False
    budget_exceeded: bool = False
    reason: str = ""


@dataclass
class PolicyEngineConfig:
    """Configuration for :class:`PolicyEngine`."""

    hitl_enabled: bool = True
    veto_authority: str = DEFAULT_VETO_AUTHORITY
    drone_id: int = DEFAULT_DRONE_ID
    cycle_budget_ms: float = AUTO_APPROVE_CYCLE_BUDGET_MS
    high_value_target_threshold: float = HIGH_VALUE_TARGET_THRESHOLD
    auto_approve_when_hitl_disabled: bool = True
    default_policies: dict[PolicyAction, ActionPolicy] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HITL workflow port (duck-typed: submit / approve / reject / get_status)
# ---------------------------------------------------------------------------


@runtime_checkable
class HITLWorkflow(Protocol):
    """Subset of the HITLAdapter/ApprovalWorkflow API used by the engine.

    Attributes/methods:
        submit: Submit an approval request; return it (with an id assigned).
        approve: Approve a pending request.
        reject: Reject a pending request.
        get_status: Return the status of a request.
    """

    def submit(self, request: object) -> object:
        """Submit an approval request; return it (with an id assigned)."""

    def approve(self, request_id: str, approver: str) -> None:
        """Approve a pending request."""

    def reject(self, request_id: str, approver: str, reason: str) -> None:
        """Reject a pending request."""

    def get_status(self, request_id: str) -> object:
        """Return the status of a request."""


# ---------------------------------------------------------------------------
# Default agent-exec policies
# ---------------------------------------------------------------------------


def _default_policies() -> dict[PolicyAction, ActionPolicy]:
    """Built-in agent-exec policies (allowed actions per role, risk, approval)."""

    policies: dict[PolicyAction, ActionPolicy] = {}

    def _policy(
        allowed_roles: set[Role],
        *,
        risk_threshold: RiskLevel = RiskLevel.MEDIUM,
        requires_approval: bool = False,
        max_target_value: float | None = None,
        deny_above_risk: RiskLevel | None = None,
    ) -> ActionPolicy:
        return ActionPolicy(
            allowed_roles=frozenset[Role](allowed_roles),
            risk_threshold=risk_threshold,
            requires_approval=requires_approval,
            max_target_value=max_target_value,
            deny_above_risk=deny_above_risk,
        )

    policies[PolicyAction.ARM] = _policy(
        {Role.OPERATOR, Role.PILOT, Role.AUTONOMOUS_AGENT},
        risk_threshold=RiskLevel.HIGH,
        requires_approval=True,
    )
    policies[PolicyAction.DISARM] = _policy(
        {Role.OPERATOR, Role.PILOT, Role.AUTONOMOUS_AGENT},
        risk_threshold=RiskLevel.HIGH,
        requires_approval=True,
    )
    policies[PolicyAction.SET_MODE] = _policy(
        {Role.OPERATOR, Role.PILOT, Role.AUTONOMOUS_AGENT},
        risk_threshold=RiskLevel.MEDIUM,
        requires_approval=True,
    )
    policies[PolicyAction.SEND_CONTROL] = _policy(
        {Role.OPERATOR, Role.PILOT, Role.AUTONOMOUS_AGENT, Role.SOLVER},
        risk_threshold=RiskLevel.LOW,
        requires_approval=False,
    )
    policies[PolicyAction.TAKEOFF] = _policy(
        {Role.OPERATOR, Role.PILOT, Role.AUTONOMOUS_AGENT},
        risk_threshold=RiskLevel.HIGH,
        requires_approval=True,
    )
    policies[PolicyAction.LAND] = _policy(
        {Role.OPERATOR, Role.PILOT, Role.AUTONOMOUS_AGENT},
        risk_threshold=RiskLevel.MEDIUM,
        requires_approval=False,
    )
    policies[PolicyAction.EMERGENCY_STOP] = _policy(
        {Role.OPERATOR, Role.GOVERNANCE},
        risk_threshold=RiskLevel.CRITICAL,
        requires_approval=False,
    )
    policies[PolicyAction.ENGAGE_TARGET] = _policy(
        {Role.SOLVER, Role.AUTONOMOUS_AGENT, Role.GOVERNANCE},
        risk_threshold=RiskLevel.HIGH,
        requires_approval=True,
    )
    policies[PolicyAction.WTA_ASSIGNMENT] = _policy(
        {Role.SOLVER, Role.AUTONOMOUS_AGENT, Role.GOVERNANCE},
        risk_threshold=RiskLevel.HIGH,
        requires_approval=True,
        deny_above_risk=RiskLevel.CRITICAL,
    )
    return policies


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Evaluate agent-exec actions and WTA assignments against governance policy.

    Args:
        veto_manager: Veto manager used to emit/latch vetoes on violation.
            Defaults to a fresh :class:`VetoManager`.
        hitl: HITL workflow port (``submit``/``approve``/``reject``/
            ``get_status``). Required when ``hitl_enabled`` is true.
        config: Engine configuration.
        clock: Callable returning the current time as a float (seconds).
            Defaults to :func:`time.time`.
    """

    def __init__(
        self,
        *,
        veto_manager: VetoManager | None = None,
        hitl: HITLWorkflow | None = None,
        config: PolicyEngineConfig | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._cfg = config or PolicyEngineConfig()
        self._policies: dict[PolicyAction, ActionPolicy] = {}
        self._policies.update(_default_policies())
        self._policies.update(self._cfg.default_policies or {})
        self._veto_manager = veto_manager or VetoManager()
        self._hitl = hitl
        self._clock = clock
        self._pending: dict[str, PolicyDecision] = {}

        if self._cfg.hitl_enabled and self._hitl is None:
            raise ValueError(
                "hitl workflow is required when HITL is enabled; "
                "disable HITL or pass a HITLWorkflow implementation"
            )

    # -- configuration -----------------------------------------------------

    @property
    def policies(self) -> dict[PolicyAction, ActionPolicy]:
        """Return the action policies (mutable for reconfiguration)."""
        return self._policies

    @property
    def veto_manager(self) -> VetoManager:
        """Return the veto manager used for veto emission."""
        return self._veto_manager

    @property
    def config(self) -> PolicyEngineConfig:
        """Return the engine configuration."""
        return self._cfg

    def set_policy(self, action: PolicyAction, policy: ActionPolicy) -> None:
        """Replace the policy for a single agent-exec action."""
        self._policies[action] = policy

    # -- public API --------------------------------------------------------

    def evaluate_assignment(self, assignment: WTAAssignment, role: Role) -> PolicyDecision:
        """Evaluate a solver WTA assignment before it becomes a setpoint.

        Checks role authorization, risk thresholds (high-value target
        engagement, critical kill probability) and approval requirements.
        On violation a veto is emitted via the veto manager; when HITL is
        enabled and approval is required the assignment is held
        (``PENDING_APPROVAL``, ``SOFT_HOLD`` veto) until :meth:`approve`
        or :meth:`reject` is called. When HITL is disabled the assignment
        is auto-approved (sub-100 ms autonomous cycle).
        """
        start = self._clock()
        action = PolicyAction.WTA_ASSIGNMENT
        policy = self._policies[action]
        violations: list[str] = []
        decision = Decision.ALLOWED
        allowed = True
        veto: Veto | None = None
        request_id: str | None = None
        auto_approved = False

        # 1. Role authorization.
        if role not in policy.allowed_roles:
            violations.append(f"role {role.value} not authorized for {action.value}")
            allowed = False
            decision = Decision.DENIED

        # 2. Risk thresholds.
        risk = self._assignment_risk(assignment)
        if policy.deny_above_risk is not None and risk >= policy.deny_above_risk:
            violations.append(
                f"risk {risk.name} at/above deny threshold {policy.deny_above_risk.name}"
            )
            allowed = False
            decision = Decision.DENIED
        if (
            policy.max_target_value is not None
            and assignment.target_value > policy.max_target_value
        ):
            violations.append(
                f"target value {assignment.target_value} exceeds max {policy.max_target_value}"
            )
            allowed = False
            decision = Decision.DENIED

        # 3. Approval requirement.
        requires_approval = allowed and policy.requires_approval and risk >= policy.risk_threshold
        if requires_approval:
            if self._cfg.hitl_enabled:
                hitl = self._hitl
                assert hitl is not None  # guaranteed by the constructor
                request = self._make_approval_request(assignment, role, risk)
                request.id = request.id or f"pol-{uuid.uuid4().hex[:12]}"
                hitl.submit(request)
                request_id = request.id
                allowed = False
                decision = Decision.PENDING_APPROVAL
                veto = self._emit_veto(
                    VETO_SOFT_HOLD,
                    (
                        f"{action.value} for target {assignment.target_id} "
                        f"(value={assignment.target_value}) awaiting human "
                        f"approval (request {request_id})"
                    ),
                )
            elif self._cfg.auto_approve_when_hitl_disabled:
                # Sub-100 ms autonomous cycle: no human in the loop.
                allowed = True
                decision = Decision.ALLOWED
                auto_approved = True
            else:
                violations.append("approval required but HITL disabled and auto-approve off")
                allowed = False
                decision = Decision.DENIED

        # 4. Emit a denial veto when not already holding for approval.
        if not allowed and veto is None:
            veto_type = VETO_HARD_EMERGENCY if risk >= RiskLevel.CRITICAL else VETO_SOFT_HOLD
            veto = self._emit_veto(
                veto_type,
                violations[-1] if violations else f"policy violation: {action.value}",
            )

        elapsed_ms = (self._clock() - start) * 1000.0
        budget_exceeded = elapsed_ms > self._cfg.cycle_budget_ms
        if budget_exceeded:
            logger.warning(
                "Policy evaluation for %s took %.1f ms (budget %.1f ms)",
                action.value,
                elapsed_ms,
                self._cfg.cycle_budget_ms,
            )

        result = PolicyDecision(
            allowed=allowed,
            decision=decision,
            action=action,
            role=role,
            violations=violations,
            veto=veto,
            request_id=request_id,
            cycle_ms=elapsed_ms,
            auto_approved=auto_approved,
            budget_exceeded=budget_exceeded,
            reason=violations[0] if violations else "",
        )
        if request_id is not None:
            self._pending[request_id] = result
        return result

    def evaluate_action(
        self,
        action: PolicyAction,
        role: Role,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluate a generic agent-exec action against policy.

        ``context`` may carry action-specific details (e.g. throttle) and an
        optional ``risk`` override; otherwise the policy's threshold is used
        as the nominal risk.
        """
        start = self._clock()
        context = context or {}
        policy = self._policies[action]
        violations: list[str] = []
        decision = Decision.ALLOWED
        allowed = True
        veto: Veto | None = None
        request_id: str | None = None
        auto_approved = False

        if role not in policy.allowed_roles:
            violations.append(f"role {role.value} not authorized for {action.value}")
            allowed = False
            decision = Decision.DENIED

        risk = context.get("risk", policy.risk_threshold)
        if (
            policy.deny_above_risk is not None
            and isinstance(risk, RiskLevel)
            and risk >= policy.deny_above_risk
        ):
            violations.append(
                f"risk {risk.name} at/above deny threshold {policy.deny_above_risk.name}"
            )
            allowed = False
            decision = Decision.DENIED

        requires_approval = (
            allowed
            and action not in _IMMEDIATE_ACTIONS
            and policy.requires_approval
            and isinstance(risk, RiskLevel)
            and risk >= policy.risk_threshold
        )
        if requires_approval:
            if self._cfg.hitl_enabled:
                hitl = self._hitl
                assert hitl is not None  # guaranteed by the constructor
                request = self._make_approval_request_for_action(action, role, risk)
                request.id = request.id or f"pol-{uuid.uuid4().hex[:12]}"
                hitl.submit(request)
                request_id = request.id
                allowed = False
                decision = Decision.PENDING_APPROVAL
                veto = self._emit_veto(
                    VETO_SOFT_HOLD,
                    f"{action.value} awaiting human approval (request {request_id})",
                )
            elif self._cfg.auto_approve_when_hitl_disabled:
                allowed = True
                decision = Decision.ALLOWED
                auto_approved = True
            else:
                violations.append("approval required but HITL disabled and auto-approve off")
                allowed = False
                decision = Decision.DENIED

        if not allowed and veto is None:
            veto_type = VETO_HARD_EMERGENCY if risk >= RiskLevel.CRITICAL else VETO_SOFT_HOLD
            veto = self._emit_veto(
                veto_type,
                violations[-1] if violations else f"policy violation: {action.value}",
            )

        elapsed_ms = (self._clock() - start) * 1000.0
        budget_exceeded = elapsed_ms > self._cfg.cycle_budget_ms

        result = PolicyDecision(
            allowed=allowed,
            decision=decision,
            action=action,
            role=role,
            violations=violations,
            veto=veto,
            request_id=request_id,
            cycle_ms=elapsed_ms,
            auto_approved=auto_approved,
            budget_exceeded=budget_exceeded,
            reason=violations[0] if violations else "",
        )
        if request_id is not None:
            self._pending[request_id] = result
        return result

    def approve(self, request_id: str, approver: str = "operator") -> PolicyDecision:
        """Approve a pending approval request and release its veto.

        Delegates to the HITL workflow's ``approve`` and issues a
        ``CLEAR`` veto so setpoints can flow again.
        """
        if request_id not in self._pending:
            raise KeyError(f"no pending decision for request '{request_id}'")
        decision = self._pending[request_id]
        hitl = self._hitl
        assert hitl is not None
        hitl.approve(request_id, approver=approver)
        decision.allowed = True
        decision.decision = Decision.ALLOWED
        decision.reason = ""
        self._emit_veto(VETO_CLEAR, f"approved by {approver} (request {request_id})")
        del self._pending[request_id]
        return decision

    def reject(
        self, request_id: str, approver: str = "operator", reason: str = "rejected"
    ) -> PolicyDecision:
        """Reject a pending approval request; its veto stays latched.

        Delegates to the HITL workflow's ``reject``.
        """
        if request_id not in self._pending:
            raise KeyError(f"no pending decision for request '{request_id}'")
        decision = self._pending[request_id]
        hitl = self._hitl
        assert hitl is not None
        hitl.reject(request_id, approver=approver, reason=reason)
        decision.allowed = False
        decision.decision = Decision.DENIED
        decision.reason = reason
        del self._pending[request_id]
        return decision

    def clear_veto(self, authority: str) -> bool:
        """Ask the veto manager to clear the active veto by ``authority``."""
        return self._veto_manager.clear(authority)

    def active_veto(self) -> Veto | None:
        """Return the currently active veto, if any."""
        return self._veto_manager.active()

    # -- internals ---------------------------------------------------------

    def _assignment_risk(self, assignment: WTAAssignment) -> RiskLevel:
        """Assess the risk of a WTA assignment."""
        if assignment.kill_probability >= HIGH_KILL_PROBABILITY:
            return RiskLevel.CRITICAL
        if assignment.target_value >= self._cfg.high_value_target_threshold:
            return RiskLevel.HIGH
        if assignment.kill_probability >= 0.7:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _make_approval_request(self, assignment: WTAAssignment, role: Role, risk: RiskLevel) -> Any:
        """Build an approval request for a WTA assignment."""
        from types import SimpleNamespace

        return SimpleNamespace(
            id="",
            action=PolicyAction.WTA_ASSIGNMENT.value,
            requester=role.value,
            context={
                "assignment_id": assignment.assignment_id,
                "weapon_id": assignment.weapon_id,
                "target_id": assignment.target_id,
                "target_value": assignment.target_value,
                "kill_probability": assignment.kill_probability,
                "engagement_type": assignment.engagement_type,
                "priority": assignment.priority,
            },
            priority="high" if risk >= RiskLevel.HIGH else "medium",
            created_at=self._clock(),
            expires_at=self._clock() + self._cfg.cycle_budget_ms / 1000.0 * 60.0,
        )

    def _make_approval_request_for_action(
        self, action: PolicyAction, role: Role, risk: RiskLevel
    ) -> Any:
        """Build an approval request for a generic agent-exec action."""
        from types import SimpleNamespace

        return SimpleNamespace(
            id="",
            action=action.value,
            requester=role.value,
            context={},
            priority="high" if risk >= RiskLevel.HIGH else "medium",
            created_at=self._clock(),
            expires_at=self._clock() + self._cfg.cycle_budget_ms / 1000.0 * 60.0,
        )

    def _emit_veto(self, veto_type: int, reason: str) -> Veto:
        """Issue a veto through the veto manager and return the active veto."""
        veto = Veto(
            drone_id=self._cfg.drone_id,
            veto_type=veto_type,
            severity=_SEVERITY_BY_VETO_TYPE.get(int(veto_type), 1),
            reason=reason,
            authority=self._cfg.veto_authority,
        )
        active = self._veto_manager.issue(veto)
        return active if active is not None else veto
