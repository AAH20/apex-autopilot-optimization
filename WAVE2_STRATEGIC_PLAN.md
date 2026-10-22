# Wave 2 Strategic Plan — apex-autopilot-optimization

**Time-to-cash prioritization** | Status: Draft for review | Repo: `/home/aah/Downloads/2000 workflows/projects/apex-autopilot-optimization/`

---

## 1. Executive summary

Wave 1 is complete: the full Option B stack (AAS sim/runtime + apex optimization/governance) is built, tested (2607 green), and benchmarked against Shield AI Hivemind with every latency check passing (swarm cycle p95 26.6 ms vs <100 ms ceiling). All Wave-2 technical modules (swarm_runner, perception, messaging, WTA solver, governance, benchmark) are implemented and CI-gated.

Three roadmap items remain unchecked:

| # | Wave 2 item | State |
|---|-------------|-------|
| A | TensorRT `.engine` files built and CI-integrated for perception gate | Bench script exists (`bench_perception_trt.py`, 43.1 fps @ 720p PyTorch FP16); `.engine` files not built, not in CI |
| B | Multi-cloud deployment (AWS/Azure/GCP) with FinOps cost tracking | Designed (`deployment/DESIGN.md`, `COST_MODEL.md`, terraform/finops/monitoring scaffolding); not deployed |
| C | Production release v1.0.0 with broker channel GTM (12 squads, 330 agent slots) | Not started; version is 0.1.0 (Alpha) |

**Cash thesis:** This is an AGPL-3.0 dual-licensable swarm optimization stack with a proven sub-100 ms story. Cash comes from (i) commercial licenses / enterprise support for organizations that cannot or will not open-source derivative works, and (ii) broker-channel seat sales (330 agent slots across 12 squads). Neither is possible without a production release (v1.0.0). TensorRT engine integration de-risks the sale quickly (reproducible, CI-gated performance evidence brokers can pitch). Multi-cloud + FinOps enables recurring cloud/SaaS revenue but is the heaviest build.

**Time-to-cash ordering (P0 → P2):** get the product release-ready and performance-proven first, then sell through the broker channel, then layer on recurring cloud revenue.

---

## 2. Time-to-cash prioritization framework

Every initiative is scored on four dimensions, then ranked by **expected weeks to first dollar** (time-to-cash):

| Dimension | Meaning | Weight |
|-----------|---------|--------|
| **Cash dependency** | Is this a prerequisite for any revenue? (v1.0.0 = yes; broker GTM = the sale itself) | 35% |
| **Build time** | Weeks to done (shorter = faster cash) | 25% |
| **Revenue potential** | Addressable cash once live (330 slots × seat price; cloud recurring) | 25% |
| **Risk / certainty** | Likelihood the initiative actually converts to cash (proven tech > new market) | 15% |

**Priority rule:** The initiative with the shortest *dependency-adjusted* time-to-cash goes first. If initiative X blocks cash and takes 6 weeks, it precedes initiative Y that brings cash directly but takes 16 weeks and depends on X.

---

## 3. Prioritized initiative stack

### P0 — Foundation for cash (Weeks 0–6) — "Release-ready & performance-proven"

**P0-1. TensorRT `.engine` build + CI integration** (perception gate)
- **Time-to-cash role:** Enabler, not direct cash. Cuts sales friction: a CI-gated, reproducible TensorRT performance number is the evidence brokers use to displace Hivemind. Fast to complete.
- **Scope:** Build FP16 TensorRT `.engine` files for YOLO26n detect + pose + ByteTrack + r3d-18 action; add `--build-engines` to CI so `.engine` artifacts are produced and the perception gate runs the engine path (not PyTorch fallback); gate p95 latency on engine path.
- **Investment:** ~2–3 weeks, 1 engineer (GPU host available: RTX 2070 Max-Q, 8 GiB).
- **DoD:** `scripts/bench_perception_trt.py --build-engines` produces `.engine` files; CI `benchmarks` job asserts engine-path p95 < 100 ms; artifacts versioned and archived.

