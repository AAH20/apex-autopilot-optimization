"""Tests for evaluation module."""

from apex_autopilot_optimization.evaluation import (
    EvaluationConfig,
    EvaluationMetric,
    EvaluationResult,
    EvaluationRunner,
    MetricAggregator,
    aggregate_metrics,
    evaluate_all,
    evaluate_metric,
    run_evaluation,
)


class TestEvaluationConfig:
    """Tests for EvaluationConfig dataclass."""

    def test_config_creation(self):
        config = EvaluationConfig(
            name="test_eval",
            metrics=["accuracy", "latency", "safety"],
        )
        assert config.name == "test_eval"
        assert len(config.metrics) == 3

    def test_config_defaults(self):
        config = EvaluationConfig(name="test")
        assert config.metrics is not None


class TestEvaluationMetric:
    """Tests for EvaluationMetric dataclass."""

    def test_metric_creation(self):
        metric = EvaluationMetric(
            name="accuracy",
            value=0.95,
            target=0.90,
            weight=1.0,
        )
        assert metric.name == "accuracy"
        assert metric.value == 0.95
        assert metric.target == 0.90

    def test_metric_pass(self):
        metric = EvaluationMetric(
            name="accuracy",
            value=0.95,
            target=0.90,
            weight=1.0,
        )
        assert metric.passed is True

    def test_metric_fail(self):
        metric = EvaluationMetric(
            name="accuracy",
            value=0.85,
            target=0.90,
            weight=1.0,
        )
        assert metric.passed is False

    def test_metric_to_dict(self):
        metric = EvaluationMetric(
            name="accuracy",
            value=0.95,
            target=0.90,
            weight=1.0,
        )
        d = metric.to_dict()
        assert d["name"] == "accuracy"
        assert d["value"] == 0.95
        assert d["passed"] is True


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_result_creation(self):
        result = EvaluationResult(
            name="test",
            metrics=[],
            overall_score=0.95,
            passed=True,
        )
        assert result.name == "test"
        assert result.overall_score == 0.95
        assert result.passed is True

    def test_result_to_dict(self):
        result = EvaluationResult(
            name="test",
            metrics=[],
            overall_score=0.95,
            passed=True,
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["overall_score"] == 0.95


class TestEvaluationRunner:
    """Tests for EvaluationRunner class."""

    def test_runner_creation(self):
        config = EvaluationConfig(name="test")
        runner = EvaluationRunner(config)
        assert runner is not None

    def test_run_evaluation(self):
        config = EvaluationConfig(
            name="test",
            metrics=["accuracy", "latency"],
        )
        runner = EvaluationRunner(config)
        result = runner.run()
        assert result is not None
        assert result.name == "test"
        assert result.overall_score >= 0

    def test_run_with_custom_metrics(self):
        config = EvaluationConfig(
            name="test",
            metrics=["accuracy"],
        )
        runner = EvaluationRunner(config)
        result = runner.run()
        assert result is not None
        assert len(result.metrics) > 0


class TestMetricAggregator:
    """Tests for MetricAggregator class."""

    def test_aggregator_creation(self):
        aggregator = MetricAggregator()
        assert aggregator is not None

    def test_add_metric(self):
        aggregator = MetricAggregator()
        aggregator.add(EvaluationMetric(name="accuracy", value=0.95, target=0.90))
        assert len(aggregator.metrics) == 1

    def test_compute_weighted_score(self):
        aggregator = MetricAggregator()
        aggregator.add(EvaluationMetric(name="accuracy", value=0.95, target=0.90, weight=1.0))
        aggregator.add(EvaluationMetric(name="latency", value=0.85, target=0.80, weight=0.5))
        score = aggregator.compute_weighted_score()
        assert score > 0
        assert score <= 1.0

    def test_get_pass_rate(self):
        aggregator = MetricAggregator()
        aggregator.add(EvaluationMetric(name="accuracy", value=0.95, target=0.90))
        aggregator.add(EvaluationMetric(name="latency", value=0.75, target=0.80))
        pass_rate = aggregator.get_pass_rate()
        assert pass_rate == 0.5


class TestAggregateMetrics:
    """Tests for aggregate_metrics function."""

    def test_returns_dict(self):
        metrics = [
            EvaluationMetric(name="accuracy", value=0.95, target=0.90),
            EvaluationMetric(name="latency", value=0.85, target=0.80),
        ]
        result = aggregate_metrics(metrics)
        assert isinstance(result, dict)
        assert "overall_score" in result
        assert "pass_rate" in result


class TestEvaluateMetric:
    """Tests for evaluate_metric function."""

    def test_returns_metric(self):
        result = evaluate_metric("accuracy", 0.95, 0.90)
        assert isinstance(result, EvaluationMetric)
        assert result.name == "accuracy"
        assert result.passed is True

    def test_fail_metric(self):
        result = evaluate_metric("accuracy", 0.85, 0.90)
        assert result.passed is False


class TestEvaluateAll:
    """Tests for evaluate_all function."""

    def test_returns_result(self):
        values = {"accuracy": 0.95, "latency": 0.85}
        targets = {"accuracy": 0.90, "latency": 0.80}
        result = evaluate_all(values, targets)
        assert isinstance(result, EvaluationResult)
        assert result.overall_score >= 0


class TestRunEvaluation:
    """Tests for run_evaluation function."""

    def test_returns_result(self):
        config = EvaluationConfig(
            name="test",
            metrics=["accuracy", "latency"],
        )
        result = run_evaluation(config)
        assert isinstance(result, EvaluationResult)
        assert result.name == "test"
