"""Tests for the combat reallocator (simulation/combat_reallocator.py).

Covers:
- SLS / SSL mode switching (engagements per cycle)
- residual WTA re-solve after BDA shows a target alive
- state-machine transitions (IDLE -> ALLOCATING -> ENGAGING -> LOOKING
  -> {TERMINAL | RE_EVALUATING})
- interference constraints respected in allocations
- kill-probability and time-window-feasibility accessors

RED -> GREEN -> REFACTOR applied.
"""

from __future__ import annotations

import numpy as np
import pytest

from apex_autopilot_optimization.simulation.combat_reallocator import (
    CombatReallocator,
)
from apex_autopilot_optimization.swarm.wta_solver import (
    AllocationMode,
    SolverState,
    Target,
    TieredWTASolver,
    Weapon,
    WTAConfig,
)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _solver() -> TieredWTASolver:
    return TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0))


def _instance():
    """2 weapons x 2 targets, diagonal dominance (weapon i suits target i).

    Target 0 is high value so weapon 0->target 0 is the unique best pair.
    """
    weapons = [Weapon(0), Weapon(1)]
    targets = [Target(0, value=10.0), Target(1, value=1.0)]
    p = np.array([[0.9, 0.1], [0.1, 0.9]])
    values = np.array([10.0, 1.0])
    return weapons, targets, p, values


# --------------------------------------------------------------------------- #
# SLS / SSL switching
# --------------------------------------------------------------------------- #
class TestModeSwitching:
    def test_sls_single_engagement_per_cycle(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v, mode=AllocationMode.SLS)
        assert cr.state == SolverState.IDLE

        eng = cr.request_allocation()  # IDLE->ALLOCATING->ENGAGING
        assert cr.state == SolverState.ENGAGING
        assert len(eng) == 1  # SLS: exactly one engagement
        assert eng[0] in ((0, 0), (1, 1))
        # bda_received is legal from ENGAGING (the look phase).
        assert cr.can_transition("bda_received")

        st = cr.report_bda([])  # ENGAGING->LOOKING->RE_EVALUATING (live targets+weapons)
        assert st == SolverState.RE_EVALUATING

    def test_ssl_salvo_per_cycle(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v, mode=AllocationMode.SSL)
        eng = cr.request_allocation()
        assert cr.state == SolverState.ENGAGING
        # SSL: the whole salvo is returned (both weapons assigned).
        assert len(eng) == 2
        assert set(eng) == {(0, 0), (1, 1)}

    def test_ssl_string_mode_accepted(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v, mode="ssl")
        assert cr.mode == AllocationMode.SSL
        eng = cr.request_allocation()
        assert len(eng) == 2


# --------------------------------------------------------------------------- #
# residual re-solve (BDA shows target alive)
# --------------------------------------------------------------------------- #
class TestResidualReSolve:
    def test_sls_residual_re_solve_when_target_stays_alive(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v, mode=AllocationMode.SLS)

        # Cycle 1: weapon 0 engages target 0.
        eng1 = cr.request_allocation()
        assert len(eng1) == 1
        assert eng1[0] == (0, 0)
        assert cr.state == SolverState.ENGAGING

        # BDA: target 1 neutralised, target 0 still alive.
        st = cr.report_bda([1])
        assert st == SolverState.RE_EVALUATING  # live target + live weapon

        # Re-solve the residual: weapon 1 + target 0 -> weapon 1 engages target 0.
        cr.reallocate_on_residual()  # RE_EVALUATING -> ALLOCATING
        assert cr.state == SolverState.ALLOCATING
        eng2 = cr.request_allocation()
        assert len(eng2) == 1
        assert eng2[0] == (1, 0)

        # BDA neutralises target 0; no targets left -> TERMINAL.
        st = cr.report_bda([0])
        assert st == SolverState.TERMINAL

    def test_ssl_residual_re_solve(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v, mode=AllocationMode.SSL)

        eng = cr.request_allocation()
        assert len(eng) == 2
        # BDA: nothing killed -> both targets alive, but weapons expended.
        st = cr.report_bda([])
        assert st == SolverState.TERMINAL  # weapons exhausted

    def test_all_neutralized_terminal(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v, mode=AllocationMode.SLS)
        cr.request_allocation()  # weapon 0 -> target 0
        st = cr.report_bda([0])  # target 0 killed; target 1 alive, weapon 1 alive
        assert st == SolverState.RE_EVALUATING
        cr.reallocate_on_residual()
        eng = cr.request_allocation()  # weapon 1 -> target 1
        assert eng[0] == (1, 1)
        st = cr.report_bda([1])  # all neutralized
        assert st == SolverState.TERMINAL


