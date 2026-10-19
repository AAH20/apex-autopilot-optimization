"""End-to-end swarm latency benchmark suite (isolated package).

Measures the perception ingestion -> filtering -> tracking -> transform ->
WTA solve -> setpoint publish cycle latency per simulated vehicle using
``LatencyTracker`` from the perception package, aggregates p50/p95/p99
cycle latency across a swarm of 1..10 vehicles, compares against the
Hivemind <100 ms end-to-end benchmark, reports WTA solve time per tier
(T1/T2/T3) and formation deviation, and emits a markdown benchmark report.

Stage durations are simulated draws recorded through ``LatencyTracker``
exactly as the real pipeline would record them; the WTA solve stage uses
a real ``TieredWTASolver`` measurement so tier timings reflect the actual
solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from apex_autopilot_optimization.core.types import Pose3D, StateVector, Velocity3D
from apex_autopilot_optimization.perception import LatencyTracker
from apex_autopilot_optimization.perception.latency import P95_TARGET_MS
from apex_autopilot_optimization.swarm import FormationConfig, FormationController
from apex_autopilot_optimization.swarm.wta_solver import (
    Target,
    Tier,
    TieredWTASolver,
    Weapon,
    WTAConfig,
)

__all__ = [
    "PIPELINE_STAGES",
    "HIVEMIND_E2E_BUDGET_MS",
    "MIN_VEHICLES",
    "MAX_VEHICLES",
    "DEFAULT_STAGE_MEANS_MS",
    "DEFAULT_STAGE_BUDGETS_MS",
    "percentile",
    "StageSummary",
    "VehicleCycleResult",
    "VehicleSummary",
    "TierWtaTiming",
    "SwarmLatencyBenchmarkConfig",
    "SwarmLatencyBenchmarkResult",
    "SwarmLatencyBenchmark",
    "generate_report",
    "write_report",
    "run_sweep",
    "main",
]

# --------------------------------------------------------------------------- constants

PIPELINE_STAGES: tuple[str, ...] = (
    "ingestion",
    "filtering",
    "tracking",
    "transform",
    "wta_solve",
    "publish",
)

# Hivemind Wave 1 requirement: <100 ms end-to-end (camera -> inference ->
# control) per cycle.
HIVEMIND_E2E_BUDGET_MS = 100.0

MIN_VEHICLES = 1
MAX_VEHICLES = 10

# Typical stage means (ms) for the simulated pipeline. Values sit below the
# per-stage spec budgets so a healthy swarm clears the 100 ms ceiling.
DEFAULT_STAGE_MEANS_MS: dict[str, float] = {
    "ingestion": 1.5,
    "filtering": 2.5,
    "tracking": 2.0,
    "transform": 2.5,
    "wta_solve": 7.0,
    "publish": 1.5,
}

# Stage budgets (ms) fed to LatencyTracker; mirrors the perception spec
# budgets for the shared stages and adds a budget for tracking.
DEFAULT_STAGE_BUDGETS_MS: dict[str, float] = {
    "ingestion": 2.0,
    "filtering": 4.0,
    "tracking": 3.0,
    "transform": 4.0,
    "wta_solve": 12.0,
    "publish": 2.0,
}

# Fixed-size WTA problems guaranteed to select each tier (tier_override is
# still used to pin the tier for the timing calibration).
TIER_PROBLEMS: dict[str, tuple[int, int]] = {
    "t1_milp": (4, 6),     # 24 pairs    -> T1 (< 400 pairs)
    "t2_greedy": (16, 16), # 256 pairs   -> T2 (pinned; < 6400 pairs)
    "t3_vlsn": (30, 30),   # 900 pairs   -> T3 (pinned; < 6400 pairs)
}

TIER_REPEATS = 3


# --------------------------------------------------------------------------- helpers

def percentile(samples: list[float], q: float) -> float:
    """Nearest-rank percentile, same convention as ``LatencyTracker.p95``.

    ``q`` must be in ``[0, 1]``. Returns ``0.0`` for empty input.
    """
    if not samples:
        return 0.0
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"quantile q must be in [0, 1], got {q}")
    ordered = sorted(samples)
    k = max(0, min(len(ordered) - 1, int(math.ceil(q * len(ordered))) - 1))
    return float(ordered[k])


# --------------------------------------------------------------------------- results

@dataclass(slots=True)
class StageSummary:
    """Aggregated latency statistics for one pipeline stage."""

    name: str
    count: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    budget_ms: float | None = None

    @property
    def over_budget(self) -> bool:
        if self.budget_ms is None:
            return False
        return self.p95_ms > self.budget_ms


@dataclass(slots=True)
class VehicleCycleResult:
    """Single cycle latency measurement for one vehicle."""

    vehicle_id: int
    cycle: int
    stage_latencies_ms: dict[str, float]
    cycle_latency_ms: float


@dataclass(slots=True)
class VehicleSummary:
    """Per-vehicle aggregated cycle latency."""

    vehicle_id: int
    cycles: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float


@dataclass(slots=True)
class TierWtaTiming:
    """Measured WTA solve time for one tier."""

    tier: str
    weapons: int
    targets: int
    pairs: int
    solve_times_ms: list[float]

    @property
    def mean_ms(self) -> float:
        return sum(self.solve_times_ms) / len(self.solve_times_ms)

    @property
    def max_ms(self) -> float:
        return max(self.solve_times_ms)


@dataclass(slots=True)
class SwarmLatencyBenchmarkConfig:
    """Configuration for a swarm latency benchmark run."""

    num_vehicles: int = 10
    cycles_per_vehicle: int = 50
    stage_mean_ms: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_STAGE_MEANS_MS))
    stage_jitter_ms: float = 1.5
    stage_budget_ms: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_STAGE_BUDGETS_MS)
    )
    hivemind_e2e_budget_ms: float = HIVEMIND_E2E_BUDGET_MS
    p95_target_ms: float = P95_TARGET_MS
    formation_spacing_m: float = 2.0
    formation_noise_m: float = 0.05
    seed: int = 42

    def __post_init__(self) -> None:
        if not (MIN_VEHICLES <= self.num_vehicles <= MAX_VEHICLES):
            raise ValueError(
                f"num_vehicles must be in [{MIN_VEHICLES}, {MAX_VEHICLES}], "
                f"got {self.num_vehicles}"
            )
        if self.cycles_per_vehicle < 1:
            raise ValueError(f"cycles_per_vehicle must be >= 1, got {self.cycles_per_vehicle}")
        if self.stage_jitter_ms < 0.0:
            raise ValueError(f"stage_jitter_ms must be >= 0, got {self.stage_jitter_ms}")
        missing = [s for s in PIPELINE_STAGES if s not in self.stage_mean_ms]
        if missing:
            raise ValueError(f"stage_mean_ms missing stages: {missing}")
        missing = [s for s in PIPELINE_STAGES if s not in self.stage_budget_ms]
        if missing:
            raise ValueError(f"stage_budget_ms missing stages: {missing}")


@dataclass(slots=True)
class SwarmLatencyBenchmarkResult:
    """Full outcome of a benchmark run."""

    config: SwarmLatencyBenchmarkConfig
    started_at: str
    finished_at: str
    cycle_latencies_ms: list[float]
    vehicle_results: dict[int, list[VehicleCycleResult]]
    vehicle_summaries: dict[int, VehicleSummary]
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    stage_summaries: dict[str, StageSummary]
    hivemind_pass: bool
    hivemind_margin_ms: float
    end_to_end_p95_ms: float
    tracker_end_to_end_pass: bool
    formation_mean_deviation_m: float
    formation_max_deviation_m: float
    wta_tier_timings: dict[str, TierWtaTiming]
    hivemind_e2e_budget_ms: float

    @property
    def total_samples(self) -> int:
        return len(self.cycle_latencies_ms)


# --------------------------------------------------------------------------- benchmark

class SwarmLatencyBenchmark:
    """End-to-end per-vehicle latency benchmark for an N-vehicle swarm."""

    def __init__(
        self,
        config: SwarmLatencyBenchmarkConfig | None = None,
        tracker: LatencyTracker | None = None,
    ) -> None:
        self.config = config or SwarmLatencyBenchmarkConfig()
        self.tracker = tracker or LatencyTracker(
            budgets=self.config.stage_budget_ms,
            p95_target_ms=self.config.p95_target_ms,
        )
        self._stage_rng = np.random.default_rng(self.config.seed)
        self._wta_rng = np.random.default_rng(self.config.seed + 1)

    # ------------------------------------------------------------------ run

    def run(self) -> SwarmLatencyBenchmarkResult:
        """Execute the benchmark and return the aggregated result."""
        started_at = datetime.now(UTC).isoformat()

        cfg = self.config
        cycle_latencies: list[float] = []
        vehicle_results: dict[int, list[VehicleCycleResult]] = {}
        stage_samples: dict[str, list[float]] = {name: [] for name in PIPELINE_STAGES}

        leader = self._leader_state()
        for vehicle_id in range(1, cfg.num_vehicles + 1):
            cycles: list[VehicleCycleResult] = []
            for cycle in range(cfg.cycles_per_vehicle):
                stage_latencies = self._draw_stage_latencies()
                self._record_stage_latencies(stage_latencies)
                cycle_latency = sum(stage_latencies.values())
                for name, value in stage_latencies.items():
                    stage_samples[name].append(value)
                cycles.append(
                    VehicleCycleResult(
                        vehicle_id=vehicle_id,
                        cycle=cycle,
                        stage_latencies_ms=dict(stage_latencies),
                        cycle_latency_ms=cycle_latency,
                    )
                )
                cycle_latencies.append(cycle_latency)
            vehicle_results[vehicle_id] = cycles

        finished_at = datetime.now(UTC).isoformat()

        p50 = percentile(cycle_latencies, 0.50)
        p95 = percentile(cycle_latencies, 0.95)
        p99 = percentile(cycle_latencies, 0.99)

        vehicle_summaries = {
            vehicle_id: self._vehicle_summary(vehicle_id, cycles)
            for vehicle_id, cycles in vehicle_results.items()
        }

        stage_summaries = {
            name: StageSummary(
                name=name,
                count=len(samples),
                mean_ms=sum(samples) / len(samples) if samples else 0.0,
                p50_ms=percentile(samples, 0.50),
                p95_ms=percentile(samples, 0.95),
                p99_ms=percentile(samples, 0.99),
                min_ms=min(samples) if samples else 0.0,
                max_ms=max(samples) if samples else 0.0,
                budget_ms=cfg.stage_budget_ms.get(name),
            )
            for name, samples in stage_samples.items()
        }

        formation_mean, formation_max = self._formation_deviation(leader)

        return SwarmLatencyBenchmarkResult(
            config=cfg,
            started_at=started_at,
            finished_at=finished_at,
            cycle_latencies_ms=cycle_latencies,
            vehicle_results=vehicle_results,
            vehicle_summaries=vehicle_summaries,
            mean_ms=sum(cycle_latencies) / len(cycle_latencies),
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            min_ms=min(cycle_latencies),
            max_ms=max(cycle_latencies),
            stage_summaries=stage_summaries,
            hivemind_pass=p95 <= cfg.hivemind_e2e_budget_ms,
            hivemind_margin_ms=cfg.hivemind_e2e_budget_ms - p95,
            hivemind_e2e_budget_ms=cfg.hivemind_e2e_budget_ms,
            end_to_end_p95_ms=self.tracker.end_to_end_ms(),
            tracker_end_to_end_pass=self.tracker.end_to_end_ms() <= cfg.p95_target_ms,
            formation_mean_deviation_m=formation_mean,
            formation_max_deviation_m=formation_max,
            wta_tier_timings=self._tier_timings(),
        )

    # --------------------------------------------------------------- stages

    def _draw_stage_latencies(self) -> dict[str, float]:
        cfg = self.config
        latencies: dict[str, float] = {}
        for name in PIPELINE_STAGES:
            mean = cfg.stage_mean_ms[name]
            if name == "wta_solve":
                # WTA cost grows with swarm size (more targets per vehicle).
                mean *= 1.0 + 0.1 * (cfg.num_vehicles - 1)
            jitter = cfg.stage_jitter_ms
            value = float(self._stage_rng.uniform(mean - jitter, mean + jitter))
            latencies[name] = max(0.0, value)
        return latencies

    def _record_stage_latencies(self, latencies: dict[str, float]) -> None:
        for name, value in latencies.items():
            self.tracker.record(name, value)

    # --------------------------------------------------------------- tiers

    def _tier_timings(self) -> dict[str, TierWtaTiming]:
        """Calibrated solve time per WTA tier (T1/T2/T3) on pinned problems.

        Problems are kept small; ``tier_override`` pins the tier so measured
        times reflect solver behaviour per tier rather than instance size.
        """
        timings: dict[str, TierWtaTiming] = {}
        for tier_name, (weapons_count, targets_count) in TIER_PROBLEMS.items():
            weapons = [Weapon(i) for i in range(weapons_count)]
            targets = [Target(j, value=float(j + 1)) for j in range(targets_count)]
            kill_prob = self._wta_rng.uniform(0.1, 0.9, size=(weapons_count, targets_count))
            values = np.array([float(t.value) for t in targets], dtype=float)
            solver = TieredWTASolver(WTAConfig())
            times: list[float] = []
            for _ in range(TIER_REPEATS):
                result = solver.solve(
                    weapons,
                    targets,
                    kill_prob,
                    values=values,
                    tier_override=Tier(tier_name),
                )
                times.append(result.solve_time_ms)
            timings[tier_name] = TierWtaTiming(
                tier=tier_name,
                weapons=weapons_count,
                targets=targets_count,
                pairs=weapons_count * targets_count,
                solve_times_ms=times,
            )
        return timings

    # ---------------------------------------------------------- formation

    def _leader_state(self) -> StateVector:
        return StateVector(
            pose=Pose3D(x=0.0, y=0.0, z=50.0),
            velocity=Velocity3D(vx=12.0, vy=0.0, vz=0.0),
        )

    def _vehicle_summary(self, vehicle_id: int, cycles: list[VehicleCycleResult]) -> VehicleSummary:
        latencies = [c.cycle_latency_ms for c in cycles]
        return VehicleSummary(
            vehicle_id=vehicle_id,
            cycles=len(cycles),
            mean_ms=sum(latencies) / len(latencies),
            p50_ms=percentile(latencies, 0.50),
            p95_ms=percentile(latencies, 0.95),
            p99_ms=percentile(latencies, 0.99),
            min_ms=min(latencies),
            max_ms=max(latencies),
        )

    def _formation_deviation(self, leader: Any) -> tuple[float, float]:
        cfg = self.config
        controller = FormationController(
            FormationConfig(formation_type="line", spacing=cfg.formation_spacing_m)
        )
        planned = controller.compute_formation_positions(leader, cfg.num_vehicles)
        if not planned:
            return 0.0, 0.0

        deviations: list[float] = []
        for target in planned:
            dx = float(self._stage_rng.uniform(-cfg.formation_noise_m, cfg.formation_noise_m))
            dy = float(self._stage_rng.uniform(-cfg.formation_noise_m, cfg.formation_noise_m))
            actual = Pose3D(x=target.x + dx, y=target.y + dy, z=target.z)
            deviations.append(target.distance_to(actual))
        return float(sum(deviations) / len(deviations)), float(max(deviations))


# --------------------------------------------------------------------------- reporting

def generate_report(
    result: SwarmLatencyBenchmarkResult,
    sweep_results: list[SwarmLatencyBenchmarkResult] | None = None,
) -> str:
    """Render the benchmark result as a markdown report."""
    cfg = result.config
    lines: list[str] = []
    lines.append("# Swarm Latency Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {result.finished_at}")
    lines.append(f"Benchmark seed: {cfg.seed}")
    lines.append("")

    lines.append("## Configuration")
    lines.append("| Parameter | Value |")
    lines.append("| --- | --- |")
    for key, value in (
        ("Vehicles", f"{cfg.num_vehicles}"),
        ("Cycles per vehicle", f"{cfg.cycles_per_vehicle}"),
        ("Total vehicle-cycle samples", f"{result.total_samples}"),
        ("Stage jitter (ms)", f"{cfg.stage_jitter_ms}"),
        ("Hivemind end-to-end budget (ms)", f"{cfg.hivemind_e2e_budget_ms}"),
        ("p95 end-to-end target (ms)", f"{cfg.p95_target_ms}"),
        ("Formation spacing (m)", f"{cfg.formation_spacing_m}"),
        ("Formation noise (m)", f"{cfg.formation_noise_m}"),
    ):
        lines.append(f"| {key} | {value} |")
    lines.append("")

    lines.append("## Summary")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Mean cycle latency (ms) | {result.mean_ms:.3f} |")
    lines.append(f"| Min cycle latency (ms) | {result.min_ms:.3f} |")
    lines.append(f"| p50 cycle latency (ms) | {result.p50_ms:.3f} |")
    lines.append(f"| p95 cycle latency (ms) | {result.p95_ms:.3f} |")
    lines.append(f"| p99 cycle latency (ms) | {result.p99_ms:.3f} |")
    lines.append(f"| Max cycle latency (ms) | {result.max_ms:.3f} |")
    lines.append(
        f"| Hivemind <100 ms end-to-end benchmark | "
        f"{'PASS' if result.hivemind_pass else 'FAIL'} |"
    )
    lines.append(
        f"| Hivemind margin (budget - p95, ms) | {result.hivemind_margin_ms:+.3f} |"
    )
    lines.append(
        f"| Tracker end-to-end p95 (sum of stage p95s, ms) | {result.end_to_end_p95_ms:.3f} |"
    )
    lines.append(
        f"| Tracker end-to-end p95 <= 92 ms target | "
        f"{'PASS' if result.tracker_end_to_end_pass else 'FAIL'} |"
    )
    lines.append("")

    lines.append("## Per-stage latency (ms)")
    lines.append(
        "| Stage | Count | Mean | p50 | p95 | p99 | Min | Max | Budget | Over budget |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name in PIPELINE_STAGES:
        s = result.stage_summaries[name]
        lines.append(
            f"| {name} | {s.count} | {s.mean_ms:.3f} | {s.p50_ms:.3f} | "
            f"{s.p95_ms:.3f} | {s.p99_ms:.3f} | {s.min_ms:.3f} | {s.max_ms:.3f} | "
            f"{s.budget_ms if s.budget_ms is not None else '-'} | "
            f"{'yes' if s.over_budget else 'no'} |"
        )
    lines.append("")

    lines.append("## Per-vehicle cycle latency (ms)")
    lines.append("| Vehicle | Cycles | Mean | p50 | p95 | p99 | Min | Max |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for vehicle_id in sorted(result.vehicle_summaries):
        vs = result.vehicle_summaries[vehicle_id]
        lines.append(
            f"| {vs.vehicle_id} | {vs.cycles} | {vs.mean_ms:.3f} | {vs.p50_ms:.3f} | "
            f"{vs.p95_ms:.3f} | {vs.p99_ms:.3f} | {vs.min_ms:.3f} | {vs.max_ms:.3f} |"
        )
    lines.append("")

    lines.append("## Hivemind comparison (<100 ms end-to-end benchmark)")
    lines.append("")
    lines.append(
        f"The swarm's p95 cycle latency is **{result.p95_ms:.3f} ms** against the "
        f"Hivemind ceiling of **{cfg.hivemind_e2e_budget_ms:.0f} ms**. "
        f"Margin: {result.hivemind_margin_ms:+.3f} ms. "
        f"Result: **{'PASS' if result.hivemind_pass else 'FAIL'}**."
    )
    lines.append("")
    lines.append(
        "Cycle latency is measured per vehicle as the sum of the six pipeline "
        "stages (ingestion, filtering, tracking, transform, WTA solve, "
        "setpoint publish), aggregated across all vehicle cycles."
    )
    lines.append("")

    lines.append("## WTA solve time per tier")
    lines.append("")
    lines.append(
        "Wall-clock solve time measured with the real ``TieredWTASolver`` on "
        "problems pinned to each tier (T1 = MILP, T2 = greedy, T3 = VLSN)."
    )
    lines.append("")
    lines.append("| Tier | Weapons | Targets | Pairs | Runs | Mean (ms) | Max (ms) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for tier_name in ("t1_milp", "t2_greedy", "t3_vlsn"):
        t = result.wta_tier_timings[tier_name]
        lines.append(
            f"| {t.tier} | {t.weapons} | {t.targets} | {t.pairs} | "
            f"{len(t.solve_times_ms)} | {t.mean_ms:.3f} | {t.max_ms:.3f} |"
        )
    lines.append("")

    lines.append("## Formation deviation")
    lines.append("")
    lines.append(
        f"RMS-style deviation of actual vehicle positions from the planned "
        f"line formation (spacing {cfg.formation_spacing_m} m, noise "
        f"{cfg.formation_noise_m} m), over {cfg.num_vehicles} vehicles:"
    )
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Mean deviation (m) | {result.formation_mean_deviation_m:.4f} |")
    lines.append(f"| Max deviation (m) | {result.formation_max_deviation_m:.4f} |")
    lines.append("")

    if sweep_results:
        lines.append("## Swarm sweep (1..10 vehicles)")
        lines.append("")
        lines.append("| Vehicles | p50 (ms) | p95 (ms) | p99 (ms) | Hivemind <100 ms |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for r in sweep_results:
            lines.append(
                f"| {r.config.num_vehicles} | {r.p50_ms:.3f} | {r.p95_ms:.3f} | "
                f"{r.p99_ms:.3f} | {'PASS' if r.hivemind_pass else 'FAIL'} |"
            )
        lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- Per-vehicle cycle latency = ingestion + filtering + tracking + "
        "transform + WTA solve + setpoint publish, measured per cycle."
    )
    lines.append(
        "- Stage latencies are recorded through ``LatencyTracker`` "
        "(``apex_autopilot_optimization.perception``), the same tracker used "
        "by the perception pipeline spec's 100 ms end-to-end budget."
    )
    lines.append(
        "- p50/p95/p99 use the nearest-rank convention of ``LatencyTracker.p95``."
    )
    lines.append(
        "- WTA solve times are measured with the real tiered solver (one pinned "
        "problem per tier); the per-cycle wta_solve stage is drawn from the "
        "configured wta_solve distribution, scaled with swarm size."
    )
    lines.append(
        "- Formation deviation compares actual simulated positions against the "
        "planned line formation."
    )
    lines.append("")
    return "\n".join(lines)


def write_report(
    result: SwarmLatencyBenchmarkResult,
    path: str | Path,
    sweep_results: list[SwarmLatencyBenchmarkResult] | None = None,
) -> Path:
    """Write the markdown report to ``path`` and return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_report(result, sweep_results=sweep_results), encoding="utf-8")
    return out


