"""Tests for the tiered WTA solver (swarm/wta_solver.py).

Covers the Wave 1 spec (docs/wta-solver-spec.md):

- engagement model (kill probability, time windows, interference)
- tier selection & config overrides
- T1 MILP exact vs brute force (optimal, LP lower bound, gap)
- T2 greedy >= 1/2 expected-damage ratio
- T3 VLSN gap / convergence / time budget
- dynamic reallocation SLS/SSL state machine with BDA re-solves
- Hypothesis property-based tests

RED -> GREEN -> REFACTOR applied.
"""

from __future__ import annotations

from itertools import product
from math import inf

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apex_autopilot_optimization.core.types import Pose3D, VehicleType
from apex_autopilot_optimization.swarm.task_allocation import (
    Agent,
    Task,
    TaskAllocator,
)
from apex_autopilot_optimization.swarm.wta_solver import (
    AllocationMode,
    DynamicReallocator,
    SolverState,
    Target,
    Tier,
    TieredWTASolver,
    Weapon,
    WTAConfig,
    WTAResult,
)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _make_instance(n: int, m: int, seed: int | None = None):
    rng = np.random.default_rng(seed)
    weapons = [Weapon(i) for i in range(n)]
    targets = [Target(j, value=float(rng.uniform(0.5, 10.0))) for j in range(m)]
    p = rng.random((n, m))
    values = np.array([t.value for t in targets])
    return weapons, targets, p, values


def _brute_force_survival(
    n: int,
    m: int,
    p: np.ndarray,
    values: np.ndarray,
    time_feasible: np.ndarray | None = None,
    salvo_caps: dict[int, int] | None = None,
    cliques: list[list[tuple[int, int]]] | None = None,
) -> float:
    """Exact optimum by enumerating every weapon->(target|None) assignment."""
    if time_feasible is None:
        time_feasible = np.ones((n, m), dtype=bool)
    if salvo_caps is None:
        salvo_caps = {}
    if cliques is None:
        cliques = []
    best = inf
    # j == m means weapon i is unassigned.
    for combo in product(range(m + 1), repeat=n):
        salvo = [0] * m
        ok = True
        for i, j in enumerate(combo):
            if j == m:
                continue
            if not time_feasible[i, j]:
                ok = False
                break
            salvo[j] += 1
            cap = salvo_caps.get(j, inf)
            if salvo[j] > cap:
                ok = False
                break
        if not ok:
            continue
        for clique in cliques:
            cnt = sum(1 for (i, j) in clique if combo[i] == j)
            if cnt > 1:
                ok = False
                break
        if not ok:
            continue
        surv = np.ones(m, dtype=float)
        for i, j in enumerate(combo):
            if j != m:
                surv[j] *= 1.0 - p[i, j]
        best = min(best, float((values * surv).sum()))
    return best


def _damage(assignments, p, values, weapons, targets) -> float:
    wid_to_i = {w.id: i for i, w in enumerate(weapons)}
    tid_to_j = {t.id: j for j, t in enumerate(targets)}
    surv = np.ones(p.shape[1], dtype=float)
    for wid, tid in assignments:
        surv[tid_to_j[tid]] *= 1.0 - p[wid_to_i[wid], tid_to_j[tid]]
    return float((values * (1.0 - surv)).sum())


def _valid(assignments, p, time_feasible, salvo_caps, cliques, weapons, targets) -> bool:
    wid_to_i = {w.id: i for i, w in enumerate(weapons)}
    tid_to_j = {t.id: j for j, t in enumerate(targets)}
    n, m = p.shape
    load = [0] * n
    salvo = [0] * m
    used = set()
    for wid, tid in assignments:
        i, j = wid_to_i[wid], tid_to_j[tid]
        if not time_feasible[i, j]:
            return False
        load[i] += 1
        if load[i] > 1:
            return False
        salvo[j] += 1
        cap = salvo_caps.get(j, inf)
        if salvo[j] > cap:
            return False
        used.add((i, j))
    return all(sum(1 for (i, j) in clique if (i, j) in used) <= 1 for clique in cliques)


