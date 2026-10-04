"""Tests for monitoring and alerting package."""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.monitoring import (
    AlertRule,
    AlertSeverity,
    GrafanaDashboard,
    MonitoringConfig,
    PrometheusExporter,
    SLODefinition,
    check_alert,
    check_slo,
    clear_alerts,
    generate_dashboard,
    get_active_alerts,
    get_error_budget,
    get_panel_queries,
    get_slo_status,
)


# ── Prometheus metric registration ─────────────────────────────────────────


class TestPrometheusMetricRegistration:
    """Tests for Prometheus metric registration."""

    def test_register_single_metric(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 10.0, "counter")
        assert "requests_total" in exporter.get_metric_names()

    def test_register_multiple_metrics(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 10.0, "counter")
        exporter.register_metric("cpu_usage", 0.75, "gauge")
        exporter.register_metric("latency_seconds", 0.05, "histogram")
        assert len(exporter.get_metric_names()) == 3

    def test_register_metric_with_labels(self):
        exporter = PrometheusExporter()
        exporter.register_metric(
            "requests_total", 10.0, "counter", labels={"method": "GET", "status": "200"}
        )
        assert "requests_total" in exporter.get_metric_names()

    def test_register_metric_overwrites_value(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 10.0, "counter")
        exporter.register_metric("requests_total", 20.0, "counter")
        assert exporter.get_metric_value("requests_total") == 20.0
        assert len(exporter.get_metric_names()) == 1

    def test_register_metric_preserves_type(self):
        exporter = PrometheusExporter()
        exporter.register_metric("cpu_usage", 0.5, "gauge")
        metrics = exporter.get_metrics()
        assert "cpu_usage" in metrics


# ── Prometheus metrics export ───────────────────────────────────────────────


class TestPrometheusMetricsExport:
    """Tests for Prometheus metrics export."""

    def test_get_metrics_returns_string(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 10.0, "counter")
        result = exporter.get_metrics()
        assert isinstance(result, str)

    def test_get_metrics_contains_metric_name(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 10.0, "counter")
        assert "requests_total" in exporter.get_metrics()

    def test_get_metrics_contains_metric_value(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 42.0, "counter")
        assert "42" in exporter.get_metrics()

    def test_get_metrics_empty_exporter(self):
        exporter = PrometheusExporter()
        result = exporter.get_metrics()
        assert isinstance(result, str)

    def test_get_metrics_multiple_metrics(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 10.0, "counter")
        exporter.register_metric("cpu_usage", 0.75, "gauge")
        output = exporter.get_metrics()
        assert "requests_total" in output
        assert "cpu_usage" in output


# ── Prometheus metric names ─────────────────────────────────────────────────


class TestPrometheusMetricNames:
    """Tests for Prometheus metric names."""

    def test_get_metric_names_empty(self):
        exporter = PrometheusExporter()
        assert exporter.get_metric_names() == []

    def test_get_metric_names_single(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 1.0, "counter")
        assert exporter.get_metric_names() == ["requests_total"]

    def test_get_metric_names_multiple(self):
        exporter = PrometheusExporter()
        exporter.register_metric("a_metric", 1.0, "counter")
        exporter.register_metric("b_metric", 2.0, "gauge")
        names = exporter.get_metric_names()
        assert "a_metric" in names
        assert "b_metric" in names
        assert len(names) == 2


# ── Prometheus metric values ────────────────────────────────────────────────


class TestPrometheusMetricValues:
    """Tests for Prometheus metric values."""

    def test_get_metric_value_existing(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 99.5, "counter")
        assert exporter.get_metric_value("requests_total") == 99.5

    def test_get_metric_value_missing_returns_none(self):
        exporter = PrometheusExporter()
        assert exporter.get_metric_value("nonexistent") is None

    def test_clear_metrics(self):
        exporter = PrometheusExporter()
        exporter.register_metric("requests_total", 10.0, "counter")
        exporter.clear_metrics()
        assert exporter.get_metric_names() == []
        assert exporter.get_metric_value("requests_total") is None


# ── Alert rule creation ────────────────────────────────────────────────────


class TestAlertRuleCreation:
    """Tests for AlertRule creation."""

    def test_create_alert_rule(self):
        rule = AlertRule(
            name="high_error_rate",
            condition="error_rate > threshold",
            threshold=0.05,
            duration="5m",
            severity="critical",
            summary="Error rate exceeds 5%",
        )
        assert rule.name == "high_error_rate"
        assert rule.condition == "error_rate > threshold"
        assert rule.threshold == 0.05
        assert rule.duration == "5m"
        assert rule.severity == "critical"
        assert rule.summary == "Error rate exceeds 5%"

    def test_alert_rule_severity_enum(self):
        rule = AlertRule(
            name="test",
            condition="x > 1",
            threshold=1.0,
            duration="1m",
            severity=AlertSeverity.WARNING,
            summary="test",
        )
        assert rule.severity == AlertSeverity.WARNING

    def test_alert_severity_values(self):
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.INFO.value == "info"


