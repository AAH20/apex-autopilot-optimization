# WTA Solver Upgrade Specification — `swarm/task_allocation.py`

**Repository:** apex-autopilot-optimization (AGPL-3.0) — `src/apex_autopilot_optimization/swarm/task_allocation.py`
**Sim/runtime surface:** Aerial Autonomy Stack (AAS, MIT) — integration via MAVLinkBridge + ROS2 topics
**Kanban card:** `t_277d9fac`
**Status:** proposed (spec only — no implementation yet)
**Parent goal:** vendor-agnostic swarm sim competitive with Shield AI Hivemind (<100 ms end-to-end allocation latency, no V-BAT lock-in)

---

## 1. Purpose and scope

Replace the pure greedy priority-first/nearest allocator in `swarm/task_allocation.py` with a **tiered Weapon-Target Assignment (WTA) solver**:

| Tier | Instance size | Algorithm | Role |
|------|---------------|-----------|------|
| T1 | weapons × targets < 20×20 (n·m < 400) | MILP, branch-and-bound exact | Optimal solution + certifiable lower bound |
| T2 | medium (≈20×20 up to ≈80×80) | Greedy construction heuristic (marginal expected damage) | Fast feasible allocation |
| T3 | large (80–200+ pairs) | VLSN (very large-scale neighborhood) local search | Near-optimal within latency budget |
| — | combat scenarios, any size | Dynamic reallocation (shoot-look-shoot / shoot-shoot-look) | Re-solve residual instance after battle damage assessment |

Out of scope for this spec: MILP solver integration code, VLSN implementation, AAS/MAVLink changes. Those follow in implementation tasks linked from `t_277d9fac`.

---

## 2. References and grounding

- [Ahuja2004] Ahuja, R., Kumar, A., Jha, K., Orlin, J. *Exact and Heuristic Methods for the Weapon Target Assignment Problem.* MIT Sloan School of Management Working Paper 4464-03, Dec 10, 2004. https://dspace.mit.edu/handle/1721.1/7388
  - WTA is a nonlinear integer program, **NP-complete**.
  - Branch-and-bound with LP / integer-programming / network-flow lower bounds solves instances **up to 80 weapons × 80 targets optimally**.
  - Network-flow construction heuristic + VLSN search obtains **almost-optimal solutions for up to 200×200 within a few seconds**.
  - Pre-2004: no quality estimates existed for WTA heuristics.
- [Ahuja2004OR] Same authors, *Operations Research* (published version), DOI 10.1287/opre.1070.0440 — same results.
- [NWF1978] Nemhauser, G.L., Wolsey, L.A., Fisher, M.L. *An analysis of approximations for maximizing submodular set functions.* Mathematical Programming 14, 265–294 (1978) — greedy gives 1/2-approximation for monotone submodular maximization under a matroid constraint.
- [Kline2019] Kline, A. *The Weapon-Target Assignment Problem.* Computers & Operations Research, 2019 — survey of static/dynamic WTA formulations and exact/heuristic methods.

Grounding claims used in this spec (ratios not from [Ahuja2004] are marked as standard/derived):

- WTA NP-complete: [Ahuja2004], [Kline2019]
- B&B optimal to 80×80: [Ahuja2004]
- VLSN near-optimal to 200×200: [Ahuja2004]
- Greedy 1/2 ratio: [NWF1978] (applied to equivalent expected-damage maximization — see §6.3)
- No constant worst-case ratio for VLSN: standard local-search property; empirical near-optimality per [Ahuja2004]

---

## 3. Problem formulation (static WTA)

### 3.1 Sets and parameters

| Symbol | Meaning |
|--------|---------|
| `W = {1..n}` | Weapons (shooters), e.g. UAVs with munitions |
| `T = {1..m}` | Targets |
| `v_j > 0` | Value of target `j` if it survives (expected survival value to minimize) |
| `p_ij ∈ [0,1]` | Kill probability: probability weapon `i` kills target `j` if engaged (§4) |
| `q_ij = 1 − p_ij` | Probability weapon `i` fails to kill target `j` |
| `x_ij ∈ {0,1}` | Decision: 1 iff weapon `i` is assigned to engage target `j` |