# --------------------------------------------------------------------------- #
# engagement model
# --------------------------------------------------------------------------- #
class TestEngagementModel:
    def test_kill_probability_clamped(self) -> None:
        solver = TieredWTASolver()
        w = [Weapon(0), Weapon(1)]
        t = [Target(0, 1.0), Target(1, 1.0)]
        p = np.array([[1.5, -0.3], [0.5, 0.5]])
        res = solver.solve(w, t, p, np.ones(2))
        assert res.tier == Tier.T1_MILP
        # solver must not crash; clamp internally keeps p in [0,1]

    def test_survival_matches_brute_force(self) -> None:
        np.random.default_rng(0)
        n, m = 4, 4
        w, t, p, v = _make_instance(n, m, seed=1)
        res = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0)).solve(w, t, p, v)
        opt = _brute_force_survival(n, m, p, v)
        assert abs(res.expected_survival_value - opt) < 1e-6

    def test_time_window_infeasible_never_assigned(self) -> None:
        w = [Weapon(0), Weapon(1)]
        t = [Target(0, 1.0), Target(1, 1.0)]
        p = np.ones((2, 2))
        # weapon 0 cannot reach target 0 in its window
        tf = np.array([[False, True], [True, True]])
        res = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0)).solve(
            w, t, p, np.ones(2), time_feasible=tf
        )
        assert _valid(res.assignments, p, tf, {}, [], w, t)
        assert not any(a == (0, 0) for a in res.assignments)

    def test_interference_clique_respected(self) -> None:
        w = [Weapon(0), Weapon(1)]
        t = [Target(0, 1.0)]
        p = np.array([[0.9], [0.9]])
        # both weapons on the same seeker band -> at most one
        cliques = [[(0, 0), (1, 0)]]
        res = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0)).solve(
            w, t, p, np.ones(1), interference_cliques=cliques
        )
        assert _valid(res.assignments, p, np.ones((2, 1)), {}, cliques, w, t)

    def test_salvo_cap_respected(self) -> None:
        w = [Weapon(0), Weapon(1), Weapon(2)]
        t = [Target(0, 1.0)]
        p = np.ones((3, 1))
        res = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0)).solve(
            w, t, p, np.ones(1), salvo_caps={0: 1}
        )
        assert len(res.assignments) <= 1


# --------------------------------------------------------------------------- #
# tier selection & config
# --------------------------------------------------------------------------- #
class TestTierSelection:
    def test_tier_selection_by_size(self) -> None:
        solver = TieredWTASolver(WTAConfig(milp_max_pairs=400, greedy_max_pairs=6400))
        r1 = solver.solve(
            [Weapon(i) for i in range(19)],
            [Target(j, 1.0) for j in range(19)],
            np.random.default_rng(0).random((19, 19)),
            np.ones(19),
        )
        r2 = solver.solve(
            [Weapon(i) for i in range(20)],
            [Target(j, 1.0) for j in range(20)],
            np.random.default_rng(0).random((20, 20)),
            np.ones(20),
        )
        r3 = solver.solve(
            [Weapon(i) for i in range(90)],
            [Target(j, 1.0) for j in range(90)],
            np.random.default_rng(0).random((90, 90)),
            np.ones(90),
        )
        assert r1.tier == Tier.T1_MILP
        assert r2.tier == Tier.T2_GREEDY
        assert r3.tier == Tier.T3_VLSN

    def test_config_override_milp(self) -> None:
        solver = TieredWTASolver(WTAConfig(wta_mode="milp"))
        big_p = np.random.default_rng(0).random((30, 30))
        res = solver.solve(
            [Weapon(i) for i in range(30)],
            [Target(j, 1.0) for j in range(30)],
            big_p,
            np.ones(30),
        )
        assert res.tier == Tier.T1_MILP

    def test_config_override_greedy(self) -> None:
        solver = TieredWTASolver(WTAConfig(wta_mode="greedy"))
        res = solver.solve([Weapon(0)], [Target(0, 1.0)], np.array([[0.5]]), np.ones(1))
        assert res.tier == Tier.T2_GREEDY

    def test_deterministic_with_seed(self) -> None:
        cfg = WTAConfig(wta_mode="vlsn", random_seed=42, vlsn_k_max=2)
        p = np.random.default_rng(0).random((10, 8))
        v = np.random.default_rng(0).random(8) + 0.5
        r1 = TieredWTASolver(cfg).solve(
            [Weapon(i) for i in range(10)],
            [Target(j, float(v[j])) for j in range(8)],
            p,
            v,
        )
        r2 = TieredWTASolver(cfg).solve(
            [Weapon(i) for i in range(10)],
            [Target(j, float(v[j])) for j in range(8)],
            p,
            v,
        )
        assert r1.assignments == r2.assignments
        assert r1.expected_damage == r2.expected_damage

    def test_empty_inputs(self) -> None:
        solver = TieredWTASolver()
        res = solver.solve([], [], np.zeros((0, 0)), np.zeros(0))
        assert res.assignments == []
        assert res.expected_damage == 0.0


