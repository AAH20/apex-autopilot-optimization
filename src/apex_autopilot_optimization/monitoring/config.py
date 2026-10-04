"""Monitoring configuration for apex-autopilot-optimization.

Provides configuration dataclass for monitoring, alerting,
Prometheus, Grafana, and Alertmanager settings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MonitoringConfig:
    """Monitoring and alerting configuration.

    Attributes:
        prometheus_enabled: Whether Prometheus metrics collection is enabled.
        grafana_enabled: Whether Grafana dashboards are enabled.
        alertmanager_enabled: Whether Alertmanager alerting is enabled.
        scrape_interval: Prometheus scrape interval.
        retention_period: Metrics retention period.
    """

    prometheus_enabled: bool = True
    grafana_enabled: bool = True
    alertmanager_enabled: bool = True
    scrape_interval: str = "15s"
    retention_period: str = "30d"
