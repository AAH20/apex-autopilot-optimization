"""Safety invariant probes for adversarial and chaos verification.

Each probe receives component inputs/outputs and returns a list of
violation strings.  An empty list means the invariant holds.  Probes are
pure functions of observed data, so they can be used in unit tests,
property-based tests, and chaos experiment assertions alike.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from apex_autopilot_optimization.core.types import ControlInput
from apex_autopilot_optimization.governance.policy_engine import PolicyDecision
from apex_autopilot_optimization.messaging.veto_manager import (
    AUTHORITY_RANK,
    VETO_HARD_EMERGENCY,
)

__all__ = [
    "cbf_throttle_monotonic",
    "cbf_output_valid",
    "cbf_correction_when_unsafe",
    "combat_no_infeasible_assignment",
    "combat_no_clique_violation",
    "combat_no_killed_reengaged",
    "combat_state_machine_legal",
    "policy_unauthorized_denied",
    "policy_critical_vetoed",
    "policy_high_value_not_allowed",
    "veto_authority_chain_respected",
]


# --------------------------------------------------------------------------- #
# CBF probes
# --------------------------------------------------------------------------- #


def cbf_throttle_monotonic(control_in: ControlInput, control_out: ControlInput) -> list[str]:
    """Throttle correction must never increase throttle or go negative."""
    violations: list[str] = []
    if control_out.throttle < 0.0:
        violations.append(f"negative throttle {control_out.throttle:.4f}")
    if control_out.throttle > control_in.throttle + 1e-9:
        violations.append(
            f"throttle increased {control_in.throttle:.4f} -> {control_out.throttle:.4f}"
        )
    return violations


def cbf_output_valid(control_in: ControlInput, control_out: ControlInput) -> list[str]:
    """Output must preserve roll/pitch/yaw/timestamp (only throttle changes)."""
    violations: list[str] = []
    if control_out.roll_rate != control_in.roll_rate:
        violations.append("roll_rate modified by CBF throttle correction")
    if control_out.pitch_rate != control_in.pitch_rate:
        violations.append("pitch_rate modified by CBF throttle correction")
    if control_out.yaw_rate != control_in.yaw_rate:
        violations.append("yaw_rate modified by CBF throttle correction")
    if control_out.timestamp != control_in.timestamp:
        violations.append("timestamp modified by CBF throttle correction")
    return violations


def cbf_correction_when_unsafe(
    min_distance: float,
    safety_margin: float,
    control_in: ControlInput,
    control_out: ControlInput,
) -> list[str]:
    """Inside the safety margin, throttle must be reduced (h <= 0)."""
    violations: list[str] = []
    if min_distance <= safety_margin and control_out.throttle >= control_in.throttle - 1e-9:
        violations.append(
            f"unsafe (dist={min_distance:.3f} <= margin={safety_margin:.3f}) "
            f"but throttle not reduced {control_in.throttle:.3f} -> {control_out.throttle:.3f}"
        )
    return violations


# --------------------------------------------------------------------------- #
# Combat reallocator probes
# --------------------------------------------------------------------------- #


def combat_no_infeasible_assignment(
    engagements: list[tuple[int, int]],
    time_feasible: np.ndarray,
    weapon_ids: list[int],
    target_ids: list[int],
) -> list[str]:
    """No engagement may use a time-infeasible weapon-target pair."""
    violations: list[str] = []
    wid_to_i = {wid: i for i, wid in enumerate(weapon_ids)}
    tid_to_j = {tid: j for j, tid in enumerate(target_ids)}
    for wid, tid in engagements:
        i = wid_to_i.get(wid)
        j = tid_to_j.get(tid)
        if i is None or j is None:
            violations.append(f"engagement ({wid},{tid}) references unknown weapon/target")
            continue
        if not bool(time_feasible[i, j]):
            violations.append(f"infeasible pair assigned ({wid},{tid})")
    return violations


def combat_no_clique_violation(
    engagements: list[tuple[int, int]], cliques: list[list[tuple[int, int]]]
) -> list[str]:
    """At most one pair from each interference clique may be assigned."""
    violations: list[str] = []
    engaged = set(engagements)
    for clique in cliques:
        assigned = [tuple(pair) for pair in clique if tuple(pair) in engaged]
        if len(assigned) > 1:
            violations.append(f"clique violated: {assigned} assigned")
    return violations


def combat_no_killed_reengaged(
    engagements: list[tuple[int, int]],
    killed_target_ids: list[int],
) -> list[str]:
    """A killed target must never be re-engaged in a later cycle."""
    violations: list[str] = []
    killed = set(killed_target_ids)
    for wid, tid in engagements:
        if tid in killed:
            violations.append(f"killed target {tid} re-engaged by weapon {wid}")
    return violations


def combat_state_machine_legal(cr: Any) -> list[str]:
    """Every logged event must be a legal transition from the current state."""
    violations: list[str] = []
    from apex_autopilot_optimization.swarm.wta_solver import SolverState

    transitions = {
        SolverState.IDLE: {"allocate_request", "reset", "abort"},
        SolverState.ALLOCATING: {"solution_ready", "reset", "abort"},
        SolverState.ENGAGING: {"bda_received", "salvo_complete", "reset", "abort"},
        SolverState.LOOKING: {
            "all_neutralized",
            "weapons_exhausted",
            "residual_instance_ready",
            "reset",
            "abort",
        },
        SolverState.RE_EVALUATING: {"residual_instance_ready", "reset", "abort"},
        SolverState.TERMINAL: {"reset", "abort"},
    }
    dest = {
        (SolverState.IDLE, "allocate_request"): SolverState.ALLOCATING,
        (SolverState.IDLE, "reset"): SolverState.IDLE,
        (SolverState.IDLE, "abort"): SolverState.IDLE,
        (SolverState.ALLOCATING, "solution_ready"): SolverState.ENGAGING,
        (SolverState.ALLOCATING, "reset"): SolverState.IDLE,
        (SolverState.ALLOCATING, "abort"): SolverState.IDLE,
        (SolverState.ENGAGING, "bda_received"): SolverState.LOOKING,
        (SolverState.ENGAGING, "salvo_complete"): SolverState.LOOKING,
        (SolverState.ENGAGING, "reset"): SolverState.IDLE,
        (SolverState.ENGAGING, "abort"): SolverState.IDLE,
        (SolverState.LOOKING, "all_neutralized"): SolverState.TERMINAL,
        (SolverState.LOOKING, "weapons_exhausted"): SolverState.TERMINAL,
        (SolverState.LOOKING, "residual_instance_ready"): SolverState.RE_EVALUATING,
        (SolverState.LOOKING, "reset"): SolverState.IDLE,
        (SolverState.LOOKING, "abort"): SolverState.IDLE,
        (SolverState.RE_EVALUATING, "residual_instance_ready"): SolverState.ALLOCATING,
        (SolverState.RE_EVALUATING, "reset"): SolverState.IDLE,
        (SolverState.RE_EVALUATING, "abort"): SolverState.IDLE,
        (SolverState.TERMINAL, "reset"): SolverState.IDLE,
        (SolverState.TERMINAL, "abort"): SolverState.IDLE,
    }
    state = SolverState.IDLE
    for idx, event in enumerate(cr.event_log):
        allowed = transitions.get(state, set())
        if event not in allowed:
            violations.append(f"event #{idx} '{event}' illegal in state {state.name}")
            break
        state = dest[(state, event)]
    return violations


# --------------------------------------------------------------------------- #
# Policy engine probes
# --------------------------------------------------------------------------- #


def policy_unauthorized_denied(
    decision: PolicyDecision, allowed_roles: frozenset[str]
) -> list[str]:
    """A role not in the action's allowed_roles must always be denied."""
    violations: list[str] = []
    if decision.role not in allowed_roles and (decision.allowed or decision.decision != "denied"):
        violations.append(
            f"unauthorized role {decision.role.value} was allowed for {decision.action.value}"
        )
    return violations