### 3.2 Objective

Minimize total expected survival value of all targets after engagements:

```
minimize   S(x) = Σ_{j∈T} v_j · Π_{i∈W} q_ij^{x_ij}
```

`Π_i q_ij^{x_ij}` is the probability target `j` survives all weapons assigned to it (independent kills assumed; see §4.3 for interference).

### 3.3 Constraints

1. **One target per weapon:** `Σ_{j∈T} x_ij ≤ 1`  ∀ i ∈ W  
   (a weapon engages at most one target per allocation cycle)
2. **Optional salvo cap:** `Σ_{i∈W} x_ij ≤ k_j`  ∀ j ∈ T  
   (max weapons engaging target `j`; `k_j = ∞` by default)
3. **Binary:** `x_ij ∈ {0,1}`

### 3.4 Complexity class

- Decision WTA ("is there an assignment with expected survival value ≤ B?"): **NP-complete** [Ahuja2004].
- Optimization WTA: **NP-hard**.
- Consequence: no polynomial-time exact algorithm unless P = NP; exact solvers (branch-and-bound) are exponential in the worst case — hence tiered solving by instance size.

---

## 4. Engagement model

### 4.1 Kill probability `p_ij`

Per weapon–target pair, not per weapon or per target alone. `p_ij` is a function of:

- engagement range and time-of-flight `τ_ij`
- relative aspect / angle-off
- target class (size, signature, maneuverability, armor)
- weapon lethality (CEP, warhead, seeker type)
- environmental state (weather, ECM, terrain masking)

Stored as an `n × m` engagement matrix refreshed from the engagement envelope service; values clamped to `[0, 1]`. A target's damage state after an engagement is sampled from `Bernoulli(p_ij)` in sim (kill / no-kill).

### 4.2 Time windows

Target `j` is only engageable during vulnerability window `[a_j, d_j]` (appearance → deadline). Weapon `i` becomes available at `t_i`; engagement `i→j` is **time-feasible** iff:

```
t_i + τ_ij ∈ [a_j, d_j]
```

Infeasible pairs get `x_ij = 0` (effectively `p_ij = 0` for the optimizer). Windows are recomputed each reallocation cycle from track state.

### 4.3 Interference constraints

- **Seeker/channel deconfliction:** at most one active seeker per frequency band per target at a given time (model as a conflict graph over pairs; clique constraints `Σ_{(i,j)∈C} x_ij ≤ 1` for each interference clique `C`).
- **Impact separation:** minimum time separation `Δt` between munitions impacting the same target (avoids fratricide / salvo interference); enforced pairwise: `x_ij = x_i'j = 1 ⇒ |impact_i − impact_i'| ≥ Δt`.
- **Footprint non-overlap:** optional — engagement footprints of simultaneous pairs must not overlap protected assets.

All interference constraints are linear in `x`, so they carry directly into the MILP (§7) and are checked as hard constraints in greedy/VLSN move evaluation (§8–§9).

---

## 5. Dynamic reallocation semantics (combat scenarios)

Static WTA assumes perfect pre-engagement knowledge. Combat needs **shoot–look–shoot / shoot–shoot–look** semantics: fire, observe battle damage assessment (BDA), then re-allocate surviving weapons against residual targets.

### 5.1 Modes

| Mode | Semantics | When to use |
|------|-----------|-------------|
| Shoot–look–shoot (SLS) | Engage **one** weapon → wait for BDA → decide next engagement | High-value targets, uncertain `p_ij`, scarce weapons |
| Shoot–shoot–look (SSL) | Fire a **salvo** → assess once → re-allocate survivors | Time-critical, salvo-friendly targets, latency-bound cycles |

### 5.2 Reallocation trigger (both modes)

On each BDA event (or salvo completion):

