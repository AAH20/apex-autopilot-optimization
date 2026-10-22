"""Alert rules for swarm observability.

Defines threshold-based alert rules over Prometheus metrics exported by the
SwarmObserver. Each rule has a name, metric, threshold, comparison operator,
severity, and an optional duration (how long the condition must hold before
firing).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AlertRule:
    """A single threshold-based alert rule.

    Attributes:
        name: Human-readable rule name.
        metric: Prometheus metric name to evaluate.
        threshold: Threshold value.
        comparison: One of "gt", "lt", "eq", "gte", "lte".
        severity: One of "info", "warning", "critical", "page".
        duration_s: How long (seconds) the condition must hold before firing.
        labels: Additional labels to attach to fired alerts.
    """

    name: str
    metric: str
    threshold: float
    comparison: str = "gt"
    severity: str = "warning"
    duration_s: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)


#: Default alert rules for the swarm stack. These mirror the SLOs in
#: CI_GATES.md (perception p95 < 100 ms, WTA p95 < 50 ms, end-to-end < 100 ms)
#: plus operational thresholds for 100-vehicle scale.
DEFAULT_ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="SwarmCycleHighLatency",
        metric="swarm_cycle_duration_ms",
        threshold=100.0,
        comparison="gt",
        severity="critical",
        duration_s=30.0,
        labels={"slo": "end_to_end_100ms"},
    ),
    AlertRule(
        name="SwarmCycleWarningLatency",
        metric="swarm_cycle_duration_ms",
        threshold=75.0,
        comparison="gt",
        severity="warning",
        duration_s=30.0,
        labels={"slo": "end_to_end_100ms"},
    ),
    AlertRule(
        name="SwarmViolationDetected",
        metric="swarm_violations_total",
        threshold=0.0,
        comparison="gt",
        severity="critical",
        duration_s=0.0,
        labels={"slo": "safety_zero_violations"},
    ),
    AlertRule(
        name="SwarmDisconnectRate",
        metric="swarm_disconnect_total",
        threshold=5.0,
        comparison="gt",
        severity="warning",
        duration_s=60.0,
        labels={"component": "swarm_runner"},
    ),
    AlertRule(
        name="CBFCorrectionHighLatency",
        metric="cbf_correction_duration_ms",
        threshold=20.0,
        comparison="gt",
        severity="warning",
        duration_s=30.0,
        labels={"slo": "cbf_filter_latency"},
    ),
    AlertRule(
        name="CBFViolationDetected",
        metric="cbf_violations_total",
        threshold=0.0,
        comparison="gt",
        severity="critical",
        duration_s=0.0,
        labels={"slo": "safety_zero_violations"},
    ),
    AlertRule(
        name="CombatReallocateHighLatency",
        metric="combat_reallocate_duration_ms",
        threshold=50.0,
        comparison="gt",
        severity="warning",
        duration_s=30.0,
        labels={"slo": "wta_50ms"},
    ),
    AlertRule(
        name="PolicyDenialRate",
        metric="policy_denied_total",
        threshold=10.0,
        comparison="gt",
        severity="warning",
        duration_s=60.0,
        labels={"component": "policy_engine"},
    ),
    AlertRule(
        name="SwarmConnectedLow",
        metric="swarm_connected_vehicles",
        threshold=1.0,
        comparison="lt",
        severity="critical",
        duration_s=15.0,
        labels={"component": "swarm_runner"},
    ),
)
