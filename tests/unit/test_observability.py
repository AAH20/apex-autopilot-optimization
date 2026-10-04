"""Tests for observability module."""

from apex_autopilot_optimization.observability import (
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


class TestObservabilityConfig:
    """Tests for ObservabilityConfig dataclass."""

    def test_config_creation(self):
        config = ObservabilityConfig(
            service_name="test-service",
            log_level="INFO",
            metrics_enabled=True,
            health_check_enabled=True,
        )
        assert config.service_name == "test-service"
        assert config.log_level == "INFO"
        assert config.metrics_enabled is True
        assert config.health_check_enabled is True

    def test_config_defaults(self):
        config = ObservabilityConfig(service_name="test")
        assert config.log_level == "INFO"
        assert config.metrics_enabled is True
        assert config.health_check_enabled is True


class TestStructuredLogger:
    """Tests for StructuredLogger class."""

    def test_logger_creation(self):
        logger = StructuredLogger("test-service")
        assert logger is not None

    def test_log_info(self):
        logger = StructuredLogger("test-service")
        result = logger.info("Test message", user="test")
        assert result is not None
        assert result["level"] == "INFO"
        assert result["message"] == "Test message"
        assert result["service"] == "test-service"

    def test_log_error(self):
        logger = StructuredLogger("test-service")
        result = logger.error("Error message", error="test_error")
        assert result is not None
        assert result["level"] == "ERROR"

    def test_log_warning(self):
        logger = StructuredLogger("test-service")
        result = logger.warning("Warning message")
        assert result is not None
        assert result["level"] == "WARNING"

    def test_log_debug(self):
        logger = StructuredLogger("test-service")
        result = logger.debug("Debug message")
        assert result is not None
        assert result["level"] == "DEBUG"

    def test_log_with_context(self):
        logger = StructuredLogger("test-service")
        result = logger.info("Test", user="test", action="login")
        assert result["context"]["user"] == "test"
        assert result["context"]["action"] == "login"


class TestMetricCollector:
    """Tests for MetricCollector class."""

    def test_collector_creation(self):
        collector = MetricCollector()
        assert collector is not None

    def test_increment_counter(self):
        collector = MetricCollector()
        collector.increment("test_counter")
        metrics = collector.get_metrics()
        assert "test_counter" in metrics

    def test_record_gauge(self):
        collector = MetricCollector()
        collector.gauge("test_gauge", 42.0)
        metrics = collector.get_metrics()
        assert metrics["test_gauge"] == 42.0

    def test_record_histogram(self):
        collector = MetricCollector()
        collector.histogram("test_histogram", 1.5)
        metrics = collector.get_metrics()
        assert "test_histogram" in metrics

    def test_get_metrics(self):
        collector = MetricCollector()
        collector.increment("counter1")
        collector.gauge("gauge1", 10.0)
        metrics = collector.get_metrics()
        assert isinstance(metrics, dict)
        assert len(metrics) >= 2


class TestHealthCheck:
    """Tests for HealthCheck class."""

    def test_check_creation(self):
        check = HealthCheck()
        assert check is not None

    def test_check_pass(self):
        check = HealthCheck()
        result = check.check("test-service")
        assert result is not None
        assert result["status"] in ("healthy", "unhealthy", "degraded")

    def test_check_with_details(self):
        check = HealthCheck()
        result = check.check("test-service")
        assert "service" in result
        assert "timestamp" in result


class TestObservabilityManager:
    """Tests for ObservabilityManager class."""

    def test_manager_creation(self):
        config = ObservabilityConfig(service_name="test")
        manager = ObservabilityManager(config)
        assert manager is not None

    def test_manager_has_logger(self):
        config = ObservabilityConfig(service_name="test")
        manager = ObservabilityManager(config)
        assert manager.logger is not None

    def test_manager_has_collector(self):
        config = ObservabilityConfig(service_name="test")
        manager = ObservabilityManager(config)
        assert manager.collector is not None

    def test_manager_has_health_check(self):
        config = ObservabilityConfig(service_name="test")
        manager = ObservabilityManager(config)
        assert manager.health_check is not None

    def test_manager_log(self):
        config = ObservabilityConfig(service_name="test")
        manager = ObservabilityManager(config)
        result = manager.log("INFO", "Test message")
        assert result is not None

    def test_manager_collect(self):
        config = ObservabilityConfig(service_name="test")
        manager = ObservabilityManager(config)
        manager.collect("test_metric", 1.0)
        metrics = manager.get_metrics()
        assert "test_metric" in metrics

    def test_manager_health(self):
        config = ObservabilityConfig(service_name="test")
        manager = ObservabilityManager(config)
        result = manager.health()
        assert result is not None
        assert "status" in result


class TestCheckHealth:
    """Tests for check_health function."""

    def test_returns_dict(self):
        result = check_health("test-service")
        assert isinstance(result, dict)

    def test_has_status(self):
        result = check_health("test-service")
        assert "status" in result


class TestCollectMetrics:
    """Tests for collect_metrics function."""

    def test_returns_dict(self):
        result = collect_metrics()
        assert isinstance(result, dict)

    def test_has_metrics(self):
        result = collect_metrics()
        assert len(result) > 0


class TestCreateLogger:
    """Tests for create_logger function."""

    def test_returns_logger(self):
        logger = create_logger("test-service")
        assert logger is not None

    def test_logger_has_service_name(self):
        logger = create_logger("test-service")
        result = logger.info("Test")
        assert result["service"] == "test-service"


class TestFormatMetric:
    """Tests for format_metric function."""

    def test_format_counter(self):
        result = format_metric("test_counter", 1, "counter")
        assert isinstance(result, dict)
        assert result["name"] == "test_counter"
        assert result["value"] == 1
        assert result["type"] == "counter"

    def test_format_gauge(self):
        result = format_metric("test_gauge", 42.0, "gauge")
        assert isinstance(result, dict)
        assert result["name"] == "test_gauge"
        assert result["value"] == 42.0
        assert result["type"] == "gauge"