1. Remove killed targets from `T`; update residual values `v_j` for damaged (not killed) targets.
2. Return surviving/unspent weapons to the pool; mark engaged weapons unavailable for cooldown `c_i`.
3. Recompute `p_ij` conditioned on observed damage (e.g., damaged target easier/harder to kill).
4. Re-run the tiered solver (§6) on the **residual instance** (remaining weapons × remaining targets).
5. Issue new engagements; repeat until weapons exhausted or all targets neutralized.

### 5.3 State machine

```
                    +----------------+
                    |     IDLE       |
                    +----------------+
                           |
                  allocate_request
                           v
                    +----------------+
                    | ALLOCATING     |  (run tiered solver: T1/T2/T3)
                    +----------------+
                           |
                   solution_ready
                           v
                    +----------------+
                    |   ENGAGING     |  → issue fire commands (SLS: 1 wpn; SSL: salvo)
                    +----------------+
                           |
             bda_received / salvo_complete
                           v
                    +----------------+
                    |    LOOKING     |  → assess kills vs BDA model
                    +----------------+
                  /               \
      all_neutralized /             \ weapons_remaining ∧ targets_remaining
                    /               \
           +----------------+   +----------------+
           |    TERMINAL    |   |  RE-EVALUATING |
           +----------------+   +----------------+
                                        |
                                  residual_instance_ready
                                        |
                                        +-------> (back to ALLOCATING)
```

**Transitions:**

| From → To | Event | Action |
|-----------|-------|--------|
| IDLE → ALLOCATING | `allocate_request(weapons, targets)` | Build instance, pick tier by size (§6) |
| ALLOCATING → ENGAGING | `solution_ready` | Publish `(weapon, target)` engagements via ROS2 / MAVLinkBridge |
| ENGAGING → LOOKING | `bda_received` (SLS) or `salvo_complete` (SSL) | Record kill/damage per `p_ij` observation |
| LOOKING → TERMINAL | `all_neutralized` or `weapons_exhausted` | Publish final allocation, release weapons |
| LOOKING → RE-EVALUATING | surviving weapons ∧ surviving targets | Build residual instance (§5.2) |
| RE-EVALUATING → ALLOCATING | residual instance ready | Re-solve; delta-assign only changed pairs |
| any → IDLE | `reset` / `abort` | Clear partial state |

**Determinism rule:** given the same seeded random instance and same BDA sequence, the state machine must produce identical allocations (for regression testing).

---

## 6. Algorithm tiers

### 6.1 Tier selection

```
n, m = weapon count, target count
if n*m < 400:           Tier 1 — MILP exact
elif n*m < 6400:        Tier 2 — greedy construction   (approx. 20×20 … 80×80)
else:                   Tier 3 — VLSN                  (80×80 … 200×200+)
```

Boundaries are tunable via `TaskAllocationConfig` (see §12). The <100 ms end-to-end latency budget (Hivemind benchmark) applies to T2/T3 in the hot path; T1 is exact but not latency-guaranteed — use T1 offline or with a time limit and accept incumbent + bound.

### 6.2 Complexity per tier

| Tier | Worst-case complexity | Typical solve time | Guarantee |
|------|----------------------|--------------------|-----------|
| T1 MILP | exponential (NP-hard) | ms–s, instance-dependent | Optimal; LP lower bound |
| T2 Greedy | O(n·m) per construction pass (naive) | <1 ms | 1/2 of optimal expected **damage** (§6.3) |
| T3 VLSN | O(iterations · neighborhood_size) | capped iterations, <100 ms | No constant worst-case ratio; near-optimal empirically to 200×200 [Ahuja2004] |

### 6.3 Approximation ratios

**Maximize expected damage** rather than minimize survival:

```
maximize   D(x) = Σ_j v_j · (1 − Π_i q_ij^{x_ij})
```

`D` is monotone submodular in the assignment set; the constraint `Σ_j x_ij ≤ 1` is a partition matroid over weapons. By [NWF1978], the greedy construction that repeatedly adds the feasible pair with the largest marginal gain achieves **D_greedy ≥ (1/2) · D_opt**.

