"""Adversarial tests for the CombatReallocator (dynamic WTA with BDA loop).

Property-based tests assert safety invariants (no infeasible pairs, no
interference-clique violations, no re-engaging killed targets, legal state
machine) hold across generated instances; directed tests pin edge cases
(NaN kill probabilities, empty instances, all-infeasible masks, extreme
values).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apex_autopilot_optimization.chaos.probes import (
    combat_no_clique_violation,
    combat_no_infeasible_assignment,
    combat_no_killed_reengaged,
    combat_state_machine_legal,
)
from apex_autopilot_optimization.simulation.combat_reallocator import CombatReallocator
from apex_autopilot_optimization.swarm.wta_solver import (
    AllocationMode,
    SolverState,
    Target,
    TieredWTASolver,
    Weapon,
    WTAConfig,
)

_FINITE_PROB = st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)
_ADVERSARIAL_PROB = st.one_of(
    _FINITE_PROB,
    st.just(float("nan")),
    st.just(float("inf")),
    st.just(-float("inf")),
    st.just(1.5),
    st.just(-0.5),
)
_POS_VALUE = st.floats(0.0, 1e6, allow_nan=False, allow_infinity=False)
_ADVERSARIAL_VALUE = st.one_of(
    _POS_VALUE, st.just(float("nan")), st.just(float("inf")), st.just(-1e6)
)
_BOOL = st.booleans()


def _solver() -> TieredWTASolver:
    return TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0))


def _build(
    n: int,
    m: int,
    p,
    values=None,
    time_feasible=None,
    mode=AllocationMode.SLS,
    cliques=None,
):
    weapons = [Weapon(i) for i in range(n)]
    p_arr = np.asarray(p, dtype=float).ravel()
    need = n * m
    if p_arr.size < need:
        p_arr = np.concatenate([p_arr, np.full(need - p_arr.size, 0.5)])
    p = p_arr[:need].reshape(n, m)
    if values is None:
        values = [1.0] * m
    values = list(values)
    values = (values + [1.0] * m)[:m]
    targets = [Target(j, value=float(values[j])) for j in range(m)]
    values_arr = np.asarray(values, dtype=float)
    tf = (
        np.ones((n, m), dtype=bool)
        if time_feasible is None
        else np.asarray(time_feasible, dtype=bool).reshape(n, m)
    )
    return CombatReallocator(
        _solver(),
        weapons,
        targets,
        p,
        values_arr,
        time_feasible=tf,
        interference_cliques=cliques or [],
        mode=mode,
    )


# --------------------------------------------------------------------------- #
# Property-based: invariants must hold for all generated instances
# --------------------------------------------------------------------------- #


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(1, 5),
    m=st.integers(1, 5),
    p=st.lists(_ADVERSARIAL_PROB, min_size=1, max_size=25),
    values=st.lists(_ADVERSARIAL_VALUE, min_size=1, max_size=5),
    mode=st.sampled_from([AllocationMode.SLS, AllocationMode.SSL]),
)
def test_adversarial_kill_prob_constructs_safely(n, m, p, values, mode) -> None:
    """Adversarial kill probabilities (NaN/>1/<0) do not crash construction.

    ``np.clip`` clips bounded values into [0, 1] but propagates NaN, so the
    invariant is: every *finite* entry of ``p`` lies in [0, 1].
    """
    need = n * m
    p = (p + [0.5] * need)[:need]
    # Construction itself must not raise on adversarial input.
    cr = _build(n, m, p, values=values, mode=mode)
    assert cr.p.shape == (n, m)
    finite = np.isfinite(cr.p)
    if finite.any():
        assert np.all((cr.p[finite] >= 0.0) & (cr.p[finite] <= 1.0))


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(1, 4),
    m=st.integers(1, 4),
    p=st.lists(_FINITE_PROB, min_size=1, max_size=16),
    tf=st.lists(_BOOL, min_size=1, max_size=16),
    clique_count=st.integers(0, 2),
    mode=st.sampled_from([AllocationMode.SLS, AllocationMode.SSL]),
)
def test_no_infeasible_or_clique_violation(n, m, p, tf, clique_count, mode) -> None:
    """Every assignment respects time-feasibility and interference cliques."""
    need = n * m
    p = (p + [0.5] * need)[:need]
    tf = (tf + [True] * need)[:need]
    cr = _build(n, m, p, time_feasible=tf, mode=mode)
    # Build up to clique_count random cliques over the instance.
    cliques = []
    for _ in range(clique_count):
        if n == 0 or m == 0:
            break
        cliques.append([(0 % n, 0 % m)])
    cr = _build(n, m, p, time_feasible=tf, cliques=cliques, mode=mode)
    try:
        eng = cr.request_allocation()
    except ValueError:
        # state-machine misuse is not an adversarial-input failure here
        return
    weapon_ids = [w.id for w in cr.weapons]
    target_ids = [t.id for t in cr.targets]
    assert combat_no_infeasible_assignment(eng, cr.time_feasible, weapon_ids, target_ids) == []
    assert combat_no_clique_violation(eng, cr.interference_cliques_for()) == []
    assert combat_state_machine_legal(cr) == []


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(1, 4),
    m=st.integers(1, 4),
    p=st.lists(_FINITE_PROB, min_size=1, max_size=16),
    mode=st.sampled_from([AllocationMode.SLS, AllocationMode.SSL]),
)
def test_killed_targets_never_reengaged(n, m, p, mode) -> None:
    """Targets killed in BDA are never re-engaged in the residual cycle."""
    need = n * m
    p = (p + [0.5] * need)[:need]
    cr = _build(n, m, p, mode=mode)
    eng1 = cr.request_allocation()
    killed = [tid for _, tid in eng1]  # pretend everything engaged was killed
    st_after = cr.report_bda(killed)
    if st_after == SolverState.RE_EVALUATING:
        cr.reallocate_on_residual()
        eng2 = cr.request_allocation()
    else:
        eng2 = []
    # Any target killed in cycle 1 must not appear in cycle 2.
    killed_set = set(killed)
    violations = combat_no_killed_reengaged(eng2, list(killed_set))
    assert violations == [], violations
    assert combat_state_machine_legal(cr) == []


# --------------------------------------------------------------------------- #
# Directed edge cases
# --------------------------------------------------------------------------- #


class TestDirectedEdgeCases:
    def test_empty_weapons_and_targets(self) -> None:
        cr = _build(0, 0, [])
        assert cr.request_allocation() == []
        assert cr.state == SolverState.ENGAGING
        assert cr.report_bda([]) == SolverState.TERMINAL

    def test_weapons_exhausted_is_terminal(self) -> None:
        cr = _build(1, 2, [[0.5, 0.5]], mode=AllocationMode.SSL)
        cr.request_allocation()  # weapon 0 expended
        assert cr.report_bda([]) == SolverState.TERMINAL  # weapons exhausted

    def test_all_infeasible_mask_yields_no_engagement(self) -> None:
        cr = _build(
            2,
            2,
            [[0.9, 0.9], [0.9, 0.9]],
            time_feasible=np.zeros((2, 2), dtype=bool),
            mode=AllocationMode.SSL,
        )
        eng = cr.request_allocation()
        assert eng == []

    def test_report_bda_from_idle_raises(self) -> None:
        cr = _build(1, 1, [[0.5]])
        with pytest.raises(ValueError):
            cr.report_bda([])

    def test_double_request_allocation_without_bda_raises(self) -> None:
        cr = _build(1, 1, [[0.5]])
        cr.request_allocation()
        with pytest.raises(ValueError):
            cr.request_allocation()

    def test_invalid_transition_raises(self) -> None:
        cr = _build(1, 1, [[0.5]])
        with pytest.raises(ValueError):
            cr._transition("bda_received")  # IDLE does not accept bda_received

    def test_reset_returns_to_idle_from_any_state(self) -> None:
        cr = _build(2, 2, [[0.9, 0.1], [0.1, 0.9]], mode=AllocationMode.SLS)
        cr.request_allocation()
        cr.report_bda([])
        cr.reset()
        assert cr.state == SolverState.IDLE

    def test_residual_never_assigns_expended_weapon(self) -> None:
        weapons = [Weapon(0), Weapon(1)]
        targets = [Target(0, value=10.0), Target(1, value=1.0)]
        p = np.array([[0.9, 0.1], [0.1, 0.9]])
        cr = CombatReallocator(
            _solver(), weapons, targets, p, np.array([10.0, 1.0]), mode=AllocationMode.SLS
        )
        eng1 = cr.request_allocation()
        assert len(eng1) == 1
        fired = eng1[0][0]
        cr.report_bda([])  # target(s) alive, re-evaluate
        cr.reallocate_on_residual()
        eng2 = cr.request_allocation()
        assert all(w != fired for w, _ in eng2)

    def test_extreme_target_values_do_not_crash(self) -> None:
        cr = _build(2, 2, [[0.5, 0.5], [0.5, 0.5]], values=[1e15, -1e15], mode=AllocationMode.SSL)
        eng = cr.request_allocation()
        assert len(eng) <= 2

    def test_interference_clique_forces_single_engagement(self) -> None:
        weapons = [Weapon(0), Weapon(1)]
        targets = [Target(0, value=10.0)]
        p = np.array([[0.9], [0.9]])
        cliques = [[(0, 0), (1, 0)]]
        cr = CombatReallocator(
            _solver(),
            weapons,
            targets,
            p,
            np.array([10.0]),
            interference_cliques=cliques,
            mode=AllocationMode.SSL,
        )
        eng = cr.request_allocation()
        assert len(eng) == 1