def policy_critical_vetoed(decision: PolicyDecision) -> list[str]:
    """CRITICAL-risk decisions must always be denied with HARD_EMERGENCY veto."""
    violations: list[str] = []
    if decision.allowed or decision.decision != "denied":
        return violations
    veto = decision.veto
    if veto is None or veto.veto_type != VETO_HARD_EMERGENCY:
        violations.append("critical risk not vetoed with HARD_EMERGENCY")
    return violations


def policy_high_value_not_allowed(
    decision: PolicyDecision, target_value: float, threshold: float, hitl_enabled: bool
) -> list[str]:
    """Above-threshold target value must never be allowed outright (HITL on)."""
    violations: list[str] = []
    if not hitl_enabled:
        return violations
    if target_value > threshold and decision.allowed and decision.decision == "allowed":
        violations.append(
            f"high-value target {target_value} allowed without approval (threshold={threshold})"
        )
    return violations


def veto_authority_chain_respected(
    clearing_authority: str, veto_authority: str, expect_cleared: bool
) -> list[str]:
    """Authority chain: only same-or-higher authority may clear a veto."""
    violations: list[str] = []
    rank = AUTHORITY_RANK.get(clearing_authority, 0)
    issuing_rank = AUTHORITY_RANK.get(veto_authority, 0)
    can_clear = clearing_authority == "apex/governance" or rank >= issuing_rank
    if can_clear and not expect_cleared:
        violations.append(f"{clearing_authority} should clear {veto_authority}'s veto")
    if not can_clear and expect_cleared:
        violations.append(f"{clearing_authority} should not clear {veto_authority}'s veto")
    return violations