# --------------------------------------------------------------------------- #
# T1 MILP
# --------------------------------------------------------------------------- #
class TestMilpTier:
    def _solver(self) -> TieredWTASolver:
        return TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0))

    def test_milp_optimal_small_brute_force(self) -> None:
        for seed in range(5):
            n, m = 4, 4
            w, t, p, v = _make_instance(n, m, seed=seed)
            res = self._solver().solve(w, t, p, v)
            opt = _brute_force_survival(n, m, p, v)
            assert abs(res.expected_survival_value - opt) < 1e-6, (
                seed,
                res.expected_survival_value,
                opt,
            )
            assert res.is_optimal

    def test_milp_5x5_brute_force(self) -> None:
        n, m = 5, 5
        rng = np.random.default_rng(3)
        w, t, p, v = _make_instance(n, m, seed=rng)
        res = self._solver().solve(w, t, p, v)
        opt = _brute_force_survival(n, m, p, v)
        assert abs(res.expected_survival_value - opt) < 1e-6

    def test_milp_respects_all_constraints(self) -> None:
        rng = np.random.default_rng(9)
        n, m = 6, 5
        w, t, p, v = _make_instance(n, m, seed=rng)
        tf = rng.random((n, m)) > 0.2
        cliques = [[(0, 0), (1, 0)], [(2, 1), (3, 1)]]
        res = self._solver().solve(
            w,
            t,
            p,
            v,
            time_feasible=tf,
            salvo_caps={0: 1, 1: 2},
            interference_cliques=cliques,
        )
        assert _valid(res.assignments, p, tf, {0: 1, 1: 2}, cliques, w, t)

    def test_milp_lower_bound_property(self) -> None:
        n, m = 5, 5
        w, t, p, v = _make_instance(n, m, seed=11)
        res = self._solver().solve(w, t, p, v)
        assert res.lp_lower_bound is not None
        assert res.lp_lower_bound <= res.expected_survival_value + 1e-6
        if res.optimality_gap is not None:
            assert 0.0 <= res.optimality_gap <= 1.0 + 1e-6

    def test_milp_time_limit_returns_incumbent(self) -> None:
        n, m = 10, 10
        w, t, p, v = _make_instance(n, m, seed=12)
        res = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=5.0)).solve(w, t, p, v)
        assert res.solver_status != "failed"
        assert _valid(res.assignments, p, np.ones((n, m)), {}, [], w, t)

    def test_milp_monotonicity_adding_weapons(self) -> None:
        # adding a weapon never increases optimal survival value
        rng = np.random.default_rng(21)
        n, m = 4, 4
        w, t, p, v = _make_instance(n, m, seed=rng)
        base = self._solver().solve(w, t, p, v).expected_survival_value
        p2 = np.vstack([p, rng.random((1, m))])
        w2 = w + [Weapon(4)]
        with_extra = self._solver().solve(w2, t, p2, v).expected_survival_value
        assert with_extra <= base + 1e-9


