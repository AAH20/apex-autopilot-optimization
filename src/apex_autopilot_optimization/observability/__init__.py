"""Observability package for apex-autopilot-optimization.

Builds on top of the tracing/ module (distributed tracing) and the
top-level observability.py (structured logging, metrics, health checks)
to provide a production-grade observability surface: Prometheus text-format
metrics endpoint, swarm health observer, alert rules, and Grafana dashboard
definitions.
"""

from apex_autopilot_optimization.observability._legacy import (
    HealthCheck,
    MetricCollector,
    ObservabilityConfig,
    ObservabilityManager,
    StructuredLogger,
    check_health,
    collect_metrics,
    create_logger,
    format_metric,
)
from apex_autopilot_optimization.observability.alerts import DEFAULT_ALERT_RULES, AlertRule
from apex_autopilot_optimization.observability.metrics import (
    CONTENT_TYPE,
    MetricsRegistry,
    generate_latest,
)
from apex_autopilot_optimization.observability.swarm_observer import SwarmObserver

__all__ = [
    "AlertRule",
    "CONTENT_TYPE",
    "DEFAULT_ALERT_RULES",
    "HealthCheck",
    "MetricCollector",
    "MetricsRegistry",
    "ObservabilityConfig",
    "ObservabilityManager",
    "SwarmObserver",
    "StructuredLogger",
    "check_health",
    "collect_metrics",
    "create_logger",
    "format_metric",
    "generate_latest",
]
