# Changelog — apex-autopilot-optimization

All notable changes to `apex-autopilot-optimization` are documented here.

## [1.0.0] — 2026-10-22 — Production release

First production-stable release of the optimization/governance layer for the Option B autonomous swarm stack (AAS sim/runtime at the ROS2/ZMQ network boundary; apex AGPL-3.0 optimization & governance).

### Highlights
- **Tiered WTA solver** — T1 MILP / T2 greedy / T3 VLSN with documented approximation ratios; T3 VLSN clears the 50 ms SLO at 200x200 (p95 ~44-50 ms).
- **Combat reallocator** — SLS/SSL state machine with BDA-driven residual re-solves, integrated into the SwarmRunner batch mission loop.
- **Multi-vehicle swarm runner** — N-vehicle MAVLink port namespacing (5760+i×10 / 5501+i×10), safety filter (TLA+/TLC-verified CBF invariants), formation integration, Gazebo SITL launcher.
- **Perception pipeline** — YOLO ingestion, EWMA tracking, COCO→WTA class mapping, end-to-end p95 latency ~0.2 ms (SLO < 100 ms).
- **ISO 42001 agent-exec policy engine** — veto emission, HITL integration, autonomous planner role enforcement.
- **CI performance gates** — perception < 100 ms, WTA T2/T3 < 50 ms, enforced on every push/PR.
- **Tenancy & packaging** — tenant tiers (free/pro/enterprise), organization sizing profiles (startup → large enterprise), example Helm/Kubernetes/Terraform deployment configs.
- **SDK & CLI** — `apex-autopilot` entry point, Python SDK client, setup wizard, diagnostics, onboarding checklists.

### Verified quality (v1.0.0)
- 2607 tests passing (unit + integration), Python 3.11 & 3.12
- Coverage 91.06% (gate >= 85%); new-module coverage >= 80%
- mypy strict clean on 254 source files; ruff check + format clean
- Performance gate: PASSED (perception p95 0.22 ms < 100 ms; WTA p95 47.83 ms < 50 ms)

### Breaking changes
None vs. 0.1.0 — all public APIs are stable from this release forward. Semantic versioning applies: major bumps only on breaking changes.

### Migration
No migration required from 0.1.0; `pip install -U apex-autopilot-optimization==1.0.0` is a drop-in upgrade.

## [0.1.0] — 2026-10-04 — Initial alpha release

Initial wave-1 alpha: core types, planners (A*/RRT/PRM/Hybrid A*), minimum-snap optimizer, EKF estimator, MPC controller, CBF safety filter, WTA solver, swarm runner, perception, messaging adapters, governance, CLI, and full CI gate suite.