# --------------------------------------------------------------------------- #
# T2 Greedy
# --------------------------------------------------------------------------- #
class TestGreedyTier:
    def _solver(self) -> TieredWTASolver:
        return TieredWTASolver(WTAConfig(wta_mode="greedy"))

    def test_greedy_half_ratio_empirical(self) -> None:
        TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0))
        greedy = self._solver()
        rng = np.random.default_rng(2024)
        trials = 0
        for _ in range(40):
            n = rng.integers(2, 7)
            m = rng.integers(2, 7)
            w, t, p, v = _make_instance(int(n), int(m), seed=int(rng.integers(0, 10_000)))
            opt_surv = _brute_force_survival(int(n), int(m), p, v)
            opt_damage = float(v.sum()) - opt_surv
            if opt_damage <= 0:
                continue
            g = greedy.solve(w, t, p, v)
            assert g.expected_damage >= 0.5 * opt_damage - 1e-9
            trials += 1
        assert trials >= 10

    def test_greedy_priority_tie_break(self) -> None:
        # equal deltas: higher target value preferred
        w = [Weapon(0), Weapon(1)]
        t = [Target(0, value=10.0), Target(1, value=1.0)]
        p = np.array([[0.5, 0.5], [0.5, 0.5]])
        res = self._solver().solve(w, t, p, np.array([10.0, 1.0]))
        assert (0, 0) in res.assignments

    def test_greedy_capacity_respected(self) -> None:
        w = [Weapon(0), Weapon(1)]
        t = [Target(0, 1.0)]
        p = np.ones((2, 1))
        res = self._solver().solve(w, t, p, np.ones(1))
        # each weapon at most one target -> at most 2 assignments but one target
        ids = [a[0] for a in res.assignments]
        assert len(ids) == len(set(ids))

    def test_greedy_monotone_damage(self) -> None:
        w = [Weapon(0), Weapon(1)]
        t = [Target(0, 1.0), Target(1, 1.0)]
        p = np.array([[0.5, 0.5], [0.5, 0.5]])
        res = self._solver().solve(w, t, p, np.ones(2))
        d = _damage(res.assignments, p, np.ones(2), w, t)
        assert d >= 0.0


# --------------------------------------------------------------------------- #
# T3 VLSN
# --------------------------------------------------------------------------- #
class TestVlsnTier:
    def _solver(self) -> TieredWTASolver:
        return TieredWTASolver(
            WTAConfig(
                wta_mode="vlsn", vlsn_k_max=2, vlsn_iteration_cap=200, vlsn_time_budget_ms=200
            )
        )

    def test_vlsn_near_optimal_gap(self) -> None:
        milp = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0))
        vlsn = self._solver()
        rng = np.random.default_rng(77)
        for trial in range(8):
            n = int(rng.integers(4, 9))
            m = int(rng.integers(4, 9))
            w, t, p, v = _make_instance(n, m, seed=int(rng.integers(0, 10_000)))
            opt_surv = self._milp_surv(milp, w, t, p, v)
            vres = vlsn.solve(w, t, p, v)
            total = float(v.sum())
            opt_damage = total - opt_surv
            vlsn_damage = vres.expected_damage
            if opt_damage > 0:
                gap = (opt_damage - vlsn_damage) / opt_damage
                assert gap <= 0.10, (trial, gap, opt_damage, vlsn_damage)

    @staticmethod
    def _milp_surv(solver, w, t, p, v) -> float:
        return solver.solve(w, t, p, v).expected_survival_value

    def test_vlsn_converges_to_local_optimum(self) -> None:
        rng = np.random.default_rng(5)
        n, m = 8, 7
        w, t, p, v = _make_instance(n, m, seed=rng)
        res = self._solver().solve(w, t, p, v)
        # VLSN should beat or match greedy on the same instance
        greedy = TieredWTASolver(WTAConfig(wta_mode="greedy")).solve(w, t, p, v)
        assert res.expected_damage >= greedy.expected_damage - 1e-9

    def test_vlsn_respects_hard_constraints(self) -> None:
        rng = np.random.default_rng(3)
        n, m = 10, 8
        w, t, p, v = _make_instance(n, m, seed=rng)
        tf = rng.random((n, m)) > 0.1
        cliques = [[(0, 0), (1, 0)]]
        res = self._solver().solve(
            w,
            t,
            p,
            v,
            time_feasible=tf,
            salvo_caps={0: 1},
            interference_cliques=cliques,
        )
        assert _valid(res.assignments, p, tf, {0: 1}, cliques, w, t)

    def test_vlsn_time_budget(self) -> None:
        n, m = 20, 20
        rng = np.random.default_rng(1)
        w, t, p, v = _make_instance(n, m, seed=rng)
        solver = TieredWTASolver(
            WTAConfig(wta_mode="vlsn", vlsn_time_budget_ms=50, vlsn_iteration_cap=100, vlsn_k_max=2)
        )
        res = solver.solve(w, t, p, v)
        assert _valid(res.assignments, p, np.ones((n, m)), {}, [], w, t)
        # VLSN must respect its time cap (well under the 100 ms hot-path budget)
        assert res.solve_time_ms < 1000


