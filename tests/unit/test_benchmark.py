"""Tests for benchmark module."""

from apex_autopilot_optimization.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkRunner,
    EvolutionTracker,
    compare_benchmarks,
    run_benchmark,
    run_benchmark_suite,
)


class TestBenchmarkConfig:
    """Tests for BenchmarkConfig dataclass."""

    def test_config_creation(self):
        config = BenchmarkConfig(
            name="test_benchmark",
            iterations=100,
            warmup_iterations=10,
        )
        assert config.name == "test_benchmark"
        assert config.iterations == 100
        assert config.warmup_iterations == 10

    def test_config_defaults(self):
        config = BenchmarkConfig(name="test")
        assert config.iterations == 100
        assert config.warmup_iterations == 10


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_result_creation(self):
        result = BenchmarkResult(
            name="test",
            mean_ms=10.5,
            p50_ms=9.0,
            p95_ms=15.0,
            p99_ms=20.0,
            iterations=100,
        )
        assert result.name == "test"
        assert result.mean_ms == 10.5
        assert result.iterations == 100

    def test_result_to_dict(self):
        result = BenchmarkResult(
            name="test",
            mean_ms=10.5,
            p50_ms=9.0,
            p95_ms=15.0,
            p99_ms=20.0,
            iterations=100,
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["mean_ms"] == 10.5


class TestBenchmarkRunner:
    """Tests for BenchmarkRunner class."""

    def test_runner_creation(self):
        config = BenchmarkConfig(name="test")
        runner = BenchmarkRunner(config)
        assert runner is not None

    def test_run_benchmark(self):
        config = BenchmarkConfig(name="test", iterations=10, warmup_iterations=2)
        runner = BenchmarkRunner(config)
        result = runner.run()
        assert result is not None
        assert result.name == "test"
        assert result.iterations == 10

    def test_run_benchmark_with_function(self):
        def test_func():
            return sum(range(100))

        config = BenchmarkConfig(name="test", iterations=10, warmup_iterations=2)
        runner = BenchmarkRunner(config)
        result = runner.run(test_func)
        assert result is not None
        assert result.iterations == 10


class TestEvolutionTracker:
    """Tests for EvolutionTracker class."""

    def test_tracker_creation(self):
        tracker = EvolutionTracker()
        assert tracker is not None

    def test_record_generation(self):
        tracker = EvolutionTracker()
        tracker.record_generation(0, 100.0)
        assert len(tracker.generations) == 1

    def test_record_multiple_generations(self):
        tracker = EvolutionTracker()
        tracker.record_generation(0, 100.0)
        tracker.record_generation(1, 90.0)
        tracker.record_generation(2, 80.0)
        assert len(tracker.generations) == 3

    def test_get_best_generation(self):
        tracker = EvolutionTracker()
        tracker.record_generation(0, 100.0)
        tracker.record_generation(1, 80.0)
        tracker.record_generation(2, 90.0)
        best = tracker.get_best_generation()
        assert best is not None
        assert best["generation"] == 1
        assert best["score"] == 80.0

    def test_get_improvement_rate(self):
        tracker = EvolutionTracker()
        tracker.record_generation(0, 100.0)
        tracker.record_generation(1, 90.0)
        tracker.record_generation(2, 80.0)
        rate = tracker.get_improvement_rate()
        assert rate is not None
        assert rate > 0

    def test_get_convergence_generation(self):
        tracker = EvolutionTracker()
        tracker.record_generation(0, 100.0)
        tracker.record_generation(1, 80.0)
        tracker.record_generation(2, 75.0)
        tracker.record_generation(3, 74.0)
        tracker.record_generation(4, 73.5)
        conv = tracker.get_convergence_generation(threshold=1.0)
        assert conv is not None


class TestRunBenchmark:
    """Tests for run_benchmark function."""

    def test_returns_result(self):
        config = BenchmarkConfig(name="test", iterations=5, warmup_iterations=1)
        result = run_benchmark(config)
        assert isinstance(result, BenchmarkResult)

    def test_result_has_metrics(self):
        config = BenchmarkConfig(name="test", iterations=5, warmup_iterations=1)
        result = run_benchmark(config)
        assert result.mean_ms >= 0
        assert result.p50_ms >= 0
        assert result.p95_ms >= 0


class TestRunBenchmarkSuite:
    """Tests for run_benchmark_suite function."""

    def test_returns_dict(self):
        configs = [
            BenchmarkConfig(name="test1", iterations=5, warmup_iterations=1),
            BenchmarkConfig(name="test2", iterations=5, warmup_iterations=1),
        ]
        results = run_benchmark_suite(configs)
        assert isinstance(results, dict)
        assert "test1" in results
        assert "test2" in results


class TestCompareBenchmarks:
    """Tests for compare_benchmarks function."""

    def test_compare_improvement(self):
        baseline = BenchmarkResult(
            name="test",
            mean_ms=100.0,
            p50_ms=90.0,
            p95_ms=150.0,
            p99_ms=200.0,
            iterations=100,
        )
        current = BenchmarkResult(
            name="test",
            mean_ms=80.0,
            p50_ms=70.0,
            p95_ms=120.0,
            p99_ms=160.0,
            iterations=100,
        )
        comparison = compare_benchmarks(baseline, current)
        assert comparison is not None
        assert comparison["improvement_pct"] > 0

    def test_compare_regression(self):
        baseline = BenchmarkResult(
            name="test",
            mean_ms=80.0,
            p50_ms=70.0,
            p95_ms=120.0,
            p99_ms=160.0,
            iterations=100,
        )
        current = BenchmarkResult(
            name="test",
            mean_ms=100.0,
            p50_ms=90.0,
            p95_ms=150.0,
            p99_ms=200.0,
            iterations=100,
        )
        comparison = compare_benchmarks(baseline, current)
        assert comparison is not None
        assert comparison["improvement_pct"] < 0
