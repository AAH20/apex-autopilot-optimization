"""CI gate for the 100-vehicle swarm scalability benchmark.

Runs a focused mocked-backend swarm mission at N=100 and gates on cycle
latency, success rate, and guaranteed teardown. Intended as an additive
check alongside scripts/ci_performance_gate.py; Gazebo SITL cannot reach
100 vehicles (~4 GB RAM per instance, under 10 vehicles practical limit),
so this uses the spec's no-op fallback path (MAVLinkBridge simulation mode).

Exit codes: 0 = pass, 1 = fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Regression gates, grounded in measured runs (see benchmark_reports/):
# N=100 mocked wall time ~93 ms/cycle, instrumented p95 ~47 ms.
WALL_CYCLE_GATE_MS = 250.0
INTERNAL_P95_GATE_MS = 150.0


def main() -> int:
    from benchmark.swarm_scalability_benchmark import (
        ScalabilityConfig,
        SwarmScalabilityBenchmark,
    )

    config = ScalabilityConfig(
        vehicle_counts=(100,),
        steps_per_mission=15,
        repeats=1,
        dt=0.05,
        spacing_m=10.0,
        min_separation_m=2.0,
        wall_budget_ms=WALL_CYCLE_GATE_MS,
        internal_p95_budget_ms=INTERNAL_P95_GATE_MS,
    )
    result = SwarmScalabilityBenchmark(config=config).run()

    hundred = result.n100
    if hundred is None or not hundred.samples:
        print("SCALABILITY GATE FAIL: no N=100 sample produced", file=sys.stderr)
        return 1

    sample = hundred.samples[0]
    checks = [
        ("N=100 mission success", sample.success),
        ("success rate == 1.0", hundred.success_rate == 1.0),
        (f"wall/cycle < {WALL_CYCLE_GATE_MS:.0f} ms", sample.per_cycle_ms < WALL_CYCLE_GATE_MS),
        (
            f"instrumented p95 cycle < {INTERNAL_P95_GATE_MS:.0f} ms",
            sample.internal_p95_ms < INTERNAL_P95_GATE_MS,
        ),
        ("all bridges/sims disconnected", sample.disconnects_ok),
        ("connected at end == 100", sample.connected_end == 100),
        ("zero safety violations", sample.safety_violations == 0),
    ]

    print("100-vehicle scalability gate:")
    all_ok = True
    for name, ok in checks:
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(
        f"  N=100: {sample.per_cycle_ms:.1f} ms/cycle wall, "
        f"{sample.internal_p95_ms:.1f} ms p95 instrumented, "
        f"success={sample.success}, teardown={sample.disconnects_ok}"
    )
    print(f"100-vehicle scalability gate: {'PASS' if all_ok and result.overall_pass else 'FAIL'}")
    return 0 if (all_ok and result.overall_pass) else 1


if __name__ == "__main__":
    raise SystemExit(main())
