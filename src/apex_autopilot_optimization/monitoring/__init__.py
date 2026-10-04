"""Monitoring and alerting package for apex-autopilot-optimization.

Provides Prometheus metrics export, alerting rules, SLO definitions,
Grafana dashboard generation, and monitoring configuration.
"""

from __future__ import annotations

from apex_autopilot_optimization.monitoring.alerting import (
    AlertRule,
    AlertSeverity,
    check_alert,
    clear_alerts,
    get_active_alerts,
)
from apex_autopilot_optimization.monitoring.config import MonitoringConfig
from apex_autopilot_optimization.monitoring.grafana import (
    GrafanaDashboard,
    generate_dashboard,
    get_panel_queries,
)
from apex_autopilot_optimization.monitoring.prometheus import PrometheusExporter
from apex_autopilot_optimization.monitoring.slo import (
    SLODefinition,
    check_slo,
    get_error_budget,
    get_slo_status,
)

__all__ = [
    "AlertRule",
    "AlertSeverity",
    "GrafanaDashboard",
    "MonitoringConfig",
    "PrometheusExporter",
    "SLODefinition",
    "check_alert",
    "check_slo",
    "clear_alerts",
    "generate_dashboard",
    "get_active_alerts",
    "get_error_budget",
    "get_panel_queries",
    "get_slo_status",
]
