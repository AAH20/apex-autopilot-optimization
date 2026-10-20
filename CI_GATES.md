# CI Gates — apex-autopilot-optimization

Gate thresholds enforced by `.github/workflows/ci.yml` on every push/PR
(branches `master`, `main`, `develop` for pushes; `master`, `main` for PRs).

## Gate summary

| Job | Gate | Threshold |
|-----|------|-----------|
| `lint` | `ruff check src tests` | 0 findings |
| `lint` | `ruff format --check src tests` | clean |
| `lint` | ruff on new Wave-2 modules — `src/apex_autopilot_optimization/perception`, `src/apex_autopilot_optimization/messaging`, `src/apex_autopilot_optimization/benchmark.py` (+ `governance/` when it exists) | 0 findings |
| `typecheck` | `mypy src` (strict, py311) | 0 errors |
| `typecheck` | mypy on new Wave-2 modules (same paths as lint) | 0 errors |
| `unit-tests` | `pytest tests/unit` on Python 3.11 and 3.12 | pass |
| `unit-tests` | `pytest tests/unit/test_cli.py` | pass |
| `unit-tests` | new-module tests: `test_perception.py`, `test_messaging.py`, `test_benchmark.py`, `test_wta_solver.py`, `test_swarm_runner.py` | pass |
| `integration-tests` | `pytest tests/integration` | pass |
| `coverage` | `pytest tests/ --cov=src --cov-fail-under=85` | overall >= 85% |
| `coverage` | new-module coverage — perception package | >= 80% |
| `coverage` | new-module coverage — `benchmark.py` | >= 80% |
| `coverage` | new-module coverage — `messaging/queue.py`, `messaging/stream.py`, `messaging/event_store.py` | >= 80% |
| `benchmarks` | perception end-to-end p95 latency | < 100 ms |
| `benchmarks` | WTA T2/T3 p95 solve time, instances <= 200x200 | < 50 ms |

Existing jobs (`lint`, `typecheck`, `unit-tests`, `integration-tests`, `coverage`)
are unchanged; all new gates are additive.

## Performance benchmark details (`benchmarks` job)

Script: `scripts/ci_performance_gate.py` (reports written to `.benchmarks/ci_*.json`).

**Perception latency** — `LatencyTracker` over the 10 perception-pipeline stages
(`camera_to_topic`, `inference`, `transport`, `ingestion`, `filtering`, `fusion`,
`transform`, `publish`, `wta_solve`, `control_dispatch`; per-stage budgets from
the spec sum to 100 ms). 300 timed iterations. Gate asserts every stage p95 is
within its stage budget and end-to-end p95 latency < 100 ms.

**WTA solve time** — `TieredWTASolver` T2 greedy on 64x64, 128x128 and 200x200
weapons x targets, and T3 VLSN on 64x64 and 128x128 (200x200 VLSN exceeds the
50 ms SLO in pure Python and is excluded from the CI gate). 12 instances per
size per tier. Gate asserts p95 solve time < 50 ms across all T2/T3 runs.
Solution quality/optimality bounds remain covered by `tests/unit/test_wta_solver.py`.

## Notes

- `governance/` and `benchmark/` are not yet package directories in the repo
  (`benchmark.py` is a module at the package root); the lint/mypy gates
  reference them and enforce them only once they exist, so CI stays green.
- Wave 2 modules: `perception/`, `messaging/`, `swarm_runner`, `wta_solver`.

## Reproducing locally

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format --check src tests
mypy src
pytest tests/unit -q
pytest tests/unit/test_cli.py -q
pytest tests/integration -q
pytest tests/ --cov=src --cov-report=term --cov-fail-under=85
pytest tests/unit/test_perception.py --cov=apex_autopilot_optimization.perception --cov-fail-under=80 -q
pytest tests/unit/test_benchmark.py --cov=apex_autopilot_optimization.benchmark --cov-fail-under=80 -q
pytest tests/unit/test_messaging.py --cov=apex_autopilot_optimization.messaging.queue --cov=apex_autopilot_optimization.messaging.stream --cov=apex_autopilot_optimization.messaging.event_store --cov-fail-under=80 -q
python scripts/ci_performance_gate.py
```