**P0-2. Production release v1.0.0** (release engineering + commercial terms)
- **Time-to-cash role:** **Critical path to all cash.** Nothing can be sold, licensed, or brokered without a stable, versioned release. AGPL-3.0 with commercial dual-licensing terms defined.
- **Scope:** Bump `pyproject.toml` to 1.0.0, change classifier to `Production/Stable`, cut `v1.0.0` tag + GitHub release, add `LICENSE-COMMERCIAL.md` + `PRICING.md` (per-agent-slot seat pricing + enterprise support), document AGPL §13 network-source obligation and commercial escape hatch, add CLA/contribution guidance for broker partners.
- **Investment:** ~3–4 weeks, 1 engineer + founder sign-off.
- **DoD:** `v1.0.0` tag exists; GitHub release with changelog; `PRICING.md` and `LICENSE-COMMERCIAL.md` committed; install via `pip install apex-autopilot-optimization==1.0.0` works from PyPI/testpypi.

### P1 — First cash (Weeks 6–14) — "Broker channel goes live"

**P1-1. Broker channel GTM launch** (12 squads, 330 agent slots)
- **Time-to-cash role:** **First actual cash.** Brokers/resellers sell agent slots into their customer bases; 12 squads × 330 slots = the initial book of business.
- **Scope:** Broker partner agreement template, partner enablement kit (deck, benchmark report, integration quick-start), slot-allocation API / license-key issuance for 330 agent slots, onboarding runbook for the 12 squads, revenue tracking (slots sold vs. 330 cap), first invoice/PO collected.
- **Depends on:** P0-2 (v1.0.0 must exist before any partner can sell a versioned product).
- **Investment:** ~6–8 weeks (mostly founder/business development, light eng for license-key issuance).
- **DoD:** ≥2 broker partners signed; ≥1 squad onboarded and invoiced; 330-slot capacity model live; first cash received.

### P2 — Recurring / scale cash (Weeks 14–24) — "Cloud revenue layer"

**P2-1. Multi-cloud deployment (AWS/Azure/GCP) with FinOps cost tracking**
- **Time-to-cash role:** Enables recurring cloud/SaaS revenue (hosted perception + WTA API, per-slot monthly fees) and protects margin via $0 committed spend. Heaviest build; starts after first cash is proven.
- **Scope:** Deploy the `deployment/DESIGN.md` multi-cloud free-tier architecture (CloudFront → API Gateway/Lambda → DynamoDB/S3 primary; Azure Functions failover; GCP Cloud Run burst); OpenCost + Grafana dashboards; Cloud Custodian policies; Infracost CI gate ($0 delta); budgets at $0 with 50/80/100% alerts; `runbooks/budget-breach.md`.
- **Depends on:** P1 (cash validates the product before investing in cloud ops).
- **Investment:** ~8–10 weeks, 1–2 engineers (DevOps/FinOps).
- **DoD:** Multi-cloud stack deployed across AWS/GCP/Azure within always-free allowances; OpenCost dashboard shows per-provider spend; Infracost fails CI on any $0-budget breach; budget-breach runbook tested.

---

### Priority ranking by time-to-cash

| Rank | Initiative | Est. weeks to done | Cash role | Blocks other cash? | Cumulative weeks to first cash |
|------|-----------|-------------------|-----------|-------------------|-------------------------------|
| 1 | P0-1 TensorRT engines + CI | 2–3 | Enabler (de-risks sale) | No | — |
| 2 | P0-2 v1.0.0 release | 3–4 | **Prerequisite for all cash** | Yes (blocks P1, P2) | ~6 |
| 3 | P1-1 Broker channel GTM | 6–8 | **First cash** | No | ~12–14 |
| 4 | P2-1 Multi-cloud + FinOps | 8–10 | Recurring revenue | No | ~20–24 (parallel after P1) |

**Critical path to first dollar:** P0-1 → P0-2 → P1-1 → cash (~12–14 weeks from start). P2-1 runs in parallel with P1 once P0-2 is done, targeting recurring revenue by week ~20–24.