# ── Alert checking ─────────────────────────────────────────────────────────


class TestAlertChecking:
    """Tests for alert checking logic."""

    def test_check_alert_fires_when_condition_met(self):
        rule = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=0.8,
            duration="5m",
            severity="warning",
            summary="CPU high",
        )
        metrics = {"cpu_usage": 0.95}
        assert check_alert(rule, metrics) is True

    def test_check_alert_not_fired_when_condition_not_met(self):
        rule = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=0.8,
            duration="5m",
            severity="warning",
            summary="CPU high",
        )
        metrics = {"cpu_usage": 0.5}
        assert check_alert(rule, metrics) is False

    def test_check_alert_missing_metric_not_fired(self):
        rule = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=0.8,
            duration="5m",
            severity="warning",
            summary="CPU high",
        )
        assert check_alert(rule, {}) is False

    def test_check_alert_at_threshold_not_fired(self):
        rule = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=0.8,
            duration="5m",
            severity="warning",
            summary="CPU high",
        )
        assert check_alert(rule, {"cpu_usage": 0.8}) is False


# ── Active alerts ──────────────────────────────────────────────────────────


class TestActiveAlerts:
    """Tests for active alerts tracking."""

    def test_get_active_alerts_empty(self):
        clear_alerts()
        assert get_active_alerts() == []

    def test_check_alert_adds_to_active(self):
        clear_alerts()
        rule = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=0.8,
            duration="5m",
            severity="warning",
            summary="CPU high",
        )
        check_alert(rule, {"cpu_usage": 0.95})
        active = get_active_alerts()
        assert len(active) == 1
        assert active[0] == "high_cpu"

    def test_clear_alerts(self):
        rule = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=0.8,
            duration="5m",
            severity="warning",
            summary="CPU high",
        )
        check_alert(rule, {"cpu_usage": 0.95})
        clear_alerts()
        assert get_active_alerts() == []

    def test_multiple_active_alerts(self):
        clear_alerts()
        rule1 = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=0.8,
            duration="5m",
            severity="warning",
            summary="CPU high",
        )
        rule2 = AlertRule(
            name="high_memory",
            condition="memory_usage > threshold",
            threshold=0.9,
            duration="5m",
            severity="critical",
            summary="Memory high",
        )
        check_alert(rule1, {"cpu_usage": 0.95})
        check_alert(rule2, {"memory_usage": 0.95})
        active = get_active_alerts()
        assert "high_cpu" in active
        assert "high_memory" in active


# ── SLO definition ─────────────────────────────────────────────────────────


class TestSLODefinition:
    """Tests for SLODefinition dataclass."""

    def test_create_slo_definition(self):
        slo = SLODefinition(
            name="availability",
            target=0.999,
            window="30d",
            burn_rate_threshold=2.0,
        )
        assert slo.name == "availability"
        assert slo.target == 0.999
        assert slo.window == "30d"
        assert slo.burn_rate_threshold == 2.0

    def test_slo_definition_defaults(self):
        slo = SLODefinition(name="latency", target=0.99, window="7d", burn_rate_threshold=1.0)
        assert slo.name == "latency"
        assert slo.target == 0.99


# ── SLO checking ───────────────────────────────────────────────────────────


