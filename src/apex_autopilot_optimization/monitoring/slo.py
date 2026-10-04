"""SLO (Service Level Objective) module for apex-autopilot-optimization.

Provides SLO definitions, SLO checking against metrics, status
reporting, and error budget calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SLODefinition:
    """Service Level Objective definition.

    Attributes:
        name: SLO name (e.g., "availability").
        target: Target success ratio (0.0 to 1.0).
        window: SLO evaluation window (e.g., "30d").
        burn_rate_threshold: Maximum acceptable burn rate multiplier.
    """

    name: str
    target: float
    window: str
    burn_rate_threshold: float


def check_slo(slo: SLODefinition, metrics: dict[str, Any]) -> bool:
    """Check if an SLO is being met.

    The SLO metric value is looked up by the SLO name. The SLO passes
    if the metric value meets or exceeds the target.

    Args:
        slo: The SLO definition.
        metrics: Current metric values keyed by name.

    Returns:
        True if the SLO is met, False otherwise.
    """
    metric_value = metrics.get(slo.name)

    if metric_value is None:
        return False

    try:
        value = float(metric_value)
    except (TypeError, ValueError):
        return False

    return value >= slo.target


def get_slo_status(slo: SLODefinition, metrics: dict[str, Any]) -> dict[str, Any]:
    """Get detailed SLO status.

    Args:
        slo: The SLO definition.
        metrics: Current metric values keyed by name.

    Returns:
        Dictionary with SLO status information.
    """
    metric_value = metrics.get(slo.name)
    passing = check_slo(slo, metrics)

    return {
        "name": slo.name,
        "status": "passing" if passing else "failing",
        "target": slo.target,
        "current": metric_value,
        "window": slo.window,
    }


def get_error_budget(slo: SLODefinition, metrics: dict[str, Any]) -> float:
    """Calculate remaining error budget.

    Error budget = (actual - target) / (1 - target)
    Positive means budget remaining, negative means budget exhausted.

    Args:
        slo: The SLO definition.
        metrics: Current metric values keyed by name.

    Returns:
        Error budget as a ratio. Positive = budget remaining.
    """
    metric_value = metrics.get(slo.name)

    if metric_value is None:
        return -1.0

    try:
        value = float(metric_value)
    except (TypeError, ValueError):
        return -1.0

    # Error budget: how much error we can still tolerate
    # budget = (actual - target) / (1 - target)
    # If actual == target, budget = 0
    # If actual > target, budget > 0 (remaining)
    # If actual < target, budget < 0 (exhausted)
    denominator = 1.0 - slo.target
    if denominator == 0:
        return 0.0 if value >= slo.target else -1.0

    return (value - slo.target) / denominator