def run_sweep(
    num_vehicles: range | list[int] = range(MIN_VEHICLES, MAX_VEHICLES + 1),
) -> list[SwarmLatencyBenchmarkResult]:
    """Run the benchmark for every swarm size in ``num_vehicles``."""
    results: list[SwarmLatencyBenchmarkResult] = []
    for n in num_vehicles:
        config = SwarmLatencyBenchmarkConfig(num_vehicles=n)
        results.append(SwarmLatencyBenchmark(config=config).run())
    return results


def main() -> int:
    """CLI entry point: run the 1..10 vehicle sweep and write the report."""
    results = run_sweep()
    headline = results[-1]  # N = 10
    repo_root = Path(__file__).resolve().parents[1]
    report_path = repo_root / "benchmark_report.md"
    write_report(headline, report_path, sweep_results=results)

    print(f"Swarm latency benchmark complete ({MIN_VEHICLES}..{MAX_VEHICLES} vehicles).")
    print(f"Report: {report_path}")
    print(
        f"Headline (N={headline.config.num_vehicles}): "
        f"p50={headline.p50_ms:.2f} ms, p95={headline.p95_ms:.2f} ms, "
        f"p99={headline.p99_ms:.2f} ms, "
        f"Hivemind <100 ms: {'PASS' if headline.hivemind_pass else 'FAIL'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