- Survival minimization does **not** inherit a constant ratio directly; report greedy quality empirically as gap vs MILP lower bound on ≤20×20 instances (test plan §13).
- T1: ratio 1 (exact). With a solver time limit, ratio = incumbent / LP lower bound (optimality gap).
- T3: no proven constant worst-case ratio (local search); [Ahuja2004] reports "almost optimal" solutions to 200×200 — spec targets empirical gap ≤ 5% vs MILP lower bound on 20×20–80×80 instances (test plan §13).

---

## 7. Tier 1 — MILP exact formulation (n·m < 400)

The objective `Π_i q_ij^{x_ij}` is nonlinear; linearize exactly with sequential survival variables.

### 7.1 Variables

- `x_ij ∈ {0,1}` — assignment (weapon i → target j)
- `z_ij ∈ [0,1]` — probability target `j` survives after considering weapons `1..i` assigned to it
- `y_ij ∈ [0,1]` — auxiliary linearization of `z_{i−1,j} · x_ij`

Weapons are ordered `1..n` per target (any fixed order).

### 7.2 Constraints

```
(1)  z_0j = 1                              ∀ j ∈ T
(2)  y_ij ≤ z_{i−1,j}                      ∀ i ∈ W, j ∈ T
(3)  y_ij ≤ x_ij                            ∀ i, j
(4)  y_ij ≥ z_{i−1,j} − (1 − x_ij)          ∀ i, j
(5)  y_ij ≥ 0                               ∀ i, j
(6)  z_ij = z_{i−1,j} − p_ij · y_ij         ∀ i, j
(7)  Σ_{j∈T} x_ij ≤ 1                       ∀ i ∈ W
(8)  Σ_{i∈W} x_ij ≤ k_j                     ∀ j ∈ T   (optional salvo cap)
(9)  interference clique constraints        (linear, §4.3)
(10) time-feasibility: x_ij = 0 if t_i + τ_ij ∉ [a_j, d_j]
```

### 7.3 Objective

```
minimize   Σ_{j∈T} v_j · z_nj
```

`z_nj` is exactly `Π_i q_ij^{x_ij}` (survival probability of target `j`), so the MILP is **exact**: solving it yields the WTA optimum. With a time limit it returns an incumbent plus an LP-relaxation lower bound; optimality gap = `(incumbent − bound) / incumbent`.

Size: O(n·m) binary variables, O(n·m) continuous variables, O(n·m) constraints. Solvable by branch-and-bound; [Ahuja2004] solves 80×80 optimally — spec default time limit 50 ms for ≤20×20 in the hot path (else asynchronous/re-planning).

---

## 8. Tier 2 — Greedy construction heuristic (medium)

### 8.1 Selection rule

Repeatedly assign the feasible `(weapon, target)` pair with the largest **marginal expected damage per unit cost**:

```
Δ(i→j | current assignment) = D(S ∪ {(i,j)}) − D(S)
```

where `D(S) = Σ_j v_j · (1 − Π_{i:(i,j)∈S} q_ij)`. Incremental delta for adding weapon `i` to target `j`:

```
Δ = v_j · (1 − q_ij) · Π_{i': (i',j)∈S} q_i'j   = v_j · p_ij · (current survival of j)
```

i.e., marginal damage = target value × kill prob × target's current survival probability. Tie-break by priority, then nearest (existing behavior), then lowest weapon id.

### 8.2 Pseudocode

```
GREEDY-WTA(W, T, p, v, k, interference, time-feasible)
  S ← ∅                                 # assignment set
  surv[j] ← 1.0   for j ∈ T             # current survival probability of each target
  load[i] ← 0     for i ∈ W             # weapons used (≤ 1)
  salvo[j] ← 0    for j ∈ T             # weapons engaged on target j (≤ k_j)

  repeat
    best ← None; bestDelta ← 0
    for each (i, j) with load[i] = 0 and salvo[j] < k_j and time-feasible(i,j):
        if (i,j) violates interference with S: continue
        delta ← v[j] * p_ij * surv[j]          # marginal expected damage
        if delta > bestDelta:
            best ← (i,j); bestDelta ← delta
    if best = None: break
    (i*, j*) ← best
    S ← S ∪ {(i*, j*)}
    load[i*] ← 1
    salvo[j*] ← salvo[j*] + 1
    surv[j*] ← surv[j*] * (1 − p_i*j*)        # target survives new shot with prob (1−p)
  until false

  return S
```

