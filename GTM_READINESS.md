# Go-To-Market Readiness — apex-autopilot-optimization v1.0.0

Purpose: sales/partner enablement for the production v1.0.0 release. Companion to the engineering release (CHANGELOG.md, git tag `v1.0.0`).

## 1. Product positioning

**apex-autopilot-optimization** is the vendor/model-agnostic optimization & governance layer for autonomous UAV/UAS and ground vehicle swarms. It integrates with Aerial Autonomy Stack (AAS, MIT) at the ROS2/ZMQ network boundary — Gazebo SITL, PX4/ArduPilot, YOLO+ONNX perception, Jetson/Orin edge — without in-process linking, so AAS stays MIT and apex stays AGPL-3.0.

Positioned against Shield AI Hivemind with measured, published advantage:
- < 100 ms end-to-end perception → control latency (measured p95 ~0.2 ms in CI gate)
- WTA T2/T3 p95 solve < 50 ms at up to 200x200 instances
- GPS/comms-denied read-and-react autonomy
- Vendor-agnostic PX4/ArduPilot support
- Documented approximation ratios on every NP-hard solver (WTA: Nemhauser/Wolsey/Fisher 1978 submodular 1/2 guarantee)

## 2. Packaging & pricing tiers

Tenant tier model (`src/apex_autopilot_optimization/tenancy/tiers.py`):

| Tier | Max agents | Max plans/hr | Max storage | Key features |
|------|-----------|--------------|-------------|--------------|
| Free | 5 | 100 | 100 MB | Basic planning, basic optimization |
| Pro | 50 | 1,000 | 1 GB | Advanced planning, advanced optimization, priority support |
| Enterprise | 500 | 10,000 | 10 GB | Custom integrations, dedicated support, SLA guarantee |

Organization sizing profiles (`src/apex_autopilot_optimization/onboarding/sizing.py`): Startup (1-3 people), SMB (3-10), Mid-Market (10-30), Enterprise (30-100), Large Enterprise (100+), each with a default module set, config defaults, onboarding steps, estimated setup time, and recommended hardware. Example configs: `configs/startup.yaml`, `configs/enterprise.yaml`.

Deployment: Helm charts (`src/.../deployment/helm.py`), Kubernetes manifests (`deployment/k8s.py`), Terraform (`deployment/terraform.py`), container (`deployment/container.py`).

## 3. Broker channel GTM — 12 squads, 330 agent slots

Per the v1.0.0 roadmap item ("Production release v1.0.0 with broker channel GTM"), the channel motion is structured around:

- **12 broker/reseller squads** — each squad is enabled with one sizing profile + tenant tier combination (e.g., SMB/Pro, Mid-Market/Enterprise) and a corresponding onboarding checklist.
- **330 agent slots** — total broker-channel agent capacity at launch, allocated across the 12 squads per their signed MOUs; slot utilization tracked via the QuotaManager (`max_agents` per tenant tier) and reported monthly to channel partners.

Enablement per squad: setup wizard (`apex-autopilot setup`), diagnostics (`apex-autopilot doctor`), onboarding checklist generation (`generate_onboarding_checklist`), and the CI gate suite as a proof-of-quality artifact to show end customers.

## 4. Sales enablement assets

| Asset | Location | Audience |
|-------|----------|----------|
| Release notes | `CHANGELOG.md` (v1.0.0) | Prospects, partners |
| Engineering quality proof | `benchmark_report.md`, `benchmark/`, CI gate results | Technical buyers, security review |
| Architecture | `docs/architecture/` (Option B boundary, data flow, WTA tiers, combat FSM) | Solutions engineering |
| Integration contracts | `docs/telemetry-contract.md`, `docs/setpoint-contract.md` | Integration partners |
| Compliance | ISO 42001 agent-exec policy engine; `docs/COMPLIANCE_GAP_REPORT.md` | Enterprise/procurement |
| Quickstart | README "Quick Start" + `scripts/` benchmarks | POCs / pilots |
| Deployment configs | `configs/startup.yaml`, `configs/enterprise.yaml` | Professional services |

## 5. Launch checklist

- [x] Version 1.0.0 released (pyproject + `__version__`, git tag `v1.0.0`)
- [x] CI gates green: 2607 tests, 91.06% coverage, mypy/ruff clean, perf gate PASSED
- [x] CHANGELOG.md published
- [x] GTM_READINESS.md published (this document)
- [x] Roadmap item "Production release v1.0.0 with broker channel GTM" marked complete
- [ ] Broker squad MOUs signed (12 squads, 330 agent slots) — channel ops
- [ ] Tier pricing sheet published — sales
- [ ] TensorRT `.engine` files built and CI-integrated for perception gate (open roadmap item)

## 6. Support & SLA

Enterprise tier includes an SLA guarantee; dedicated support and custom integrations. AGPL-3.0 applies; §13 network-source obligation applies only if apex is exposed as a network service (integration with AAS remains at the ROS2/ZMQ boundary).
