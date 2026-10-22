# Swarm Scalability Benchmark Report (100 vehicles)

Generated: 2026-10-22T02:16:14.606151+00:00
Backend: mocked ``MAVLinkBridge(simulation=True)`` (no Gazebo/PX4 required)
Benchmark seed: 42

## Configuration
| Parameter | Value |
| --- | --- |
| Vehicle counts | 1, 10, 50, 100 |
| Steps per mission | 25 (dt = 0.05 s) |
| Repeats | 3 |
| Inter-vehicle spacing (m) | 10.0 |
| Min separation (m) | 2.0 |
| Cycle budget (ms) | 100.0 |
| Wall-time cycle gate (ms) | 200.0 |
| Instrumented p95 gate (ms) | 150.0 |
| WTA vehicle counts | 10, 50, 100 |
| WTA problem size | 4 weapons x 6 targets |
| WTA steps per mission | 8 |

## Swarm mission sweep (mocked backends)

| Vehicles | Repeats | Wall/cycle (ms) mean/max | Instr. p95 cycle (ms) | Success rate | Makespan (s) | Safety violations | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 0.15 / 0.18 | 0.14 | 1.00 | 1.250 | 0 | PASS |
| 10 | 3 | 2.26 / 2.96 | 1.73 | 1.00 | 1.250 | 0 | PASS |
| 50 | 3 | 31.90 / 34.45 | 16.30 | 1.00 | 1.250 | 0 | PASS |
| 100 | 3 | 92.35 / 93.86 | 50.01 | 1.00 | 1.250 | 0 | PASS |

### N = 100 detail

| Metric | Value |
| --- | --- |
| Wall time per cycle | 93.86 ms (gate < 200 ms) |
| Runner-instrumented p95 cycle | 53.72 ms (gate < 150 ms) |
| Runner-instrumented mean cycle | 34.02 ms |
| Successful missions | 2500 / 2500 |
| Makespan | 1.250 s (25 steps x 0.05 s) |
| Safety violations | 0 |
| Formation deviation (m) | 574.2000 |
| Connected at end | 100 / 100 |
| Teardown (all bridges/sims disconnected) | True |

## WTA batch mission sweep (sequential per-vehicle solves)

| Vehicles | Steps | Wall/cycle (ms) | Cycles over 100 ms budget | Success |
| --- | ---: | ---: | ---: | ---: |
| 10 | 8 | 167.2 | 8 / 8 | True |
| 50 | 8 | 816.9 | 8 / 8 | True |
| 100 | 8 | 1460.4 | 8 / 8 | True |

Note: the per-vehicle WTA solve loop inside ``run_wta_batch_mission`` is sequential, so cycle time grows roughly linearly with N for fixed-size problems; a single 4x6 T1 MILP solve is ~14 ms mean on this host, which puts a 100-vehicle cycle well over the 100 ms budget without parallel solves or smaller problems. Functional correctness (all vehicles complete, guaranteed teardown) holds at N=100.

## Component timing (O(N^2) components)

### SwarmSafetyFilter (pairwise collision avoidance)

| Vehicles | Samples | Mean filter call (ms) | p95 (ms) | Max (ms) |
| --- | ---: | ---: | ---: | ---: |
| 10 | 50 | 0.226 | 0.396 | 0.539 |
| 50 | 50 | 6.205 | 6.989 | 7.209 |
| 100 | 50 | 20.412 | 27.836 | 28.511 |
| 200 | 50 | 20.336 | 102.288 | 111.364 |

### FormationSetpointGenerator (formation slot computation)

| Agents | Samples | Mean compute (ms) | p95 (ms) |
| --- | ---: | ---: | ---: |
| 10 | 100 | 0.0090 | 0.0093 |
| 50 | 100 | 0.0488 | 0.0831 |
| 100 | 100 | 0.0968 | 0.1270 |

## Findings

- At N=100 the mocked swarm completes all 25 steps with 100% success, full teardown, and zero safety violations (10 m spacing vs 2 m min separation).
- Wall time per cycle at N=100 is 93.9 ms (runner-instrumented p95 53.7 ms), dominated by the O(N^2) safety filter and per-vehicle stats recording; the p95 component timing below shows where the quadratic growth lives.
- Gazebo SITL remains limited to under 10 vehicles per instance (~4 GB RAM each); the 100-vehicle scale point is therefore validated with mocked backends, per the spec's no-op fallback path.
- Formation deviation at N=100 is large (574 m) because mocked backends return static states: vehicles never advance toward their formation slots, so deviation reflects mock placement, not a control failure. Missions still succeed and teardown is guaranteed.

## Methodology

- Every swarm mission runs ``SwarmRunner.run_swarm_mission`` with mocked ``MAVLinkBridge``/``SimulationInterface`` backends; wall time is measured around the whole mission and divided by the number of executed steps.
- ``internal p95 cycle`` is the runner's own ``time.perf_counter()`` cycle measurement (recorded per vehicle per cycle via ``SwarmStatsAggregator``).
- Port namespacing (5760 + i*10 master, 5501 + i*10 SITL) is exercised up to slot 99; all 200 ports are bind-tested in the companion test suite.
