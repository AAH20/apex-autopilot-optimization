"""Combat reallocator: shoot-look-shoot / shoot-shoot-look dynamic WTA.

Wraps :class:`TieredWTASolver` (``swarm/wta_solver.py``) and drives a
battle-damage-assessment (BDA) loop::

    IDLE -> ALLOCATING -> ENGAGING -> LOOKING -> {TERMINAL | RE-EVALUATING}
                                              |______________________|
                                                             (back to ALLOCATING)

Modes
-----
SLS (shoot-look-shoot): one engagement per cycle.  Allocate -> engage the
    single top pair -> look (BDA) -> if a target is still alive, build the
    residual instance (remaining weapons + live targets), re-solve and
    re-allocate.
SSL (shoot-shoot-look): a salvo per cycle.  Allocate -> engage the whole
    salvo -> look (BDA) -> residual re-solve / re-allocate as above.

The allocator tracks:
* kill probability per weapon-target pair (``kill_prob`` matrix),
* time-window feasibility (``time_feasible`` mask),
* interference constraints (``interference_cliques``).

On a BDA report, killed targets are dropped from the residual.  When live
targets remain (and weapons remain) the machine enters RE_EVALUATING; the
next :meth:`request_allocation` re-solves the residual instance and re-assigns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from apex_autopilot_optimization.swarm.wta_solver import (
    AllocationCycle,
    AllocationMode,
    BDAEvent,
    SolverState,
    Target,
    TieredWTASolver,
    Weapon,
    WTAResult,
)


@dataclass(slots=True)
class CombatReallocator:
    """Dynamic WTA reallocator wrapping :class:`TieredWTASolver`.

    Parameters
    ----------
    solver:
        Tiered WTA solver used to solve each (residual) instance.
    weapons, targets:
        Ordered sequences; ``kill_prob`` is indexed by their positions.
    kill_prob:
        (n, m) array with p_ij in [0, 1] -- kill probability per pair.
    values:
        (m,) target values; defaults to all ones.
    time_feasible:
        (n, m) bool mask; False => pair cannot be assigned (time window).
    salvo_caps:
        target_id -> max weapons on that target.
    interference_cliques:
        list of cliques, each a list of (weapon_index, target_index) pairs of
        which at most one may be assigned.
    mode:
        ``AllocationMode.SLS`` (one engagement per cycle) or
        ``AllocationMode.SSL`` (whole salvo per cycle).
    """

    solver: TieredWTASolver
    weapons: list[Weapon]
    targets: list[Target]
    kill_prob: np.ndarray
    values: np.ndarray | None = None
    time_feasible: np.ndarray | None = None
    salvo_caps: dict[int, int] | None = None
    interference_cliques: list[list[tuple[int, int]]] | None = None
    mode: AllocationMode | str = AllocationMode.SLS

    # Derived / runtime state (must be declared for slots=True) -----------
    p: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    cycle: int = 0
    state: SolverState = SolverState.IDLE
    event_log: list[str] = field(default_factory=list)
    cycles: list[AllocationCycle] = field(default_factory=list)
    current_assignments: list[tuple[int, int]] = field(default_factory=list)
    remaining_weapon_ids: list[int] = field(default_factory=list)
    remaining_target_ids: list[int] = field(default_factory=list)
    _last_result: WTAResult | None = field(default=None, repr=False)

    # ------------------------------------------------------------------ init
    def __post_init__(self) -> None:
        self.weapons = list(self.weapons)
        self.targets = list(self.targets)
        self.p = np.clip(np.asarray(self.kill_prob, dtype=float), 0.0, 1.0)
        n, m = self.p.shape
        self.values = (
            np.ones(m, dtype=float) if self.values is None else np.asarray(self.values, dtype=float)
        )
        self.time_feasible = (
            np.ones((n, m), dtype=bool)
            if self.time_feasible is None
            else np.asarray(self.time_feasible, dtype=bool)
        )
        self.salvo_caps = dict(self.salvo_caps or {})
        self.interference_cliques = self.interference_cliques or []
        self.mode = AllocationMode(self.mode) if isinstance(self.mode, str) else self.mode

        self.remaining_weapon_ids = [w.id for w in self.weapons]
        self.remaining_target_ids = [t.id for t in self.targets]

    # --------------------------------------------------------------- events
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

    # kill-probability / feasibility / interference accessors --------------
    def kill_probability(self, weapon_id: int, target_id: int) -> float:
        """Kill probability for a weapon-target pair."""
        wid_to_i = {w.id: i for i, w in enumerate(self.weapons)}
        tid_to_j = {t.id: j for j, t in enumerate(self.targets)}
        if weapon_id not in wid_to_i or target_id not in tid_to_j:
            raise KeyError(f"unknown weapon {weapon_id} or target {target_id}")
        return float(self.p[wid_to_i[weapon_id], tid_to_j[target_id]])

    def is_feasible(self, weapon_id: int, target_id: int) -> bool:
        """Time-window feasibility for a weapon-target pair."""
        wid_to_i = {w.id: i for i, w in enumerate(self.weapons)}
        tid_to_j = {t.id: j for j, t in enumerate(self.targets)}
        if weapon_id not in wid_to_i or target_id not in tid_to_j:
            raise KeyError(f"unknown weapon {weapon_id} or target {target_id}")
        return bool(self.time_feasible[wid_to_i[weapon_id], tid_to_j[target_id]])  # type: ignore[index]

    def interference_cliques_for(self) -> list[list[tuple[int, int]]]:
        """Return the configured interference cliques."""
        return list(self.interference_cliques or [])

    # -------------------------------------------------------------- public API
    def request_allocation(self) -> list[tuple[int, int]]:
        """Solve the residual instance and issue engagements.

        IDLE -> ALLOCATING -> ENGAGING.  Returns the engagements to fire this
        cycle (one pair for SLS; the full salvo for SSL).  Fired weapons are
        expended and removed from the residual instance.
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
        # Expend fired weapons: they are committed to this engagement round.
        fired = {wid for wid, _ in engagements}
        self.remaining_weapon_ids = [wid for wid in self.remaining_weapon_ids if wid not in fired]

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
        state.  Killed targets are removed from the residual; when live
        targets remain the machine enters RE_EVALUATING ready for a residual
        re-solve.
        """
        self._transition("bda_received")  # ENGAGING -> LOOKING

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
                    self.values[j] = float(updates["value"])  # type: ignore[index]

        # Decide terminal vs re-evaluating.
        if not self.remaining_target_ids:
            event = "all_neutralized"
        elif not self.remaining_weapon_ids:
            event = "weapons_exhausted"
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

    def can_transition(self, event: str) -> bool:
        """Whether ``event`` is a legal transition from the current state."""
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
            SolverState.RE_EVALUATING: {
                "residual_instance_ready",
                "reset",
                "abort",
            },
            SolverState.TERMINAL: {"reset", "abort"},
        }
        return event in transitions.get(self.state, set())

    # ------------------------------------------------------------ internals
    def _current_weapons(self) -> list[Weapon]:
        id_set = set(self.remaining_weapon_ids)
        return [w for w in self.weapons if w.id in id_set]

    def _current_targets(self) -> list[Target]:
        id_set = set(self.remaining_target_ids)
        return [t for t in self.targets if t.id in id_set]

    def _weapon_rows(self) -> list[int]:
        wid_to_i = {w.id: i for i, w in enumerate(self.weapons)}
        return [wid_to_i[wid] for wid in self.remaining_weapon_ids]

    def _target_cols(self) -> list[int]:
        tid_to_j = {t.id: j for j, t in enumerate(self.targets)}
        return [tid_to_j[t] for t in self.remaining_target_ids]

    def _current_p(self) -> np.ndarray:
        rows = self._weapon_rows()
        cols = self._target_cols()
        return self.p[np.ix_(rows, cols)] if rows and cols else self.p[:0, :0]

    def _current_values(self) -> np.ndarray:
        cols = self._target_cols()
        return self.values[cols] if cols else self.values[:0]  # type: ignore[index]

    def _current_time_feasible(self) -> np.ndarray:
        rows = self._weapon_rows()
        cols = self._target_cols()
        if rows and cols:
            return self.time_feasible[np.ix_(rows, cols)]  # type: ignore[index]
        return self.time_feasible[:0, :0]  # type: ignore[index]

    def _select_engagements(self, assignments: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if self.mode == AllocationMode.SLS:
            return assignments[:1]
        return list(assignments)  # SSL: the whole salvo
