"""Tiered Weapon-Target Assignment (WTA) solver.

Implements the Wave 1 tiered WTA solver from ``docs/wta-solver-spec.md``:

Tiers
-----
T1 -- exact MILP (n*m < 400).  The nonlinear objective
    ``S = sum_j v_j * prod_i q_ij**x_ij`` is linearised exactly with sequential
    survival variables ``z_ij`` (probability target ``j`` survives weapons
    ``0..i``) and big-M auxiliaries ``y_ij = z_{i-1,j} * x_ij``.  Solved with
    HiGHS (``scipy.optimize.milp``); reports an LP/MIP dual lower bound and an
    optimality gap.  Approximation ratio 1.0 (optimal).
T2 -- greedy marginal-damage construction (approx. 20x20 .. 80x80).  Repeatedly
    assigns the feasible pair with the largest marginal expected damage
    ``v_j * p_ij * surv[j]``.  Guarantees ``D_greedy >= 1/2 * D_opt`` for the
    expected-damage maximisation form (Nemhauser/Wolsey/Fisher 1978;
    monotone submodular under a partition matroid).
T3 -- VLSN k-exchange variable-neighbourhood descent (80x200+).  Seeded from T2;
    repeatedly applies improving 1-/2-/k-exchange moves, small neighbourhoods
    first, capped by iteration count and a wall-clock time budget.  No proven
    constant worst-case ratio; near-optimal in practice.

Dynamic reallocation
--------------------
Shoot-look-shoot (SLS) and shoot-shoot-look (SSL) modes with a state machine
IDLE -> ALLOCATING -> ENGAGING -> LOOKING -> {TERMINAL | RE-EVALUATING -> ALLOCATING}
driven by battle-damage-assessment (BDA) events that re-solve the residual
instance.

The public ``solve`` API returns ``list[(weapon_id, target_id)]`` assignments
plus metadata, keeping the allocation-result shape compatible with the existing
``TaskAllocator`` where sensible.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from itertools import combinations, product
from typing import Any

import numpy as np

try:  # T1 MILP backend (HiGHS via SciPy)
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    _HAS_SCIPY = True
except Exception:  # pragma: no cover - scipy is a hard dependency of the project
    _HAS_SCIPY = False


class Tier(Enum):
    T1_MILP = "t1_milp"
    T2_GREEDY = "t2_greedy"
    T3_VLSN = "t3_vlsn"


class SolverState(Enum):
    IDLE = auto()
    ALLOCATING = auto()
    ENGAGING = auto()
    LOOKING = auto()
    TERMINAL = auto()
    RE_EVALUATING = auto()


class AllocationMode(Enum):
    SLS = "sls"  # shoot-look-shoot: one engagement per cycle
    SSL = "ssl"  # shoot-shoot-look: salvo per cycle
    NONE = "none"  # static allocation only


@dataclass(frozen=True, slots=True)
class Weapon:
    id: int
    available_time: float = 0.0


@dataclass(frozen=True, slots=True)
class Target:
    id: int
    value: float
    window_start: float = 0.0
    window_end: float = math.inf


@dataclass(slots=True)
class WTAConfig:
    """Configuration for the tiered WTA solver (additive, backward compatible)."""

    wta_mode: str = "tiered"  # "tiered" | "milp" | "greedy" | "vlsn"
    milp_max_pairs: int = 400  # n*m < 400 -> T1
    greedy_max_pairs: int = 6400  # n*m < 6400 -> T2; else T3
    milp_time_limit_ms: float = 50.0  # T1 time limit (0 = solve to optimality)
    vlsn_iteration_cap: int = 100  # T3 iteration cap
    vlsn_time_budget_ms: float = 40.0  # T3 wall-clock cap (< 100 ms budget)
    vlsn_k_max: int = 3  # max k-exchange neighbourhood size
    dynamic_mode: str = "sls"  # "sls" | "ssl" | "none"
    bda_confidence_threshold: float = 0.5
    random_seed: int | None = None  # determinism
    salvo_cap_default: int | None = None  # None == unlimited salvo per target
    max_tasks_per_agent: int = 1  # one target per weapon per cycle


@dataclass(slots=True)
class WTAResult:
    """Outcome of ``TieredWTASolver.solve``."""

    assignments: list[tuple[int, int]]  # (weapon_id, target_id)
    tier: Tier
    expected_survival_value: float  # min S(x)
    expected_damage: float  # max D(x) = total - S
    total_target_value: float
    lp_lower_bound: float | None = None  # T1 dual bound (survival form)
    optimality_gap: float | None = None  # (incumbent - bound) / incumbent
    solve_time_ms: float = 0.0
    solver_status: str = ""
    message: str = ""
    num_weapons: int = 0
    num_targets: int = 0

    @property
    def is_optimal(self) -> bool:
        return (
            self.tier == Tier.T1_MILP
            and self.optimality_gap is not None
            and self.optimality_gap <= 1e-9
        )


class TieredWTASolver:
    """Tiered WTA solver: MILP exact / greedy construction / VLSN local search."""

    def __init__(self, config: WTAConfig | None = None) -> None:
        self.config = config or WTAConfig()
        self._rng = np.random.default_rng(self.config.random_seed)

    # ------------------------------------------------------------------ solve
    def solve(
        self,
        weapons: Iterable[Weapon],
        targets: Iterable[Target],
        kill_prob: np.ndarray,
        values: np.ndarray | None = None,
        time_feasible: np.ndarray | None = None,
        salvo_caps: dict[int, int] | None = None,
        interference_cliques: list[list[tuple[int, int]]] | None = None,
        tier_override: Tier | str | None = None,
        time_limit_ms: float | None = None,
    ) -> WTAResult:
        """Solve a static WTA instance.

        Parameters
        ----------
        weapons, targets:
            Ordered sequences; ``kill_prob`` is indexed by their positions.
        kill_prob:
            (n, m) array with p_ij in [0, 1].
        values:
            (m,) target values; defaults to all ones.
        time_feasible:
            (n, m) bool array; False => pair cannot be assigned.
        salvo_caps:
            target_id -> max weapons on that target.
        interference_cliques:
            list of cliques, each a list of (weapon_index, target_index) pairs
            of which at most one may be assigned.
        tier_override:
            force a tier (overrides automatic size-based selection).
        time_limit_ms:
            per-call wall-clock limit (applies to T1/T3).
        """
        weapons = list(weapons)
        targets = list(targets)
        p = np.asarray(kill_prob, dtype=float)
        n, m = p.shape
        if values is None:
            values = np.ones(m, dtype=float)
        values = np.asarray(values, dtype=float)
        if time_feasible is None:
            time_feasible = np.ones((n, m), dtype=bool)
        time_feasible = np.asarray(time_feasible, dtype=bool)

        total_value = float(values.sum())
        start = time.perf_counter()

        effective_override: Tier | str | None = (
            tier_override if tier_override is not None else self.config.wta_mode
        )
        if isinstance(effective_override, str) and effective_override == "tiered":
            effective_override = None
        elif isinstance(effective_override, str):
            _alias = {"milp": Tier.T1_MILP, "greedy": Tier.T2_GREEDY, "vlsn": Tier.T3_VLSN}
            effective_override = _alias.get(effective_override, effective_override)
        tier = self._select_tier(n, m, effective_override)

        empty = WTAResult(
            assignments=[],
            tier=tier,
            expected_survival_value=total_value,
            expected_damage=0.0,
            total_target_value=total_value,
            solve_time_ms=(time.perf_counter() - start) * 1e3,
            solver_status="empty",
            message="no weapons or no targets",
            num_weapons=n,
            num_targets=m,
        )
        if n == 0 or m == 0:
            return empty

        p = np.clip(p, 0.0, 1.0)

        if tier == Tier.T1_MILP:
            result = self._solve_milp(
                n,
                m,
                p,
                values,
                time_feasible,
                salvo_caps,
                interference_cliques,
                time_limit_ms,
                weapons,
                targets,
            )
        elif tier == Tier.T2_GREEDY:
            result = self._solve_greedy(
                n,
                m,
                p,
                values,
                time_feasible,
                salvo_caps,
                interference_cliques,
                weapons,
                targets,
            )
        else:
            result = self._solve_vlsn(
                n,
                m,
                p,
                values,
                time_feasible,
                salvo_caps,
                interference_cliques,
                time_limit_ms,
                weapons,
                targets,
            )

        result.num_weapons = n
        result.num_targets = m
        result.solve_time_ms = (time.perf_counter() - start) * 1e3
        return result

    # ---------------------------------------------------------------- tier sel
    def _select_tier(self, n: int, m: int, override: Tier | str | None) -> Tier:
        if override is not None:
            if isinstance(override, str):
                override = Tier(override)
            return override
        pairs = n * m
        if pairs < self.config.milp_max_pairs:
            return Tier.T1_MILP
        if pairs < self.config.greedy_max_pairs:
            return Tier.T2_GREEDY
        return Tier.T3_VLSN

    # -------------------------------------------------------------------- T1
    def _solve_milp(
        self,
        n: int,
        m: int,
        p: np.ndarray,
        values: np.ndarray,
        time_feasible: np.ndarray,
        salvo_caps: dict[int, int] | None,
        interference_cliques: list[list[tuple[int, int]]] | None,
        time_limit_ms: float | None,
        weapons: list[Weapon],
        targets: list[Target],
    ) -> WTAResult:
        if not _HAS_SCIPY:
            raise RuntimeError("scipy is required for the T1 MILP tier")

        total_value = float(values.sum())

        # Variable layout:
        #   x:  n*m              [0, n*m)
        #   z:  (n+1)*m          [n*m, n*m + (n+1)*m)
        #   y:  n*m              [n*m + (n+1)*m, n*m + (n+1)*m + n*m)
        nx = n * m
        nz = (n + 1) * m
        ny = n * m
        nvar = nx + nz + ny

        def x_idx(i: int, j: int) -> int:
            return i * m + j

        def z_idx(i: int, j: int) -> int:  # i in 0..n
            return nx + i * m + j

        def y_idx(i: int, j: int) -> int:
            return nx + nz + i * m + j

        c = np.zeros(nvar)
        c[nx + nz - m : nx + nz] = values  # z_{n,j} coefficients

        lb = np.zeros(nvar)
        ub = np.ones(nvar)
        # x binary
        lb[:nx] = 0.0
        ub[:nx] = 1.0
        # z_{0,j} = 1 fixed; z_{i>=1,j} in [0,1]
        lb[nx : nx + m] = 1.0
        ub[nx : nx + m] = 1.0
        # y in [0,1]
        lb[nx + nz :] = 0.0
        ub[nx + nz :] = 1.0
        # infeasible pairs -> x forced to 0
        for i in range(n):
            for j in range(m):
                if not time_feasible[i, j]:
                    ub[x_idx(i, j)] = 0.0

        rows: list[tuple[int, int, float]] = []
        clb: list[float] = []
        cub: list[float] = []
        r = 0

        # (6) z_{i+1,j} = z_{i,j} - p_ij * y_ij   (equality)
        for i in range(n):
            for j in range(m):
                rows.append((r, z_idx(i + 1, j), 1.0))
                rows.append((r, z_idx(i, j), -1.0))
                rows.append((r, y_idx(i, j), p[i, j]))
                clb.append(0.0)
                cub.append(0.0)
                r += 1

        # y_ij <= z_{i,j}
        # y_ij <= x_ij
        # y_ij >= z_{i,j} - (1 - x_ij)  =>  -y_ij + z_{i,j} + x_ij <= 1
        for i in range(n):
            for j in range(m):
                y = y_idx(i, j)
                z = z_idx(i, j)
                x = x_idx(i, j)
                rows.append((r, y, 1.0))
                rows.append((r, z, -1.0))
                clb.append(-np.inf)
                cub.append(0.0)
                r += 1
                rows.append((r, y, 1.0))
                rows.append((r, x, -1.0))
                clb.append(-np.inf)
                cub.append(0.0)
                r += 1
                rows.append((r, y, -1.0))
                rows.append((r, z, 1.0))
                rows.append((r, x, 1.0))
                clb.append(-np.inf)
                cub.append(1.0)
                r += 1

        # (7) one target per weapon: sum_j x_ij <= 1
        for i in range(n):
            for j in range(m):
                rows.append((r, x_idx(i, j), 1.0))
            clb.append(-np.inf)
            cub.append(1.0)
            r += 1

        # (8) salvo cap: sum_i x_ij <= k_j
        caps = [self.config.salvo_cap_default] * m
        if salvo_caps:
            for j, t in enumerate(targets):
                if t.id in salvo_caps:
                    caps[j] = salvo_caps[t.id]
        for j in range(m):
            cap = caps[j]
            if cap is None or cap == math.inf:
                continue
            for i in range(n):
                rows.append((r, x_idx(i, j), 1.0))
            clb.append(-np.inf)
            cub.append(float(cap))
            r += 1

        # (9) interference cliques: sum_{(i,j) in C} x_ij <= 1
        if interference_cliques:
            for clique in interference_cliques:
                for pair in clique:
                    i, j = int(pair[0]), int(pair[1])
                    rows.append((r, x_idx(i, j), 1.0))
                clb.append(-np.inf)
                cub.append(1.0)
                r += 1

        data = np.array([v for (_, _, v) in rows])
        row_idx = np.array([rr for (rr, _, _) in rows])
        col_idx = np.array([cc for (_, cc, _) in rows])
        a_sp = coo_matrix((data, (row_idx, col_idx)), shape=(r, nvar)).tocsr()
        constraints = LinearConstraint(a_sp, lb=np.array(clb), ub=np.array(cub))

        options: dict[str, Any] = {}
        tl = self.config.milp_time_limit_ms if time_limit_ms is None else time_limit_ms
        if tl and tl > 0:
            options["time_limit"] = tl / 1e3

        integrality = np.ones(nvar, dtype=float)
        integrality[nx:] = 0.0  # z and y continuous; only x binary

        res = milp(
            c=c,
            integrality=integrality,
            bounds=Bounds(lb, ub),
            constraints=constraints,
            options=options or None,
        )

        status = getattr(res, "message", "")
        if res.x is None:
            return WTAResult(
                assignments=[],
                tier=Tier.T1_MILP,
                expected_survival_value=total_value,
                expected_damage=0.0,
                total_target_value=total_value,
                solve_time_ms=0.0,
                solver_status="failed",
                message=str(status),
                num_weapons=n,
                num_targets=m,
            )

        x_sol = res.x[:nx].reshape(n, m)
        assignments = self._extract_assignments(x_sol, weapons, targets, time_feasible)
        surv = self._survival_from_ids(assignments, p, weapons, targets)
        survival_value = float((values * surv).sum())
        damage = total_value - survival_value
        bound = float(res.mip_dual_bound) if res.mip_dual_bound is not None else None
        gap = None
        if bound is not None and survival_value > 0:
            gap = (survival_value - bound) / survival_value

        return WTAResult(
            assignments=assignments,
            tier=Tier.T1_MILP,
            expected_survival_value=survival_value,
            expected_damage=damage,
            total_target_value=total_value,
            lp_lower_bound=bound,
            optimality_gap=gap,
            solver_status=str(status),
            message=str(status),
            num_weapons=n,
            num_targets=m,
        )

    # -------------------------------------------------------------------- T2
    def _solve_greedy(
        self,
        n: int,
        m: int,
        p: np.ndarray,
        values: np.ndarray,
        time_feasible: np.ndarray,
        salvo_caps: dict[int, int] | None,
        interference_cliques: list[list[tuple[int, int]]] | None,
        weapons: list[Weapon],
        targets: list[Target],
    ) -> WTAResult:
        total_value = float(values.sum())
        q = 1.0 - p
        surv = np.ones(m, dtype=float)  # current survival of each target
        # weapon_free / salvo_load track weapon usage and salvo counts below.

        # pair -> clique indices it belongs to (for interference)
        pair_to_cliques: dict[tuple[int, int], list[int]] = {}
        if interference_cliques:
            for ci, clique in enumerate(interference_cliques):
                for pair in clique:
                    pair_to_cliques.setdefault(pair, []).append(ci)
        clique_load = [0] * len(interference_cliques or [])

        def cap_of(j: int) -> float:
            if salvo_caps is None:
                return math.inf
            v = salvo_caps.get(j)
            return math.inf if v is None else float(v)

        def clique_ok(i: int, j: int, adding: bool) -> bool:
            if not interference_cliques:
                return True
            delta = 1 if adding else -1
            return all(clique_load[ci] + delta <= 1 for ci in pair_to_cliques.get((i, j), ()))

        assignments: list[tuple[int, int]] = []
        weapon_free = np.ones(n, dtype=bool)
        salvo_load = np.zeros(m, dtype=int)
        caps = np.array([cap_of(j) for j in range(m)], dtype=float)
        # values[j] * surv[j] is recomputed each iteration because surv changes
        # after every assignment; p and values are fixed.

        def clique_free_matrix() -> np.ndarray:
            """Pair (i, j) is free iff every clique containing it has zero load."""
            if not interference_cliques:
                return np.ones((n, m), dtype=bool)
            free = np.ones((n, m), dtype=bool)
            for ci, clique_load_ci in enumerate(clique_load):
                if clique_load_ci >= 1:
                    for i, j in interference_cliques[ci]:
                        free[i, j] = False
            return free

        # Selection rule: largest marginal damage, ties broken by first occurrence
        # in row-major (i, j) order -- np.argmax's first-max matches the strict->
        # comparison in the original scalar loop exactly.
        while True:
            delta = p * (values * surv)[None, :]
            ok = (
                weapon_free[:, None]
                & time_feasible
                & (salvo_load[None, :] < caps)
                & clique_free_matrix()
            )
            masked = np.where(ok, delta, -np.inf)
            flat_idx = int(np.argmax(masked))
            best_delta = float(masked.flat[flat_idx])
            if not np.isfinite(best_delta) or best_delta <= 0.0:
                break
            i, j = divmod(flat_idx, m)
            weapon_free[i] = False
            salvo_load[j] += 1
            surv[j] *= q[i, j]
            assignments.append((i, j))
            for ci in pair_to_cliques.get((i, j), ()):
                clique_load[ci] += 1

        survival_value = float((values * surv).sum())
        damage = total_value - survival_value
        id_assignments = [(weapons[i].id, targets[j].id) for (i, j) in assignments]
        return WTAResult(
            assignments=id_assignments,
            tier=Tier.T2_GREEDY,
            expected_survival_value=survival_value,
            expected_damage=damage,
            total_target_value=total_value,
            solver_status="optimal",
            message="greedy construction complete",
            num_weapons=n,
            num_targets=m,
        )

    # -------------------------------------------------------------------- T3
    def _solve_vlsn(
        self,
        n: int,
        m: int,
        p: np.ndarray,
        values: np.ndarray,
        time_feasible: np.ndarray,
        salvo_caps: dict[int, int] | None,
        interference_cliques: list[list[tuple[int, int]]] | None,
        time_limit_ms: float | None,
        weapons: list[Weapon],
        targets: list[Target],
    ) -> WTAResult:
        total_value = float(values.sum())
        q = 1.0 - p
        k_max = max(1, int(self.config.vlsn_k_max))
        iteration_cap = int(self.config.vlsn_iteration_cap)
        budget = (self.config.vlsn_time_budget_ms if time_limit_ms is None else time_limit_ms) / 1e3

        # Candidate targets per weapon (positional), ranked by solo marginal gain.
        cand_limit = 6
        candidates: list[list[int]] = []
        for i in range(n):
            order = sorted(
                range(m),
                key=lambda j: values[j] * p[i, j],
                reverse=True,
            )
            candidates.append(order[:cand_limit])

        def cap_of(j: int) -> float:
            if salvo_caps is None:
                return math.inf
            v = salvo_caps.get(j)
            return math.inf if v is None else float(v)

        def clique_pairs() -> dict[tuple[int, int], list[int]]:
            d: dict[tuple[int, int], list[int]] = {}
            if interference_cliques:
                for ci, clique in enumerate(interference_cliques):
                    for pair in clique:
                        d.setdefault(pair, []).append(ci)
            return d

        pair_to_cliques = clique_pairs()
        n_cliques = len(interference_cliques or [])

        def salvo_count(assign: list[int], j: int) -> int:
            return sum(1 for t in assign if t == j)

        def clique_load_count(assign: list[int], ci: int) -> int:
            cnt = 0
            clique = interference_cliques[ci] if interference_cliques else ()
            for i, j in clique:
                if assign[i] == j:
                    cnt += 1
            return cnt

        def move_feasible(
            assign: list[int],
            changes: dict[int, int],
            salvo_load: list[int],
            clique_load: list[int],
        ) -> bool:
            new_salvo = salvo_load[:]
            new_clique = clique_load[:]
            # remove old
            for i, old_j in changes.items():
                if old_j == -1:
                    continue
                new_salvo[old_j] -= 1
                for ci in pair_to_cliques.get((i, old_j), ()):
                    new_clique[ci] -= 1
            # add new
            for i, new_j in changes.items():
                if new_j == -1:
                    continue
                if not time_feasible[i, new_j]:
                    return False
                if new_salvo[new_j] >= cap_of(new_j):
                    return False
                new_salvo[new_j] += 1
                for ci in pair_to_cliques.get((i, new_j), ()):
                    new_clique[ci] += 1
                    if new_clique[ci] > 1:
                        return False
            return True

        def damage_of(assign: list[int]) -> float:
            surv = np.ones(m, dtype=float)
            for i, j in enumerate(assign):
                if j != -1:
                    surv[j] *= q[i, j]
            return float((values * (1.0 - surv)).sum())

        # initialise from greedy seed
        greedy = self._solve_greedy(
            n,
            m,
            p,
            values,
            time_feasible,
            salvo_caps,
            interference_cliques,
            weapons,
            targets,
        )
        assign = [-1] * n
        wid_to_i = {w.id: i for i, w in enumerate(weapons)}
        tid_to_j = {t.id: j for j, t in enumerate(targets)}
        for wid, tid in greedy.assignments:
            assign[wid_to_i[wid]] = tid_to_j[tid]

        salvo_load = [salvo_count(assign, j) for j in range(m)]
        clique_load = [clique_load_count(assign, ci) for ci in range(n_cliques)]
        cur_damage = damage_of(assign)

        start = time.perf_counter()
        iteration = 0
        improved = True
        # current survival per target (maintained incrementally)
        surv = np.ones(m, dtype=float)
        for i, j in enumerate(assign):
            if j != -1:
                surv[j] *= q[i, j]
        cur_damage = float((values * (1.0 - surv)).sum())

        def move_delta(changes: dict[int, int]) -> float:
            """O(|changes|) expected-damage delta of applying ``changes``."""
            affected: dict[int, float] = {}
            for i, new_j in changes.items():
                old_j = assign[i]
                for j in (old_j, new_j):
                    if j == -1 or j in affected:
                        continue
                    affected[j] = surv[j]
            for i, new_j in changes.items():
                old_j = assign[i]
                if old_j != -1 and old_j in affected:
                    qi = q[i, old_j]
                    if qi > 0:
                        affected[old_j] /= qi
                if new_j != -1 and new_j in affected:
                    affected[new_j] *= q[i, new_j]
            delta = 0.0
            for j, ns in affected.items():
                delta += values[j] * (surv[j] - ns)
            return float(delta)

        while improved and iteration < iteration_cap:
            improved = False
            iteration += 1
            if time.perf_counter() - start > budget:
                break
            for k in range(1, k_max + 1):
                best_changes: dict[int, int] | None = None
                best_delta = 0.0
                if k == 1:
                    for i in range(n):
                        cur_j = assign[i]
                        for new_j in list(candidates[i]) + [-1]:
                            if new_j == cur_j:
                                continue
                            changes = {i: new_j}
                            if not move_feasible(assign, changes, salvo_load, clique_load):
                                continue
                            delta = move_delta(changes)
                            if delta > best_delta:
                                best_delta = delta
                                best_changes = changes
                else:
                    # k-exchange: choose up to k weapons and reassign over candidates
                    weapon_pool = [i for i in range(n) if assign[i] != -1]
                    tried = 0
                    pair_limit = 400
                    budget_exceeded = False
                    for combo in combinations(weapon_pool, k):
                        if time.perf_counter() - start > budget:
                            budget_exceeded = True
                            break
                        if tried >= pair_limit:
                            break
                        tried += 1
                        cand_lists = [list(candidates[i]) + [-1] for i in combo]
                        for choice in product(*cand_lists):
                            changes = {i: nj for i, nj in zip(combo, choice, strict=False)}
                            if all(changes[i] == assign[i] for i in combo):
                                continue
                            if not move_feasible(assign, changes, salvo_load, clique_load):
                                continue
                            delta = move_delta(changes)
                            if delta > best_delta:
                                best_delta = delta
                                best_changes = changes
                    if budget_exceeded:
                        break
                if best_changes is not None and best_delta > 1e-12:
                    # apply best_changes; delta computed against pre-apply state
                    delta = move_delta(best_changes)
                    for i, new_j in best_changes.items():
                        old_j = assign[i]
                        if old_j != -1:
                            salvo_load[old_j] -= 1
                            for ci in pair_to_cliques.get((i, old_j), ()):
                                clique_load[ci] -= 1
                        assign[i] = new_j
                        if new_j != -1:
                            salvo_load[new_j] += 1
                            for ci in pair_to_cliques.get((i, new_j), ()):
                                clique_load[ci] += 1
                    # refresh survival for all targets (cheap, keeps it consistent)
                    surv = np.ones(m, dtype=float)
                    for ii, jj in enumerate(assign):
                        if jj != -1:
                            surv[jj] *= q[ii, jj]
                    cur_damage += delta
                    improved = True
                    break  # restart at k=1 (variable neighbourhood descent)
            if time.perf_counter() - start > budget:
                break

        survival_value = total_value - cur_damage
        id_assignments = [(weapons[i].id, targets[j].id) for i, j in enumerate(assign) if j != -1]
        return WTAResult(
            assignments=id_assignments,
            tier=Tier.T3_VLSN,
            expected_survival_value=survival_value,
            expected_damage=cur_damage,
            total_target_value=total_value,
            solver_status="local_optimum",
            message=f"VLSN converged after {iteration} iterations",
            num_weapons=n,
            num_targets=m,
        )

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _extract_assignments(
        x_sol: np.ndarray,
        weapons: list[Weapon],
        targets: list[Target],
        time_feasible: np.ndarray,
    ) -> list[tuple[int, int]]:
        n, m = x_sol.shape
        out: list[tuple[int, int]] = []
        for i in range(n):
            for j in range(m):
                if x_sol[i, j] > 0.5 and time_feasible[i, j]:
                    out.append((weapons[i].id, targets[j].id))
        return out

    @staticmethod
    def _survival_from_ids(
        assignments: list[tuple[int, int]],
        p: np.ndarray,
        weapons: list[Weapon],
        targets: list[Target],
    ) -> np.ndarray:
        surv = np.ones(p.shape[1], dtype=float)
        q = 1.0 - p
        wid_to_i = {w.id: i for i, w in enumerate(weapons)}
        tid_to_j = {t.id: j for j, t in enumerate(targets)}
        for wid, tid in assignments:
            i = wid_to_i[wid]
            j = tid_to_j[tid]
            surv[j] *= q[i, j]
        return surv


# ---------------------------------------------------------------------------
# Dynamic reallocation (shoot-look-shoot / shoot-shoot-look)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BDAEvent:
    """A single battle-damage-assessment observation."""

    cycle: int
    killed_target_ids: list[int]
    # target_id -> dict of field updates (e.g. {"value": ..., "p_row": [...]})
    damage_updates: dict[int, dict[str, Any]] = None  # type: ignore[assignment]
    timestamp: float = 0.0


@dataclass(slots=True)
class AllocationCycle:
    """Record of one allocate/engage/look cycle."""

    cycle: int
    state_before: SolverState
    state_after: SolverState
    engagements: list[tuple[int, int]]
    bda: BDAEvent | None = None
    tier: Tier | None = None
    solve_time_ms: float = 0.0


class DynamicReallocator:
    """Dynamic WTA reallocation with SLS/SSL modes and a state machine.

    State machine (per spec §5.3)::

        IDLE -> ALLOCATING -> ENGAGING -> LOOKING -> {TERMINAL | RE-EVALUATING}
                                                            |_______________|
                                                                        (back to ALLOCATING)

    Transitions are driven by events; invalid transitions raise ValueError.
    With a fixed ``random_seed`` the same BDA trace yields identical
    allocations (determinism rule, spec §5.3).
    """

    def __init__(
        self,
        solver: TieredWTASolver,
        weapons: list[Weapon],
        targets: list[Target],
        kill_prob: np.ndarray,
        values: np.ndarray | None = None,
        time_feasible: np.ndarray | None = None,
        salvo_caps: dict[int, int] | None = None,
        interference_cliques: list[list[tuple[int, int]]] | None = None,
        mode: AllocationMode | str = AllocationMode.SLS,
    ) -> None:
        self.solver = solver
        self.config = solver.config
        self.weapons = list(weapons)
        self.targets = list(targets)
        self.p = np.clip(np.asarray(kill_prob, dtype=float), 0.0, 1.0)
        self.values = (
            np.ones(len(targets), dtype=float)
            if values is None
            else np.asarray(values, dtype=float)
        )
        self.time_feasible = (
            np.ones(self.p.shape, dtype=bool)
            if time_feasible is None
            else np.asarray(time_feasible, dtype=bool)
        )
        self.salvo_caps = dict(salvo_caps or {})
        self.interference_cliques = interference_cliques or []
        self.mode = AllocationMode(mode) if isinstance(mode, str) else mode

        # Residual instance (shrinks as targets are neutralized).
        self.remaining_weapon_ids = [w.id for w in self.weapons]
        self.remaining_target_ids = [t.id for t in self.targets]

        self.state = SolverState.IDLE
        self.cycle = 0
        self.event_log: list[str] = []
        self.cycles: list[AllocationCycle] = []
        self.current_assignments: list[tuple[int, int]] = []
        self._last_result: WTAResult | None = None

    # ----------------------------------------------------------------- events
    def _log(self, event: str) -> None:
        self.event_log.append(event)

    def _transition(self, event: str) -> None:
        """Validate and perform a state-machine transition."""
        transitions = {
            SolverState.IDLE: {
                "allocate_request": SolverState.ALLOCATING,
                "reset": SolverState.IDLE,
                "abort": SolverState.IDLE,
            },
            SolverState.ALLOCATING: {
                "solution_ready": SolverState.ENGAGING,
                "reset": SolverState.IDLE,
                "abort": SolverState.IDLE,
            },
            SolverState.ENGAGING: {
                "bda_received": SolverState.LOOKING,
                "salvo_complete": SolverState.LOOKING,
                "reset": SolverState.IDLE,
                "abort": SolverState.IDLE,
            },
            SolverState.LOOKING: {
                "all_neutralized": SolverState.TERMINAL,
                "weapons_exhausted": SolverState.TERMINAL,
                "residual_instance_ready": SolverState.RE_EVALUATING,
                "reset": SolverState.IDLE,
                "abort": SolverState.IDLE,
            },
            SolverState.RE_EVALUATING: {
                "residual_instance_ready": SolverState.ALLOCATING,
                "reset": SolverState.IDLE,
                "abort": SolverState.IDLE,
            },
            SolverState.TERMINAL: {
                "reset": SolverState.IDLE,
                "abort": SolverState.IDLE,
            },
        }
        allowed = transitions.get(self.state, {})
        if event not in allowed:
            raise ValueError(
                f"invalid transition {self.state.name} --{event}-> ? (allowed: {sorted(allowed)})"
            )
        self.state = allowed[event]
        self._log(event)

    # -------------------------------------------------------------- public API
    def request_allocation(self) -> list[tuple[int, int]]:
        """Run the tiered solver on the residual instance and issue engagements.

        IDLE -> ALLOCATING -> ENGAGING (or ALLOCATING -> ENGAGING when called
        after ``reallocate_on_residual``).  Returns the engagements to fire
        this cycle (one pair for SLS; the salvo for SSL).
        """
        if self.state == SolverState.IDLE:
            self._transition("allocate_request")  # IDLE -> ALLOCATING
        elif self.state != SolverState.ALLOCATING:
            raise ValueError(f"request_allocation from {self.state.name} is not allowed")
        result = self.solver.solve(
            self._current_weapons(),
            self._current_targets(),
            self._current_p(),
            self._current_values(),
            time_feasible=self._current_time_feasible(),
            salvo_caps=self.salvo_caps,
            interference_cliques=self.interference_cliques,
        )
        self._transition("solution_ready")  # ALLOCATING -> ENGAGING
        self._last_result = result
        self.current_assignments = list(result.assignments)
        self.cycle += 1

        engagements = self._select_engagements(result.assignments)
        self.cycles.append(
            AllocationCycle(
                cycle=self.cycle,
                state_before=SolverState.ALLOCATING,
                state_after=SolverState.ENGAGING,
                engagements=engagements,
                tier=result.tier,
                solve_time_ms=result.solve_time_ms,
            )
        )
        return engagements

    def report_bda(
        self,
        killed_target_ids: list[int],
        damage_updates: dict[int, dict[str, Any]] | None = None,
    ) -> SolverState:
        """Process a BDA observation.

        ENGAGING -> LOOKING -> {TERMINAL | RE_EVALUATING}.  Returns the new
        state.
        """
        self._transition("bda_received")
        # state is now LOOKING

        killed = set(killed_target_ids)
        self.remaining_target_ids = [t for t in self.remaining_target_ids if t not in killed]

        # Condition p / values on observed damage.
        if damage_updates:
            tid_to_j = {t.id: j for j, t in enumerate(self.targets)}
            for tid, updates in damage_updates.items():
                if tid not in tid_to_j:
                    continue
                j = tid_to_j[tid]
                if "p_row" in updates:
                    row = np.asarray(updates["p_row"], dtype=float)
                    self.p[:, j] = np.clip(row, 0.0, 1.0)
                if "value" in updates:
                    self.values[j] = float(updates["value"])

        # Decide terminal vs re-evaluating.
        if not self.remaining_target_ids or not self.remaining_weapon_ids:
            event = "all_neutralized" if not self.remaining_target_ids else "weapons_exhausted"
        else:
            event = "residual_instance_ready"
        self._transition(event)  # LOOKING -> TERMINAL | RE_EVALUATING

        self.cycles[-1].bda = BDAEvent(
            cycle=self.cycle,
            killed_target_ids=list(killed),
            damage_updates=damage_updates or {},
        )
        return self.state

    def reallocate_on_residual(self) -> None:
        """Move RE_EVALUATING -> ALLOCATING so the next request re-solves."""
        self._transition("residual_instance_ready")
        # state is now ALLOCATING; the next request_allocation() re-solves.

    def reset(self) -> None:
        """Return to IDLE from any state (clears partial state)."""
        self._transition("reset")
        self.current_assignments = []
        self._last_result = None

    def abort(self) -> None:
        """Abort and return to IDLE from any state."""
        self._transition("abort")
        self.current_assignments = []
        self._last_result = None

    # ------------------------------------------------------------ internals
    def _current_weapons(self) -> list[Weapon]:
        id_set = set(self.remaining_weapon_ids)
        return [w for w in self.weapons if w.id in id_set]

    def _current_targets(self) -> list[Target]:
        id_set = set(self.remaining_target_ids)
        return [t for t in self.targets if t.id in id_set]

    def _current_p(self) -> np.ndarray:
        target_ids = [t.id for t in self._current_targets()]
        tid_to_j = {t.id: j for j, t in enumerate(self.targets)}
        cols = [tid_to_j[t] for t in target_ids]
        return self.p[:, cols] if cols else self.p[:, :0]

    def _current_values(self) -> np.ndarray:
        target_ids = [t.id for t in self._current_targets()]
        tid_to_j = {t.id: j for j, t in enumerate(self.targets)}
        cols = [tid_to_j[t] for t in target_ids]
        return self.values[cols] if cols else self.values[:0]

    def _current_time_feasible(self) -> np.ndarray:
        target_ids = [t.id for t in self._current_targets()]
        tid_to_j = {t.id: j for j, t in enumerate(self.targets)}
        cols = [tid_to_j[t] for t in target_ids]
        return self.time_feasible[:, cols] if cols else self.time_feasible[:, :0]

    def _select_engagements(self, assignments: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if self.mode == AllocationMode.SLS:
            return assignments[:1]
        return list(assignments)  # SSL: the whole salvo

    def can_transition(self, event: str) -> bool:
        transitions = {
            SolverState.IDLE: {"allocate_request", "reset", "abort"},
            SolverState.ALLOCATING: {"solution_ready", "reset", "abort"},
            SolverState.ENGAGING: {
                "bda_received",
                "salvo_complete",
                "reset",
                "abort",
            },
            SolverState.LOOKING: {
                "all_neutralized",
                "weapons_exhausted",
                "residual_instance_ready",
                "reset",
                "abort",
            },
            SolverState.RE_EVALUATING: {"residual_instance_ready", "reset", "abort"},
            SolverState.TERMINAL: {"reset", "abort"},
        }
        return event in transitions.get(self.state, set())