**Properties:**
- Each weapon assigned at most once (`load[i] ≤ 1`).
- Monotone: `D(S)` never decreases.
- Ratio: `D(S_greedy) ≥ (1/2) · D(S_opt)` [NWF1978], since marginal-damage greedy over a monotone submodular function under a partition matroid.
- Complexity: O(n·m) per added weapon, O(n²·m) worst case (each of ≤ n assignments scans all pairs); in practice bounded by a max-iteration cap for the <100 ms budget.

---

## 9. Tier 3 — VLSN local search (80–200+ pairs)

### 9.1 Incumbent

Seed from Tier 2 greedy solution (or random multi-start for offline mode).

### 9.2 Neighborhood structure

A **move** changes the assignment of up to `k` weapon–target pairs simultaneously (a `k`-exchange neighborhood `N_k`):

- **1-swap:** reassign one weapon to a different target, or unassign one weapon.
- **2-swap:** reassign two weapons (e.g., swap their targets, or one target swap + one unassign).
- **k-exchange (k ≤ K_max, default 3):** reassign up to K_max weapons in one move; the residual sub-problem over the freed weapons/targets is solved exactly by a tiny MILP or enumeratively (network-flow based per [Ahuja2004]).

Neighborhood size for `k`-exchange: O((n·m)^k) moves — evaluated incrementally using survival deltas (§8.1), so move evaluation is O(k) instead of re-scoring the full objective.

### 9.3 Search

```
VLSN-WTA(S0, p, v, ...)
  S ← S0
  repeat
    improved ← false
    for k = 1 .. K_max:                          # variable-depth: small neighborhoods first
        for each move N in N_k(S) (best-improvement or first-improvement):
            if move feasible (capacity, interference, time windows):
                ΔD ← incremental damage change of move
                if ΔD > tolerance:
                    apply move to S
                    improved ← true
                    break to outer repeat        # first-improvement restart at k=1
    until not improved
  return S
```

- **Variable neighborhood descent:** start k=1; only grow k when no improving move at smaller k (keeps large instances fast).
- **Iteration cap + time cap** (default 80 ms) to honor the <100 ms end-to-end budget; return best incumbent found.
- **Multi-start (offline mode):** different greedy seeds, keep best.

### 9.4 Guarantee

- Terminates at a local optimum w.r.t. `N_{K_max}` (no improving k-exchange for k ≤ K_max).
- No constant worst-case approximation ratio (standard for local search); empirical near-optimality to 200×200 per [Ahuja2004]. Test target: gap ≤ 5% vs MILP lower bound on 20×20–80×80 instances (§13).

---

## 10. Complexity classes and approximation ratios — summary

| Tier | Problem class | Algorithm class | Worst-case complexity | Approximation ratio | Source/basis |
|------|---------------|-----------------|----------------------|---------------------|--------------|
| T1 | WTA optimization | Exact MILP + branch-and-bound | exponential (NP-hard) | 1 (optimal); gap reported with time limit | [Ahuja2004] |
| T2 | WTA optimization | Greedy construction | O(n²·m) naive | ≥ 1/2 of optimal expected **damage** | [NWF1978] + submodularity |
| T3 | WTA optimization | VLSN local search | O(iters · neighborhood) | none proven; near-optimal empirically | [Ahuja2004] |
| Dynamic | residual WTA per BDA event | Re-solve T1/T2/T3 on residual instance | per tier per event | per tier | — |

Decision version of WTA: **NP-complete** [Ahuja2004, Kline2019].

---

## 11. Constraints and integration context

