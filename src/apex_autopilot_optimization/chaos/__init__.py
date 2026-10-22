"""Chaos engineering and fault injection for resilience testing."""

from apex_autopilot_optimization.chaos.config import ChaosConfig
from apex_autopilot_optimization.chaos.experiment import (
    ChaosExperiment,
    ChaosRunReport,
    TrialResult,
)
from apex_autopilot_optimization.chaos.faults import (
    FaultSchedule,
    FaultSpec,
    FaultType,
    Severity,
)
from apex_autopilot_optimization.chaos.injector import FaultInjector
from apex_autopilot_optimization.chaos.probes import (
    cbf_correction_when_unsafe,
    cbf_output_valid,
    cbf_throttle_monotonic,
    combat_no_clique_violation,
    combat_no_infeasible_assignment,
    combat_no_killed_reengaged,
    combat_state_machine_legal,
    policy_critical_vetoed,
    policy_high_value_not_allowed,
    policy_unauthorized_denied,
    veto_authority_chain_respected,
)
from apex_autopilot_optimization.chaos.result import ChaosResult
from apex_autopilot_optimization.chaos.runtime import (
    BEHAVIORS,
    RuntimeFaultInjector,
    fault_scope,
    inject_fault_behavior,
)

__all__ = [
    "ChaosConfig",
    "ChaosExperiment",
    "ChaosRunReport",
    "ChaosResult",
    "FaultInjector",
    "FaultSchedule",
    "FaultSpec",
    "FaultType",
    "RuntimeFaultInjector",
    "Severity",
    "TrialResult",
    "BEHAVIORS",
    "fault_scope",
    "inject_fault_behavior",
    "combat_no_clique_violation",
    "combat_no_infeasible_assignment",
    "combat_no_killed_reengaged",
    "combat_state_machine_legal",
    "cbf_correction_when_unsafe",
    "cbf_output_valid",
    "cbf_throttle_monotonic",
    "policy_critical_vetoed",
    "policy_high_value_not_allowed",
    "policy_unauthorized_denied",
    "veto_authority_chain_respected",
]
