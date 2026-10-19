"""Unit tests for the swarm latency benchmark suite.

TDD: RED->GREEN->REFACTOR.

Covers latency aggregation, p95 calculation, the Hivemind <100 ms
end-to-end comparison flag, and markdown report generation for
``benchmark/swarm_latency_benchmark.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The isolated ``benchmark/`` package lives at the project root, next to
# ``tests/``; make it importable regardless of the CWD pytest is invoked from.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.swarm_latency_benchmark import (  # noqa: E402  (imported after the path bootstrap above)
    HIVEMIND_E2E_BUDGET_MS,
    MAX_VEHICLES,
    MIN_VEHICLES,
    PIPELINE_STAGES,
    SwarmLatencyBenchmark,
    SwarmLatencyBenchmarkConfig,
    generate_report,
    percentile,
    run_sweep,
    write_report,
)

STAGE_MEANS_UNDER_BUDGET = {name: 1.0 for name in PIPELINE_STAGES}  # 6 ms total
STAGE_MEANS_OVER_BUDGET = {name: 25.0 for name in PIPELINE_STAGES}  # 150 ms total


def _config(**overrides) -> SwarmLatencyBenchmarkConfig:
    data = dict(
        num_vehicles=3,
        cycles_per_vehicle=25,
        stage_mean_ms=dict(STAGE_MEANS_UNDER_BUDGET),
        stage_jitter_ms=0.0,
        seed=11,
    )
    data.update(overrides)
    return SwarmLatencyBenchmarkConfig(**data)


class TestPercentile:
    def test_known_nearest_rank_values(self):
        samples = list(range(1, 101))
        assert percentile(samples, 0.50) == 50.0
        assert percentile(samples, 0.95) == 95.0
        assert percentile(samples, 0.99) == 99.0

    def test_empty_returns_zero(self):
        assert percentile([], 0.95) == 0.0

    def test_single_sample(self):
        assert percentile([42.0], 0.95) == 42.0

    def test_matches_latency_tracker_convention(self):
        from apex_autopilot_optimization.perception import LatencyTracker

        tracker = LatencyTracker()
        samples = [1.0, 2.0, 3.0, 10.0]
        for sample in samples:
            tracker.record("ingestion", sample)
        assert percentile(samples, 0.95) == tracker.p95("ingestion")


class TestLatencyAggregation:
    def test_aggregate_shape(self):
        bench = SwarmLatencyBenchmark(_config())
        result = bench.run()

        assert len(result.cycle_latencies_ms) == 3 * 25
        assert set(result.vehicle_results) == {1, 2, 3}
        assert all(len(cycles) == 25 for cycles in result.vehicle_results.values())
        assert result.mean_ms > 0.0
        assert result.min_ms >= 0.0
        assert result.p50_ms <= result.p95_ms <= result.p99_ms
        assert result.p99_ms <= max(result.cycle_latencies_ms)
        # Every cycle latency equals the sum of its six recorded stages.
        for _vehicle_id, cycles in result.vehicle_results.items():
            for cycle in cycles:
                assert cycle.cycle_latency_ms == sum(cycle.stage_latencies_ms.values())

    def test_all_pipeline_stages_recorded_via_latency_tracker(self):
        bench = SwarmLatencyBenchmark(_config())
        result = bench.run()

        for stage in PIPELINE_STAGES:
            assert bench.tracker.p95(stage) > 0.0
            assert bench.tracker.stage_over_budget(stage) is False
        assert bench.tracker.end_to_end_ms() > 0.0
        assert result.end_to_end_p95_ms == bench.tracker.end_to_end_ms()

    def test_deterministic_given_seed(self):
        first = SwarmLatencyBenchmark(_config()).run()
        second = SwarmLatencyBenchmark(_config()).run()
        assert first.cycle_latencies_ms == second.cycle_latencies_ms
        assert first.p95_ms == second.p95_ms

    def test_vehicle_summaries_cover_all_vehicles(self):
        bench = SwarmLatencyBenchmark(_config(num_vehicles=5, cycles_per_vehicle=10))
        result = bench.run()
        assert set(result.vehicle_summaries) == {1, 2, 3, 4, 5}
        for summary in result.vehicle_summaries.values():
            assert summary.cycles == 10
            assert 0.0 <= summary.p50_ms <= summary.p95_ms <= summary.p99_ms


class TestHivemindComparison:
    def test_pass_when_p95_under_budget(self):
        bench = SwarmLatencyBenchmark(
            _config(stage_mean_ms=STAGE_MEANS_UNDER_BUDGET, num_vehicles=10)
        )
        result = bench.run()
        assert result.hivemind_pass is True
        assert result.hivemind_margin_ms >= 0.0
        assert result.hivemind_e2e_budget_ms == HIVEMIND_E2E_BUDGET_MS

    def test_fail_when_p95_over_budget(self):
        bench = SwarmLatencyBenchmark(
            _config(stage_mean_ms=STAGE_MEANS_OVER_BUDGET, num_vehicles=1)
        )
        result = bench.run()
        assert result.hivemind_pass is False
        assert result.hivemind_margin_ms < 0.0

    def test_flag_matches_p95_versus_budget(self):
        result = SwarmLatencyBenchmark(_config()).run()
        assert result.hivemind_pass is (result.p95_ms <= result.hivemind_e2e_budget_ms)


class TestWtaTierTimings:
    def test_all_tiers_present_with_measured_times(self):
        result = SwarmLatencyBenchmark(_config(num_vehicles=2)).run()
        assert set(result.wta_tier_timings) == {"t1_milp", "t2_greedy", "t3_vlsn"}
        for timing in result.wta_tier_timings.values():
            assert len(timing.solve_times_ms) >= 1
            assert timing.weapons > 0 and timing.targets > 0
            assert timing.pairs == timing.weapons * timing.targets
            assert 0.0 <= timing.mean_ms <= timing.max_ms


class TestFormationDeviation:
    def test_zero_deviation_with_zero_noise(self):
        result = SwarmLatencyBenchmark(_config(num_vehicles=6, formation_noise_m=0.0)).run()
        assert result.formation_mean_deviation_m == 0.0
        assert result.formation_max_deviation_m == 0.0

    def test_positive_deviation_with_noise(self):
        result = SwarmLatencyBenchmark(_config(num_vehicles=6, formation_noise_m=0.5)).run()
        assert result.formation_mean_deviation_m > 0.0
        assert result.formation_max_deviation_m >= result.formation_mean_deviation_m


class TestConfigValidation:
    def test_num_vehicles_bounds(self):
        with pytest.raises(ValueError):
            SwarmLatencyBenchmarkConfig(num_vehicles=MIN_VEHICLES - 1)
        with pytest.raises(ValueError):
            SwarmLatencyBenchmarkConfig(num_vehicles=MAX_VEHICLES + 1)
        SwarmLatencyBenchmarkConfig(num_vehicles=MIN_VEHICLES)
        SwarmLatencyBenchmarkConfig(num_vehicles=MAX_VEHICLES)


class TestReportGeneration:
    def test_generated_report_contains_required_sections(self):
        result = SwarmLatencyBenchmark(_config(num_vehicles=4)).run()
        report = generate_report(result)

        for token in (
            "# Swarm Latency Benchmark Report",
            "Hivemind <100 ms end-to-end benchmark",
            "PASS",
            "t1_milp",
            "t2_greedy",
            "t3_vlsn",
            "Formation deviation",
            "ingestion",
            "filtering",
            "tracking",
            "transform",
            "wta_solve",
            "publish",
        ):
            assert token in report, f"missing report section/token: {token!r}"

    def test_report_marks_fail_when_over_budget(self):
        result = SwarmLatencyBenchmark(
            _config(stage_mean_ms=STAGE_MEANS_OVER_BUDGET, num_vehicles=1)
        ).run()
        assert "FAIL" in generate_report(result)

    def test_write_report_creates_filled_file(self, tmp_path):
        result = SwarmLatencyBenchmark(_config()).run()
        out = tmp_path / "benchmark_report.md"
        write_report(result, out)

        assert out.exists()
        text = out.read_text()
        assert text.strip().startswith("# Swarm Latency Benchmark Report")
        assert f"p95 = {result.p95_ms:.3f} ms" in text or f"{result.p95_ms:.3f}" in text

    def test_sweep_covers_one_to_ten_vehicles(self):
        results = run_sweep(num_vehicles=range(1, MAX_VEHICLES + 1))
        assert [r.config.num_vehicles for r in results] == list(range(1, MAX_VEHICLES + 1))
        assert all(r.hivemind_e2e_budget_ms == HIVEMIND_E2E_BUDGET_MS for r in results)