- **Latency budget:** <100 ms end-to-end allocation (Hivemind benchmark). T2/T3 must meet it in the hot path via iteration/time caps; T1 is not latency-guaranteed and is used offline or asynchronously.
- **Vendor-agnostic:** no V-BAT lock-in; solver depends only on `(weapons, targets, p_ij, v_j)` — platform-agnostic.
- **Licensing:** apex-autopilot-optimization is AGPL-3.0; this tiered solver (derivative work) inherits AGPL-3.0. AAS (MIT, sim/runtime surface) remains separate; integration via MAVLinkBridge + ROS2 topics is an arm's-length boundary — confirm with counsel before shipping combined binaries.
- **Scale limits from context:** PX4 Gazebo SITL practical under 10 vehicles; 4 GB RAM per Gazebo instance — solver tiers sized for ≤200×200 WTA pairs but SITL validation at smaller scale.
- **Port/topic naming:** preserve existing conventions — port namespacing `5760 + i·10` master, `5501 + i·10` SITL, `DRONE_ID = ROS_DOMAIN_ID = MAV_SYS_ID`; allocations published as ROS2 topics consumed by `integration/mavlink.py` (`MAVLinkBridge`) and `offboard/guided` actions.

---

## 12. Configuration (`TaskAllocationConfig` additions)

Additive, backward-compatible fields (existing `algorithm="greedy"`, `max_tasks_per_agent`, `communication_range` unchanged):

```
wta_mode: str = "tiered"          # "tiered" | "milp" | "greedy" | "vlsn" (override)
milp_time_limit_ms: float = 50.0  # T1 time limit (0 = solve to optimality)
vlsn_iteration_cap: int = 500     # T3 iteration cap
vlsn_time_budget_ms: float = 80.0 # T3 time cap (< 100 ms end-to-end)
vlsn_k_max: int = 3               # max k-exchange neighborhood size
dynamic_mode: str = "sls"         # "sls" | "ssl" | "none"
bda_confidence_threshold: float = 0.5
random_seed: int | None = None    # determinism
```

Tier-selection thresholds (`n·m < 400`, `< 6400`) exposed as `milp_max_pairs`, `greedy_max_pairs`.

---

## 13. TDD test plan

Follow RED–GREEN–REFACTOR; new tests in `tests/unit/test_wta_solver.py` (extend `tests/unit/test_swarm_task_allocation.py`). Every test names the tier and scenario it covers.

### 13.1 Unit — engagement model
- `test_kill_probability_clamped` — `p_ij` outside [0,1] rejected/clamped.
- `test_survival_probability_independent_kills` — `Π q_ij` matches brute force for small assignments.
- `test_time_window_feasibility` — pair with `t_i + τ_ij ∉ [a_j, d_j]` is never assigned.
- `test_interference_clique` — conflicting pairs (same seeker band, same target) never co-assigned.
- `test_impact_separation` — two munitions on same target respect `Δt`.

### 13.2 Unit — tier selection & config
- `test_tier_selection_by_size` — 19×19 → MILP, 20×20 → greedy, 80×80+ → VLSN (per thresholds).
- `test_config_override_respected` — forcing `algorithm="milp"` on large instance uses T1 (or raises/limits).
- `test_deterministic_with_seed` — same seed → identical allocations across runs.

### 13.3 T1 MILP
- `test_milp_optimal_small_brute_force` — for n·m ≤ 25 (e.g., 5×5), MILP result equals brute-force enumeration of all valid assignments.
- `test_milp_respects_all_constraints` — each weapon ≤ 1 target; salvo caps; interference; time windows.
- `test_milp_lower_bound_property` — LP relaxation lower bound ≤ optimal (report gap).
- `test_milp_time_limit_returns_incumbent` — with short time limit, returns feasible assignment + gap, never crashes.

### 13.4 T2 Greedy
- `test_greedy_half_ratio_empirical` — on 50 random ≤20×20 instances, `D_greedy / D_milp_optimal ≥ 0.5` (expected-damage form).
- `test_greedy_priority_ordering` — higher-priority target assigned first when deltas tie.
- `test_greedy_capacity_respected` — `max_tasks_per_agent` / one-target-per-weapon never violated.
- `test_greedy_monotone_damage` — `D(S)` never decreases as pairs are added.