# --------------------------------------------------------------------------- #
# state transitions
# --------------------------------------------------------------------------- #
class TestStateTransitions:
    def test_idle_to_allocating_to_engaging(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v)
        assert cr.state == SolverState.IDLE
        assert cr.can_transition("allocate_request")
        cr.request_allocation()
        assert cr.state == SolverState.ENGAGING

    def test_report_bda_from_idle_raises(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v)
        with pytest.raises(ValueError):
            cr.report_bda([])

    def test_request_allocation_twice_without_bda_raises(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v)
        cr.request_allocation()  # -> ENGAGING
        with pytest.raises(ValueError):
            cr.request_allocation()  # not ALLOCATING

    def test_reset_returns_to_idle_from_any_state(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v)
        cr.request_allocation()
        cr.report_bda([])  # -> LOOKING / RE_EVALUATING
        cr.reset()
        assert cr.state == SolverState.IDLE

    def test_invalid_event_raises(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v)
        # IDLE does not accept "bda_received".
        with pytest.raises(ValueError):
            cr._transition("bda_received")


# --------------------------------------------------------------------------- #
# interference constraints
# --------------------------------------------------------------------------- #
class TestInterferenceConstraints:
    def test_clique_at_most_one_pair_assigned(self) -> None:
        weapons = [Weapon(0), Weapon(1)]
        targets = [Target(0, value=10.0)]
        p = np.array([[0.9], [0.9]])
        v = np.array([10.0])
        # Both weapons on the same seeker band -> at most one may engage target 0.
        cliques = [[(0, 0), (1, 0)]]
        cr = CombatReallocator(
            _solver(),
            weapons,
            targets,
            p,
            v,
            interference_cliques=cliques,
            mode=AllocationMode.SSL,
        )
        eng = cr.request_allocation()
        assert len(eng) == 1  # clique forces a single engagement
        assert eng[0] in ((0, 0), (1, 0))

    def test_interference_accessor(self) -> None:
        w, t, p, v = _instance()
        cliques = [[(0, 0), (1, 1)]]
        cr = CombatReallocator(_solver(), w, t, p, v, interference_cliques=cliques)
        assert cr.interference_cliques_for() == cliques


# --------------------------------------------------------------------------- #
# kill probability / time-window feasibility
# --------------------------------------------------------------------------- #
class TestKillProbabilityAndFeasibility:
    def test_kill_probability_per_pair(self) -> None:
        w, t, p, v = _instance()
        cr = CombatReallocator(_solver(), w, t, p, v)
        assert cr.kill_probability(0, 0) == 0.9
        assert cr.kill_probability(0, 1) == 0.1
        assert cr.kill_probability(1, 1) == 0.9
        with pytest.raises(KeyError):
            cr.kill_probability(99, 0)

    def test_time_window_feasibility_mask(self) -> None:
        w, t, p, v = _instance()
        tf = np.array([[False, True], [True, True]])  # (0,0) infeasible
        cr = CombatReallocator(_solver(), w, t, p, v, time_feasible=tf)
        assert cr.is_feasible(0, 0) is False
        assert cr.is_feasible(0, 1) is True
        assert cr.is_feasible(1, 0) is True

    def test_infeasible_pair_never_assigned(self) -> None:
        w, t, p, v = _instance()
        tf = np.array([[False, True], [True, True]])
        cr = CombatReallocator(_solver(), w, t, p, v, time_feasible=tf, mode=AllocationMode.SSL)
        eng = cr.request_allocation()
        assert not any(e == (0, 0) for e in eng)