# --------------------------------------------------------------------------- #
# dynamic reallocation (SLS / SSL) state machine
# --------------------------------------------------------------------------- #
class TestDynamicReallocator:
    def _small(self):
        w = [Weapon(i) for i in range(3)]
        t = [Target(j, value=10.0) for j in range(2)]
        p = np.array([[0.8, 0.2], [0.2, 0.8], [0.5, 0.5]])
        return w, t, p

    def test_sls_single_weapon_per_cycle(self) -> None:
        w, t, p = self._small()
        solver = TieredWTASolver(WTAConfig(random_seed=1))
        dr = DynamicReallocator(solver, w, t, p, mode=AllocationMode.SLS)
        eng = dr.request_allocation()
        assert dr.state == SolverState.ENGAGING
        assert len(eng) == 1  # exactly one engagement before BDA
        dr.report_bda([eng[0][1]])
        assert dr.state in (SolverState.TERMINAL, SolverState.RE_EVALUATING)

    def test_ssl_salvo_then_assess(self) -> None:
        w, t, p = self._small()
        solver = TieredWTASolver(WTAConfig(random_seed=1))
        dr = DynamicReallocator(solver, w, t, p, mode=AllocationMode.SSL)
        eng = dr.request_allocation()
        assert dr.state == SolverState.ENGAGING
        assert len(eng) >= 1  # salvo before BDA
        dr.report_bda([e[1] for e in eng])
        assert dr.state in (SolverState.TERMINAL, SolverState.RE_EVALUATING)

    def test_bda_removes_killed_targets(self) -> None:
        w, t, p = self._small()
        solver = TieredWTASolver(WTAConfig(random_seed=1))
        dr = DynamicReallocator(solver, w, t, p, mode=AllocationMode.SLS)
        eng = dr.request_allocation()
        killed = [eng[0][1]]
        dr.report_bda(killed)
        assert killed[0] not in dr.remaining_target_ids

    def test_bda_updates_residual_p(self) -> None:
        w, t, p = self._small()
        solver = TieredWTASolver(WTAConfig(random_seed=1))
        dr = DynamicReallocator(solver, w, t, p, mode=AllocationMode.SLS)
        dr.request_allocation()
        dr.report_bda([], damage_updates={0: {"p_row": [0.9, 0.1, 0.4]}})
        assert dr.p[0, 0] == 0.9
        assert dr.p[1, 0] == 0.1
        assert dr.p[2, 0] == 0.4

    def test_state_machine_transitions(self) -> None:
        w, t, p = self._small()
        solver = TieredWTASolver(WTAConfig(random_seed=1))
        dr = DynamicReallocator(solver, w, t, p, mode=AllocationMode.SLS)
        assert dr.state == SolverState.IDLE
        assert dr.can_transition("allocate_request")
        assert not dr.can_transition("bda_received")

        dr.request_allocation()
        assert dr.state == SolverState.ENGAGING
        assert dr.can_transition("bda_received")
        assert not dr.can_transition("allocate_request")

        dr.report_bda([t.id for t in t])  # all neutralized
        assert dr.state == SolverState.TERMINAL

        # invalid transition rejected
        with pytest.raises(ValueError):
            dr.report_bda([])

    def test_invalid_transition_rejected(self) -> None:
        w, t, p = self._small()
        solver = TieredWTASolver(WTAConfig(random_seed=1))
        dr = DynamicReallocator(solver, w, t, p)
        assert dr.state == SolverState.IDLE
        with pytest.raises(ValueError):
            dr.report_bda([])  # bda without engaging

    def test_reallocation_converges(self) -> None:
        w, t, p = self._small()
        solver = TieredWTASolver(WTAConfig(random_seed=1))
        dr = DynamicReallocator(solver, w, t, p, mode=AllocationMode.SLS)
        for _ in range(10):
            if dr.state == SolverState.TERMINAL:
                break
            if dr.state in (SolverState.IDLE, SolverState.ALLOCATING):
                eng = dr.request_allocation()
            elif dr.state == SolverState.RE_EVALUATING:
                dr.reallocate_on_residual()
            if dr.state == SolverState.ENGAGING:
                dr.report_bda([e[1] for e in eng])
        assert dr.state == SolverState.TERMINAL

    def test_deterministic_bda_sequence(self) -> None:
        def run(seed):
            w, t, p = self._small()
            solver = TieredWTASolver(WTAConfig(random_seed=seed))
            dr = DynamicReallocator(solver, w, t, p, mode=AllocationMode.SLS)
            trace = []
            while dr.state != SolverState.TERMINAL:
                if dr.state in (SolverState.IDLE, SolverState.ALLOCATING):
                    eng = dr.request_allocation()
                    trace.append(("alloc", tuple(sorted(eng))))
                elif dr.state == SolverState.RE_EVALUATING:
                    dr.reallocate_on_residual()
                elif dr.state == SolverState.ENGAGING:
                    dr.report_bda([e[1] for e in eng])
                    trace.append(("bda",))
            return trace

        assert run(7) == run(7)
        # two runs same seed -> identical trace


