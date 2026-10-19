"""End-to-end swarm latency benchmark suite (isolated package).

See ``benchmark/swarm_latency_benchmark.py`` for the public API.
"""

from __future__ import annotations

from .swarm_latency_benchmark import (
    DEFAULT_STAGE_BUDGETS_MS,
    DEFAULT_STAGE_MEANS_MS,
    HIVEMIND_E2E_BUDGET_MS,
    MAX_VEHICLES,
    MIN_VEHICLES,
    PIPELINE_STAGES,
    StageSummary,
    SwarmLatencyBenchmark,
    SwarmLatencyBenchmarkConfig,
    SwarmLatencyBenchmarkResult,
    TierWtaTiming,
    VehicleCycleResult,
    VehicleSummary,
    generate_report,
    percentile,
    run_sweep,
    write_report,
)

__all__ = [
    "PIPELINE_STAGES",
    "HIVEMIND_E2E_BUDGET_MS",
    "MIN_VEHICLES",
    "MAX_VEHICLES",
    "DEFAULT_STAGE_MEANS_MS",
    "DEFAULT_STAGE_BUDGETS_MS",
    "SwarmLatencyBenchmark",
    "SwarmLatencyBenchmarkConfig",
    "SwarmLatencyBenchmarkResult",
    "StageSummary",
    "TierWtaTiming",
    "VehicleCycleResult",
    "VehicleSummary",
    "generate_report",
    "percentile",
    "run_sweep",
    "write_report",
]
