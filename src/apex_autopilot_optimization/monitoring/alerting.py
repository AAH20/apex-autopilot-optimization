"""Alerting module for apex-autopilot-optimization.

Provides alert rule definitions, alert checking against metrics,
and active alert tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AlertSeverity(Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class AlertRule:
    """Alert rule definition.

    Attributes:
        name: Unique alert rule name.
        condition: Human-readable condition expression.
        threshold: Numeric threshold for the condition.
        duration: How long the condition must hold before firing.
        severity: Alert severity level.
        summary: Human-readable alert summary.
    """

    name: str
    condition: str
    threshold: float
    duration: str
    severity: str
    summary: str


# Module-level active alerts store
_active_alerts: list[str] = []


def check_alert(rule: AlertRule, metrics: dict[str, Any]) -> bool:
    """Check if an alert rule fires against current metrics.

    The condition is evaluated by checking if any metric value
    exceeds the rule's threshold. The metric name is derived from
    the condition (first token before the comparison operator).

    Args:
        rule: The alert rule to check.
        metrics: Current metric values keyed by name.

    Returns:
        True if the alert fires, False otherwise.
    """
    # Extract metric name from condition (e.g., "cpu_usage > threshold" -> "cpu_usage")
    condition_parts = rule.condition.split()
    if not condition_parts:
        return False

    metric_name = condition_parts[0]
    metric_value = metrics.get(metric_name)

    if metric_value is None:
        return False

    try:
        value = float(metric_value)
    except (TypeError, ValueError):
        return False

    # Check if value exceeds threshold
    fires = value > rule.threshold

    if fires and rule.name not in _active_alerts:
        _active_alerts.append(rule.name)

    return fires


def get_active_alerts() -> list[str]:
    """Get names of currently active (firing) alerts.

    Returns:
        List of active alert rule names.
    """
    return list(_active_alerts)


def clear_alerts() -> None:
    """Clear all active alerts."""
    _active_alerts.clear()