---

## 4. Detailed initiative specs

### 4.1 P0-1 — TensorRT `.engine` build & CI integration

**Why now (time-to-cash):** The perception benchmark already shows 43.1 fps @ 720p on PyTorch FP16, but CI runs the PyTorch path. Brokers pitching against Hivemind need a CI-gated TensorRT number, not a local script. This is a 2–3 week task that materially strengthens every sales conversation.

**Work breakdown:**
1. Add TensorRT build step to `scripts/bench_perception_trt.py` (already supports `--build-engines`); export YOLO26n detect + pose + r3d-18 to FP16 `.engine`.
2. Add CI job `tensorrt-engines` (runs on GPU runner if available, else documents engine build locally and archives artifacts).
3. Update `ci_performance_gate.py` to run perception gate on the engine path when `.engine` files are present; keep PyTorch/CPU fallback with a clear warning (never silent slowness).
4. Archive `.engine` artifacts per release; pin engine version in `benchmark_report.md`.

**Acceptance:** `--build-engines` succeeds on the GPU host; CI gate passes on engine path; p95 perception latency < 100 ms documented in `benchmark_report.md`.

### 4.2 P0-2 — Production release v1.0.0

**Why now (time-to-cash):** All cash is downstream of a versioned release. AGPL-3.0 means commercial adopters who can't open-source derivatives need a commercial license path — that must be defined and priced before the first broker conversation.

**Work breakdown:**
1. `pyproject.toml`: version `1.0.0`, classifier `Development Status :: 5 - Production/Stable`.
2. Add `PRICING.md`: per-agent-slot annual seat fee (basis for the 330-slot broker book), enterprise support tier, commercial license fee for closed-source derivatives.
3. Add `LICENSE-COMMERCIAL.md`: plain-language commercial terms + AGPL §13 network-source disclosure.
4. Cut `v1.0.0` tag + GitHub release with changelog drawn from Wave 1 (benchmark report, formal verification, Hivemind comparison).
5. Publish to TestPyPI/PyPI; verify `pip install apex-autopilot-optimization==1.0.0`.
6. Founder sign-off on release readiness.

**Acceptance:** `v1.0.0` installable from PyPI; `PRICING.md` + `LICENSE-COMMERCIAL.md` committed; release notes cite Hivemind-beating benchmarks.

### 4.3 P1-1 — Broker channel GTM (12 squads, 330 agent slots)

**Why now (time-to-cash):** This is the revenue event. Brokers bring existing customer relationships; apex supplies the swarm optimization stack + per-slot licensing. 330 slots is the initial capacity cap to manage delivery risk.

**Work breakdown:**
1. Broker partner agreement (rev-share or wholesale slot pricing), template contract.
2. Partner enablement kit: sales deck, `benchmark_report.md`, integration quick-start (MAVLink/ROS2 boundary), pricing card from `PRICING.md`.
3. License-key / slot-issuance mechanism (lightweight: CLI or API that allocates N agent slots per broker, enforces the 330 cap).
4. Onboard 12 brokers → assign squad slot allocations summing ≤330.
5. Onboard first squad; deliver + invoice; collect first PO/payment.
6. Revenue tracker: slots sold / 330, cash collected, pipeline by broker.

**Acceptance:** ≥2 brokers contracted; ≥1 squad live and invoiced; slot tracker shows allocations ≤330; first cash in bank.

### 4.4 P2-1 — Multi-cloud deployment + FinOps

**Why now (time-to-cash):** Converts the product into a recurring cloud service (hosted WTA/perception API, per-slot/month). Runs on always-free tiers ($0 committed spend) so margin is protected while revenue scales. Starts after first cash validates demand.

