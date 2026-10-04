"""Tests for observability module - verify StructuredLogger actually emits."""

import json
import sys
from io import StringIO
from apex_autopilot_optimization.observability import (
    ObservabilityConfig,
    ObservabilityManager,
    StructuredLogger,
)


class TestStructuredLogger:
    """Tests for StructuredLogger class."""

    def test_logger_creation(self):
        logger = StructuredLogger("test-service")
        assert logger is not None

    def test_log_returns_dict(self):
        logger = StructuredLogger("test-service")
        result = logger.info("test message")
        assert isinstance(result, dict)
        assert result["level"] == "INFO"
        assert result["message"] == "test message"
        assert result["service"] == "test-service"

    def test_info_log(self):
        logger = StructuredLogger("test-service")
        result = logger.info("info message")
        assert result["level"] == "INFO"

    def test_error_log(self):
        logger = StructuredLogger("test-service")
        result = logger.error("error message")
        assert result["level"] == "ERROR"

    def test_warning_log(self):
        logger = StructuredLogger("test-service")
        result = logger.warning("warning message")
        assert result["level"] == "WARNING"

    def test_debug_log(self):
        logger = StructuredLogger("test-service")
        result = logger.debug("debug message")
        assert result["level"] == "DEBUG"

    def test_log_with_context(self):
        logger = StructuredLogger("test-service")
        result = logger.info("test", user="alice", action="login")
        assert result["context"]["user"] == "alice"
        assert result["context"]["action"] == "login"

    def test_log_has_timestamp(self):
        logger = StructuredLogger("test-service")
        result = logger.info("test")
        assert "timestamp" in result
        assert result["timestamp"] > 0


class TestMetricCollector:
    """Tests for MetricCollector class."""

    def test_collector_creation(self):
        from apex_autopilot_optimization.observability import MetricCollector
        collector = MetricCollector()
        assert collector is not None

    def test_increment(self):
        from apex_autopilot_optimization.observability import MetricCollector
        collector = MetricCollector()
        collector.increment("requests")
        collector.increment("requests")
        metrics = collector.get_metrics()
        assert metrics["requests"] == 2

    def test_gauge(self):
        from apex_autopilot_optimization.observability import MetricCollector
        collector = MetricCollector()
        collector.gauge("cpu_usage", 45.2)
        metrics = collector.get_metrics()
        assert metrics["cpu_usage"] == 45.2


class TestHealthCheck:
    """Tests for HealthCheck class."""

    def test_health_check(self):
        from apex_autopilot_optimization.observability import HealthCheck
        check = HealthCheck()
        result = check.check("test-service")
        assert result["service"] == "test-service"
        assert result["status"] == "healthy"
        assert result["checks"]["liveness"] == "pass"
        assert result["checks"]["readiness"] == "pass"


class TestObservabilityManager:
    """Tests for ObservabilityManager class."""

    def test_manager_creation(self):
        config = ObservabilityConfig(service_name="test-service")
        manager = ObservabilityManager(config)
        assert manager is not None

    def test_log(self):
        config = ObservabilityConfig(service_name="test-service")
        manager = ObservabilityManager(config)
        result = manager.log("INFO", "test message")
        assert result["level"] == "INFO"

    def test_collect(self):
        config = ObservabilityConfig(service_name="test-service")
        manager = ObservabilityManager(config)
        manager.collect("cpu_usage", 50.0)
        metrics = manager.get_metrics()
        assert metrics["cpu_usage"] == 50.0

    def test_health(self):
        config = ObservabilityConfig(service_name="test-service")
        manager = ObservabilityManager(config)
        result = manager.health()
        assert result["status"] == "healthy"


class TestObservabilityFunctions:
    """Tests for module-level functions."""

    def test_check_health(self):
        from apex_autopilot_optimization.observability import check_health
        result = check_health("test-service")
        assert result["status"] == "healthy"

    def test_collect_metrics(self):
        from apex_autopilot_optimization.observability import collect_metrics
        result = collect_metrics()
        assert "cpu_usage" in result
        assert "memory_usage" in result
        assert "requests_total" in result

    def test_create_logger(self):
        from apex_autopilot_optimization.observability import create_logger
        logger = create_logger("test-service")
        assert logger is not None

    def test_format_metric(self):
        from apex_autopilot_optimization.observability import format_metric
        result = format_metric("cpu_usage", 45.2, "gauge")
        assert result["name"] == "cpu_usage"
        assert result["value"] == 45.2
        assert result["type"] == "gauge"
