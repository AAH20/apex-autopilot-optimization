"""Grafana dashboard module for apex-autopilot-optimization.

Provides Grafana dashboard generation from monitoring configuration
and panel query extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apex_autopilot_optimization.monitoring.config import MonitoringConfig


@dataclass
class GrafanaDashboard:
    """Grafana dashboard definition.

    Attributes:
        title: Dashboard title.
        panels: List of panel configuration dictionaries.
        datasource: Grafana datasource name.
        refresh: Dashboard auto-refresh interval.
    """

    title: str
    panels: list[dict[str, Any]] = field(default_factory=list)
    datasource: str = "prometheus"
    refresh: str = "30s"


def generate_dashboard(config: MonitoringConfig) -> dict[str, Any]:
    """Generate a Grafana dashboard JSON from monitoring configuration.

    Args:
        config: Monitoring configuration.

    Returns:
        Grafana dashboard JSON dictionary.
    """
    panels: list[dict[str, Any]] = []

    if config.prometheus_enabled:
        panels.append(
            {
                "title": "Request Rate",
                "type": "graph",
                "targets": [{"expr": "rate(requests_total[5m])"}],
            }
        )
        panels.append(
            {
                "title": "Error Rate",
                "type": "graph",
                "targets": [{"expr": "rate(errors_total[5m])"}],
            }
        )
        panels.append(
            {
                "title": "CPU Usage",
                "type": "gauge",
                "targets": [{"expr": "cpu_usage"}],
            }
        )
        panels.append(
            {
                "title": "Memory Usage",
                "type": "gauge",
                "targets": [{"expr": "memory_usage"}],
            }
        )

    if config.alertmanager_enabled:
        panels.append(
            {
                "title": "Active Alerts",
                "type": "table",
                "targets": [{"expr": "ALERTS"}],
            }
        )

    return {
        "title": "Apex Autopilot Optimization",
        "panels": panels,
        "datasource": "prometheus",
        "refresh": config.scrape_interval,
    }


def get_panel_queries(panels: list[dict[str, Any]]) -> list[str]:
    """Extract PromQL queries from dashboard panels.

    Args:
        panels: List of panel configuration dictionaries.

    Returns:
        List of PromQL query expressions.
    """
    queries: list[str] = []
    for panel in panels:
        targets = panel.get("targets", [])
        for target in targets:
            expr = target.get("expr")
            if expr:
                queries.append(expr)
    return queries
