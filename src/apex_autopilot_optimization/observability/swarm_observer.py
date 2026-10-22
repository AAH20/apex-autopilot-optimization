"""Swarm health observer.

Wraps SwarmRunner, CombatReallocator, CBFFilter and PolicyEngine to collect
RED metrics (Rate, Errors, Duration) and swarm-health signals (vehicle count,
active vetoes, CBF violations, WTA solve latency, formation deviation) into
the Prometheus metrics registry. All public methods are thread-safe.
"""

from __future__ import annotations

import time
from typing import Any

from apex_autopilot_optimization.observability.metrics import (
    DEFAULT_REGISTRY,
    MetricsRegistry,
)


class SwarmObserver:
    """Observes a running swarm and exports RED metrics + health signals.

    Instruments:
    - SwarmRunner: connect/arm/step/disconnect counts, cycle latency, violations
    - CombatReallocator: reallocation events, veto emissions, BDA loop iterations
    - CBFFilter: filter decisions, corrections applied, safety violations
    - PolicyEngine: policy evaluations, auto-approvals, HITL referrals
    """

    def __init__(self, registry: MetricsRegistry | None = None) -> None:
        self._registry = registry or DEFAULT_REGISTRY

    # -- SwarmRunner instrumentation ---------------------------------------
    def record_swarm_cycle(
        self,
        vehicle_count: int,
        cycle_ms: float,
        violations: int = 0,
        connected: int | None = None,
        makespan_s: float | None = None,
    ) -> None:
        """Record one SwarmRunner cycle."""
        r = self._registry
        r.gauge("swarm_vehicles", float(vehicle_count))
        r.observe("swarm_cycle_duration_ms", cycle_ms)
        r.inc("swarm_cycles_total", 1.0)
        r.inc("swarm_violations_total", float(violations))
        if connected is not None:
            r.gauge("swarm_connected_vehicles", float(connected))
        if makespan_s is not None:
            r.observe("swarm_makespan_seconds", makespan_s)

    def record_swarm_connect(self, slot: int) -> None:
        """Record a vehicle connecting."""
        self._registry.inc("swarm_connect_total", 1.0, slot=str(slot))

    def record_swarm_disconnect(self, slot: int) -> None:
        """Record a vehicle disconnecting."""
        self._registry.inc("swarm_disconnect_total", 1.0, slot=str(slot))

    # -- CombatReallocator instrumentation ---------------------------------
    def record_reallocation(
        self,
        event: str,
        weapons: int,
        targets: int,
        assignments: int,
        vetoed: bool = False,
        solve_ms: float | None = None,
    ) -> None:
        """Record a CombatReallocator reallocation event."""
        r = self._registry
        r.inc("combat_reallocations_total", 1.0, event=event)
        r.gauge("combat_weapons", float(weapons))
        r.gauge("combat_targets", float(targets))
        r.gauge("combat_assignments", float(assignments))
        if vetoed:
            r.inc("combat_vetoed_total", 1.0)
        if solve_ms is not None:
            r.observe("combat_reallocate_duration_ms", solve_ms)

    # -- CBFFilter instrumentation -----------------------------------------
    def record_cbf_decision(
        self,
        applied: bool,
        correction_ms: float,
        violation: bool = False,
        obstacle_count: int = 0,
    ) -> None:
        """Record one CBF filter decision."""
        r = self._registry
        r.inc("cbf_decisions_total", 1.0)
        if applied:
            r.inc("cbf_corrections_applied_total", 1.0)
        if violation:
            r.inc("cbf_violations_total", 1.0)
        r.observe("cbf_correction_duration_ms", correction_ms)
        r.gauge("cbf_obstacle_count", float(obstacle_count))

    # -- PolicyEngine instrumentation --------------------------------------
    def record_policy_evaluation(
        self,
        action: str,
        allowed: bool,
        auto_approved: bool = False,
        hitl_referral: bool = False,
        eval_ms: float | None = None,
    ) -> None:
        """Record one PolicyEngine evaluation."""
        r = self._registry
        r.inc("policy_evaluations_total", 1.0, action=action)
        if not allowed:
            r.inc("policy_denied_total", 1.0, action=action)
        if auto_approved:
            r.inc("policy_auto_approved_total", 1.0, action=action)
        if hitl_referral:
            r.inc("policy_hitl_referrals_total", 1.0, action=action)
        if eval_ms is not None:
            r.observe("policy_evaluation_duration_ms", eval_ms)

    # -- Health snapshot ---------------------------------------------------
    def health_snapshot(self) -> dict[str, Any]:
        """Return a point-in-time health snapshot of all observed signals."""
        samples = self._registry.get_samples()
        return {
            "timestamp": time.time(),
            "metrics_count": len(samples),
            "samples": [
                {
                    "name": s.name,
                    "type": s.type,
                    "value": s.value,
                    "labels": s.labels,
                }
                for s in samples
            ],
        }