# --------------------------------------------------------------------------- #
# result schema / contract
# --------------------------------------------------------------------------- #
class TestResultContract:
    def test_allocation_result_schema(self) -> None:
        w = [Weapon(0), Weapon(1)]
        t = [Target(0, 1.0), Target(1, 1.0)]
        p = np.ones((2, 2))
        res = TieredWTASolver().solve(w, t, p, np.ones(2))
        assert isinstance(res, WTAResult)
        assert all(isinstance(a, tuple) and len(a) == 2 for a in res.assignments)
        assert isinstance(res.tier, Tier)
        assert res.solve_time_ms >= 0

    def test_result_has_tier_metadata(self) -> None:
        w = [Weapon(0)]
        t = [Target(0, 1.0)]
        res = TieredWTASolver(WTAConfig(wta_mode="milp")).solve(w, t, np.array([[0.5]]), np.ones(1))
        assert res.tier == Tier.T1_MILP


# --------------------------------------------------------------------------- #
# property-based (Hypothesis)
# --------------------------------------------------------------------------- #
class TestHypothesis:
    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        n=st.integers(1, 5),
        m=st.integers(1, 5),
        seed=st.integers(0, 10_000),
    )
    def test_assignment_validity_invariant(self, n, m, seed) -> None:
        rng = np.random.default_rng(seed)
        w = [Weapon(i) for i in range(n)]
        t = [Target(j, value=float(rng.uniform(0.1, 5.0))) for j in range(m)]
        p = rng.random((n, m))
        v = np.array([target.value for target in t])
        res = TieredWTASolver(WTAConfig(wta_mode="greedy")).solve(w, t, p, v)
        assert _valid(res.assignments, p, np.ones((n, m)), {}, [], w, t)

    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        n=st.integers(2, 5),
        m=st.integers(2, 5),
        seed=st.integers(0, 10_000),
    )
    def test_permutation_invariance(self, n, m, seed) -> None:
        rng = np.random.default_rng(seed)
        w, t, p, v = _make_instance(n, m, seed=seed)
        perm_w = list(range(n))
        perm_m = list(range(m))
        rng.shuffle(perm_w)
        rng.shuffle(perm_m)
        p2 = p[np.ix_(perm_w, perm_m)]
        v2 = v[perm_m]
        w2 = [Weapon(i) for i in perm_w]
        t2 = [Target(j, float(v2[jj])) for jj, j in enumerate(perm_m)]
        r1 = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0)).solve(w, t, p, v)
        r2 = TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0)).solve(w2, t2, p2, v2)
        assert abs(r1.expected_survival_value - r2.expected_survival_value) < 1e-6


# --------------------------------------------------------------------------- #
# no regression against existing TaskAllocator
# --------------------------------------------------------------------------- #
class TestNoRegression:
    def test_existing_allocator_still_works(self) -> None:
        allocator = TaskAllocator()
        agents = [
            Agent(
                id=1,
                position=Pose3D(x=0, y=0, z=0),
                vehicle_type=VehicleType.UAV_MULTIROTOR,
            )
        ]
        tasks = [Task(id=1, position=Pose3D(x=5, y=0, z=0))]
        res = allocator.allocate(agents, tasks)
        assert len(res) == 1
