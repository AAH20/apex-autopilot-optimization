# Swarm Latency Benchmark Report

Generated: 2026-10-19T23:25:11.823444+00:00
Benchmark seed: 42

## Configuration
| Parameter | Value |
| --- | --- |
| Vehicles | 10 |
| Cycles per vehicle | 50 |
| Total vehicle-cycle samples | 500 |
| Stage jitter (ms) | 1.5 |
| Hivemind end-to-end budget (ms) | 100.0 |
| p95 end-to-end target (ms) | 92.0 |
| Formation spacing (m) | 2.0 |
| Formation noise (m) | 0.05 |

## Summary
| Metric | Value |
| --- | --- |
| Mean cycle latency (ms) | 23.291 |
| Min cycle latency (ms) | 17.013 |
| p50 cycle latency (ms) | 23.211 |
| p95 cycle latency (ms) | 26.628 |
| p99 cycle latency (ms) | 28.076 |
| Max cycle latency (ms) | 29.149 |
| Hivemind <100 ms end-to-end benchmark | PASS |
| Hivemind margin (budget - p95, ms) | +73.372 |
| Tracker end-to-end p95 (sum of stage p95s, ms) | 31.387 |
| Tracker end-to-end p95 <= 92 ms target | PASS |

## Per-stage latency (ms)
| Stage | Count | Mean | p50 | p95 | p99 | Min | Max | Budget | Over budget |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ingestion | 500 | 1.479 | 1.475 | 2.820 | 2.967 | 0.002 | 2.996 | 2.0 | yes |
| filtering | 500 | 2.503 | 2.529 | 3.852 | 3.981 | 1.007 | 3.997 | 4.0 | no |
| tracking | 500 | 1.977 | 1.944 | 3.348 | 3.479 | 0.503 | 3.499 | 3.0 | yes |
| transform | 500 | 2.503 | 2.440 | 3.850 | 3.958 | 1.022 | 3.981 | 4.0 | no |
| wta_solve | 500 | 13.323 | 13.301 | 14.699 | 14.779 | 11.812 | 14.798 | 12.0 | yes |
| publish | 500 | 1.505 | 1.523 | 2.819 | 2.973 | 0.002 | 2.991 | 2.0 | yes |

## Per-vehicle cycle latency (ms)
| Vehicle | Cycles | Mean | p50 | p95 | p99 | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 50 | 23.060 | 22.794 | 26.458 | 29.149 | 19.284 | 29.149 |
| 2 | 50 | 23.396 | 23.864 | 26.303 | 26.815 | 19.572 | 26.815 |
| 3 | 50 | 23.250 | 23.170 | 27.203 | 28.125 | 17.170 | 28.125 |
| 4 | 50 | 23.502 | 23.178 | 26.683 | 28.242 | 17.013 | 28.242 |
| 5 | 50 | 23.261 | 23.061 | 26.609 | 27.843 | 18.098 | 27.843 |
| 6 | 50 | 23.594 | 23.176 | 27.179 | 28.289 | 19.786 | 28.289 |
| 7 | 50 | 23.124 | 22.918 | 27.096 | 28.076 | 18.972 | 28.076 |
| 8 | 50 | 22.912 | 22.918 | 26.177 | 27.594 | 17.683 | 27.594 |
| 9 | 50 | 23.808 | 23.770 | 27.657 | 28.162 | 19.048 | 28.162 |
| 10 | 50 | 23.007 | 23.092 | 26.062 | 27.641 | 18.924 | 27.641 |

## Hivemind comparison (<100 ms end-to-end benchmark)

The swarm's p95 cycle latency is **26.628 ms** against the Hivemind ceiling of **100 ms**. Margin: +73.372 ms. Result: **PASS**.

Cycle latency is measured per vehicle as the sum of the six pipeline stages (ingestion, filtering, tracking, transform, WTA solve, setpoint publish), aggregated across all vehicle cycles.

## WTA solve time per tier

Wall-clock solve time measured with the real ``TieredWTASolver`` on problems pinned to each tier (T1 = MILP, T2 = greedy, T3 = VLSN).

| Tier | Weapons | Targets | Pairs | Runs | Mean (ms) | Max (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| t1_milp | 4 | 6 | 24 | 3 | 39.148 | 40.531 |
| t2_greedy | 16 | 16 | 256 | 3 | 0.330 | 0.358 |
| t3_vlsn | 30 | 30 | 900 | 3 | 81.558 | 81.841 |

## Formation deviation

RMS-style deviation of actual vehicle positions from the planned line formation (spacing 2.0 m, noise 0.05 m), over 10 vehicles:

| Metric | Value |
| --- | --- |
| Mean deviation (m) | 0.0408 |
| Max deviation (m) | 0.0606 |

## Swarm sweep (1..10 vehicles)

| Vehicles | p50 (ms) | p95 (ms) | p99 (ms) | Hivemind <100 ms |
| --- | ---: | ---: | ---: | ---: |
| 1 | 16.494 | 20.158 | 22.849 | PASS |
| 2 | 17.839 | 20.703 | 22.007 | PASS |
| 3 | 18.344 | 21.695 | 23.225 | PASS |
| 4 | 19.030 | 22.395 | 23.925 | PASS |
| 5 | 19.685 | 23.109 | 24.625 | PASS |
| 6 | 20.385 | 23.817 | 25.325 | PASS |
| 7 | 21.085 | 24.583 | 26.025 | PASS |
| 8 | 21.779 | 25.217 | 26.676 | PASS |
| 9 | 22.530 | 25.983 | 27.425 | PASS |
| 10 | 23.211 | 26.628 | 28.076 | PASS |

## Methodology

- Per-vehicle cycle latency = ingestion + filtering + tracking + transform + WTA solve + setpoint publish, measured per cycle.
- Stage latencies are recorded through ``LatencyTracker`` (``apex_autopilot_optimization.perception``), the same tracker used by the perception pipeline spec's 100 ms end-to-end budget.
- p50/p95/p99 use the nearest-rank convention of ``LatencyTracker.p95``.
- WTA solve times are measured with the real tiered solver (one pinned problem per tier); the per-cycle wta_solve stage is drawn from the configured wta_solve distribution, scaled with swarm size.
- Formation deviation compares actual simulated positions against the planned line formation.