**Work breakdown (from `deployment/DESIGN.md`):**
1. Terraform: AWS (CloudFront, API Gateway, Lambda, DynamoDB, S3), Azure (Functions, Cosmos DB, Static Web Apps), GCP (Cloud Run, Firestore, Cloud Storage) — always-free only.
2. Traffic manager: priority routing AWS → Azure → GCP.
3. FinOps: OpenCost + Prometheus + Grafana (single pane of glass), Cloud Custodian policies (tag enforcement, orphan cleanup, idle shutdown), Infracost CI gate ($0 delta fails PR).
4. Budgets: $0/provider, alerts at 50/80/100%; 100% → auto-suspend non-essential resources (`runbooks/budget-breach.md`).
5. Deploy hosted perception + WTA API behind the edge; meter per-agent-slot usage for recurring billing.

**Acceptance:** Stack live on 3 providers within always-free allowances; OpenCost dashboard shows $0 projected spend; Infracost blocks cost-increasing PRs; budget-breach runbook executed in a fire-drill.

---

## 5. Resource requirements

| Role | P0 (wks 0–6) | P1 (wks 6–14) | P2 (wks 14–24) |
|------|-------------|---------------|----------------|
| Engineer (ML/perf) | 1.0 (TensorRT) | 0.5 (slot issuance) | — |
| Engineer (release/DevOps) | 1.0 (v1.0.0) | 0.2 | 1.0–2.0 (multi-cloud/FinOps) |
| Founder / BD | 0.5 (commercial terms) | 1.0 (broker GTM) | 0.5 (pricing/cloud GTM) |

**Non-personnel:** GPU host already available (RTX 2070 Max-Q). Cloud accounts: Azure free-tier (anchor), AWS + GCP always-free (no committed spend). Domain + SSL for hosted API (minimal cost).

---

## 6. Risks & mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| TensorRT build fails on host / no GPU runner in CI | Medium | Medium | Keep PyTorch FP16 path as documented fallback; gate on engine path only when `.engine` present; never silent slowness (existing script behavior). |
| v1.0.0 slip delays broker GTM (cash blocked) | Medium | High | Time-box release to 4 weeks; ship v1.0.0 even if minor polish is deferred to v1.0.1. |
| Broker sign-up slower than expected | Medium | High | Start partner outreach in parallel with P0-2 (week 4); have a direct-sales fallback for the first 10–20 slots. |
| Multi-cloud always-free allowances shrink (AWS new-account free plan changes) | Medium | Medium | Design already avoids 12-month trial services on the hot path; monitor account status; auto-suspend at 100% budget. |
| AGPL §13 network-source obligation deters commercial adopters | Low | Medium | Commercial dual-license escape hatch in `LICENSE-COMMERCIAL.md`; keep AAS integration at network boundary (already architected). |

---

## 7. Definition of done & success metrics

**Wave 2 complete when:**
- [ ] TensorRT `.engine` files built; CI gate runs engine path; p95 < 100 ms documented.
- [ ] `v1.0.0` tagged, released, installable; `PRICING.md` + `LICENSE-COMMERCIAL.md` committed.
- [ ] ≥2 broker partners contracted; ≥1 squad onboarded and invoiced; slot allocations tracked ≤330.
- [ ] First cash collected.
- [ ] Multi-cloud stack deployed (AWS/GCP/Azure) within always-free allowances; OpenCost + Cloud Custodian + Infracost CI gate live; $0 projected spend.
- [ ] Recurring cloud revenue path priced (per-slot/month) in `PRICING.md`.

**Time-to-cash milestones:**
- Week 6: v1.0.0 released (product sellable).
- Week 12–14: first broker cash (P1-1).
- Week 20–24: recurring cloud revenue live (P2-1).

---

## 8. Recommended execution order

1. **Start P0-1 and P0-2 in parallel** (weeks 0–4): TensorRT engines + v1.0.0 release engineering.
2. **Launch broker outreach at week 4** (commercial terms ready from P0-2); sign brokers while P0-1 finishes.
3. **P1-1 goes live at week 6–8** once v1.0.0 is out; first cash target week 12–14.
4. **Kick off P2-1 at week 14** (after first cash validates demand); recurring revenue target week 20–24.

This order minimizes the dependency-adjusted time to first dollar while keeping the recurring-revenue build (P2) from delaying the initial cash event (P1).