class TestSLOChecking:
    """Tests for SLO checking logic."""

    def test_check_slo_passes_when_target_met(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        metrics = {"availability": 0.995}
        assert check_slo(slo, metrics) is True

    def test_check_slo_fails_when_target_missed(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        metrics = {"availability": 0.95}
        assert check_slo(slo, metrics) is False

    def test_check_slo_missing_metric_fails(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        assert check_slo(slo, {}) is False


# ── SLO status ─────────────────────────────────────────────────────────────


class TestSLOStatus:
    """Tests for SLO status reporting."""

    def test_get_slo_status_passing(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        status = get_slo_status(slo, {"availability": 0.995})
        assert status["name"] == "availability"
        assert status["status"] == "passing"

    def test_get_slo_status_failing(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        status = get_slo_status(slo, {"availability": 0.95})
        assert status["status"] == "failing"

    def test_get_slo_status_includes_target(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        status = get_slo_status(slo, {"availability": 0.995})
        assert status["target"] == 0.99


# ── Error budget ───────────────────────────────────────────────────────────


class TestErrorBudget:
    """Tests for error budget calculation."""

    def test_error_budget_positive_when_passing(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        budget = get_error_budget(slo, {"availability": 0.995})
        assert budget > 0

    def test_error_budget_negative_when_failing(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        budget = get_error_budget(slo, {"availability": 0.95})
        assert budget < 0

    def test_error_budget_zero_when_at_target(self):
        slo = SLODefinition(
            name="availability",
            target=0.99,
            window="30d",
            burn_rate_threshold=2.0,
        )
        budget = get_error_budget(slo, {"availability": 0.99})
        assert budget == pytest.approx(0.0)


# ── Grafana dashboard generation ───────────────────────────────────────────


class TestGrafanaDashboardGeneration:
    """Tests for Grafana dashboard generation."""

    def test_generate_dashboard_returns_dict(self):
        config = MonitoringConfig(
            prometheus_enabled=True,
            grafana_enabled=True,
            alertmanager_enabled=True,
            scrape_interval="15s",
            retention_period="30d",
        )
        dashboard = generate_dashboard(config)
        assert isinstance(dashboard, dict)

    def test_generate_dashboard_has_title(self):
        config = MonitoringConfig(
            prometheus_enabled=True,
            grafana_enabled=True,
            alertmanager_enabled=True,
            scrape_interval="15s",
            retention_period="30d",
        )
        dashboard = generate_dashboard(config)
        assert "title" in dashboard

    def test_generate_dashboard_has_panels(self):
        config = MonitoringConfig(
            prometheus_enabled=True,
            grafana_enabled=True,
            alertmanager_enabled=True,
            scrape_interval="15s",
            retention_period="30d",
        )
        dashboard = generate_dashboard(config)
        assert "panels" in dashboard
        assert len(dashboard["panels"]) > 0

    def test_generate_dashboard_has_datasource(self):
        config = MonitoringConfig(
            prometheus_enabled=True,
            grafana_enabled=True,
            alertmanager_enabled=True,
            scrape_interval="15s",
            retention_period="30d",
        )
        dashboard = generate_dashboard(config)
        assert "datasource" in dashboard

    def test_grafana_dashboard_dataclass(self):
        dashboard = GrafanaDashboard(
            title="Test Dashboard",
            panels=[{"title": "CPU", "type": "graph"}],
            datasource="prometheus",
            refresh="30s",
        )
        assert dashboard.title == "Test Dashboard"
        assert len(dashboard.panels) == 1
        assert dashboard.datasource == "prometheus"
        assert dashboard.refresh == "30s"


# ── Grafana panel queries ──────────────────────────────────────────────────


class TestGrafanaPanelQueries:
    """Tests for Grafana panel queries."""

    def test_get_panel_queries(self):
        panels = [
            {"title": "CPU", "targets": [{"expr": "cpu_usage"}]},
            {"title": "Memory", "targets": [{"expr": "memory_usage"}]},
        ]
        queries = get_panel_queries(panels)
        assert "cpu_usage" in queries
        assert "memory_usage" in queries

    def test_get_panel_queries_empty(self):
        assert get_panel_queries([]) == []

    def test_get_panel_queries_multiple_targets(self):
        panels = [
            {"title": "Requests", "targets": [{"expr": "requests_total"}, {"expr": "errors_total"}]},
        ]
        queries = get_panel_queries(panels)
        assert "requests_total" in queries
        assert "errors_total" in queries


# ── Monitoring config ──────────────────────────────────────────────────────


class TestMonitoringConfig:
    """Tests for MonitoringConfig dataclass."""

    def test_config_creation(self):
        config = MonitoringConfig(
            prometheus_enabled=True,
            grafana_enabled=True,
            alertmanager_enabled=True,
            scrape_interval="15s",
            retention_period="30d",
        )
        assert config.prometheus_enabled is True
        assert config.grafana_enabled is True
        assert config.alertmanager_enabled is True
        assert config.scrape_interval == "15s"
        assert config.retention_period == "30d"

    def test_config_defaults(self):
        config = MonitoringConfig()
        assert config.prometheus_enabled is True
        assert config.grafana_enabled is True
        assert config.alertmanager_enabled is True
        assert config.scrape_interval == "15s"
        assert config.retention_period == "30d"

    def test_config_custom_values(self):
        config = MonitoringConfig(
            prometheus_enabled=False,
            grafana_enabled=False,
            alertmanager_enabled=False,
            scrape_interval="30s",
            retention_period="7d",
        )
        assert config.prometheus_enabled is False
        assert config.grafana_enabled is False
        assert config.alertmanager_enabled is False
        assert config.scrape_interval == "30s"
        assert config.retention_period == "7d"


# ── Package exports ────────────────────────────────────────────────────────


class TestPackageExports:
    """Tests for package-level exports."""

    def test_all_exports_available(self):
        from apex_autopilot_optimization import monitoring

        assert hasattr(monitoring, "PrometheusExporter")
        assert hasattr(monitoring, "AlertRule")
        assert hasattr(monitoring, "SLODefinition")
        assert hasattr(monitoring, "GrafanaDashboard")
        assert hasattr(monitoring, "MonitoringConfig")