### 13.5 T3 VLSN
- `test_vlsn_near_optimal_gap` — on 20×20–80×80 instances, `1 − D_vlsn/D_milp_lower_bound ≤ 5%` (damage form; survival-value gap reported alongside).
- `test_vlsn_converges_to_local_optimum` — no improving k-exchange move remains (k ≤ k_max).
- `test_vlsn_respects_hard_constraints` — all final assignments feasible.
- `test_vlsn_time_budget` — 200×200 instance completes within `vlsn_time_budget_ms`.
- `test_vlsn_variable_neighborhood` — k=1 exhausts before k=2 is attempted (instrumented via move counter).

### 13.6 Dynamic reallocation (SLS / SSL)
- `test_sls_single_weapon_per_cycle` — exactly one engagement issued before BDA.
- `test_ssl_salvo_then_assess` — salvo of ≤ k_j weapons engaged before BDA.
- `test_bda_removes_killed_targets` — killed target excluded from residual instance.
- `test_bda_updates_residual_p` — damaged target's `p_ij` conditioned on observation.
- `test_state_machine_transitions` — IDLE→ALLOCATING→ENGAGING→LOOKING→{TERMINAL,RE-EVALUATING→ALLOCATING}; invalid transitions rejected.
- `test_reallocation_converges` — sequence of BDA events terminates (weapons exhausted or all neutralized).
- `test_deterministic_bda_sequence` — identical BDA trace → identical final allocation.

### 13.7 Property-based (Hypothesis)
- `test_assignment_validity_invariant` — every emitted allocation satisfies one-target-per-weapon, salvo caps, interference.
- `test_monotonicity_adding_weapons` — adding a weapon never increases optimal expected survival value (MILP, small instances).
- `test_permutation_invariance` — permuting weapon/target IDs yields same objective value.

### 13.8 Performance / regression
- `test_milp_20x20_solves` — 20×20 solved to optimality (or incumbent+bound within time limit).
- `test_vlsn_200x200_seconds` — 200×200 completes in seconds ([Ahuja2004] benchmark).
- `test_end_to_end_latency_budget` — T2/T3 allocation call < 100 ms on representative 80×80 sim instance.
- `test_no_regression_existing_greedy_tests` — all existing `tests/unit/test_swarm_task_allocation.py` tests still pass with tiered solver as default.

### 13.9 Contract
- `test_allocation_result_schema` — output is `list[(weapon_id, target_id)]` plus optional metadata (tier used, gap, solve time).
- `test_empty_inputs` — no weapons or no targets → empty allocation.

---

## 14. Acceptance criteria (Definition of Done)

1. `swarm/task_allocation.py` exposes `allocate(weapons, targets)` returning tiered allocation with tier metadata; existing public API (`Agent`, `Task`, `TaskAllocationConfig`, `TaskAllocator`) remains import-compatible.
2. All §13 tests pass (RED→GREEN→REFACTOR complete; mutation/property-based suites included).
3. MILP tier optimal on ≤20×20 vs brute force; greedy ≥ 1/2 damage ratio empirically; VLSN gap ≤ 5% vs MILP bound on 20×20–80×80.
4. T2/T3 hot-path allocations < 100 ms on 80×80 representative instance; VLSN 200×200 in seconds.
5. SLS and SSL state machines implemented per §5.3 with BDA-driven reallocation.
6. Determinism with `random_seed`; documented in module docstring.
7. Spec reviewed against kanban card `t_277d9fac`; implementation tasks linked from it.

---

## 15. Open questions

- MILP solver choice (PuLP/CBC vs scipy.optimize.milp vs commercial) — must be AGPL-3.0-compatible or isolated behind an interface so the AGPL solver dependency does not infect the MIT AAS boundary.
- Exact `p_ij` source: engagement envelope service vs static lookup table; time-varying `p_ij` refresh rate.
- Whether salvo cap `k_j` defaults to ∞ or 1 for the first implementation iteration.
- Latency budget enforcement: hard exception vs best-effort when T1/T3 caps exceeded.
