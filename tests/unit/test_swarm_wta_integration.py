"""TDD suite: TieredWTASolver wired into SwarmRunner batch mission loop.

Covers: per-vehicle WTA solve, assignments applied as formation setpoints,
BDA-driven reallocation, <100 ms cycle budget, partial-failure isolation.
All backends are mocked; no Gazebo/PX4 is required.

RED -> GREEN -> REFACTOR.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from apex_autopilot_optimization.core.types import Pose3D, StateVector, Velocity3D
from apex_autopilot_optimization.simulation.config import SimulationConfig
from apex_autopilot_optimization.simulation.swarm_runner import (
    SwarmRunner,
    WTAMissionProblem,
)
from apex_autopilot_optimization.swarm.wta_solver import (
    BDAEvent,
    DynamicReallocator,
    SolverState,
    Target,
    Tier,
    TieredWTASolver,
    Weapon,
    WTAResult,
)

# Shared mocked MAVLinkBridge + SimulationInterface backend (see test_swarm_runner.py).
from tests.unit.test_swarm_runner import _mocked_backends  # noqa: E402

_WTA_OK = WTAResult(
    assignments=[(0, 0)],
    tier=Tier.T2_GREEDY,
    expected_survival_value=10.0,
    expected_damage=90.0,
    total_target_value=100.0,
    solve_time_ms=5.0,
)


def _make_config() -> SimulationConfig:
    return SimulationConfig(
        backend="mock",
        connection_string="mock://test",
        lockstep=False,
        time_scale=1.0,
        vehicle_type="multirotor",
        model="test_model",
    )


def _make_problem(vehicle_id: int) -> WTAMissionProblem:
    weapons = [Weapon(id=0), Weapon(id=1)]
    targets = [Target(id=0, value=100.0), Target(id=1, value=50.0)]
    kill_prob = np.array([[0.9, 0.6], [0.8, 0.7]])
    target_poses = {t.id: Pose3D(x=10.0 + float(t.id) * 5.0, y=0.0, z=5.0) for t in targets}
    return WTAMissionProblem(
        vehicle_id=vehicle_id,
        weapons=weapons,
        targets=targets,
        kill_prob=kill_prob,
        target_poses=target_poses,
    )


def _solve_ok(*args: object, **kwargs: object) -> WTAResult:
    return _WTA_OK


@contextmanager
def _wta_mocked(
    n: int,
    solver_side_effect=None,
    with_reallocator: bool = False,
    bda_events: dict[int, list[BDAEvent]] | None = None,
    step_ok: bool = True,
):
    """Mocked swarm backends + optional TieredWTASolver/DynamicReallocator mocks."""
    with _mocked_backends(n, step_ok=step_ok) as (runner, bridges, sims):
        solver_inst = MagicMock(spec=TieredWTASolver)
        solver_inst.solve.side_effect = solver_side_effect or _solve_ok
        with patch(
            "apex_autopilot_optimization.simulation.swarm_runner.TieredWTASolver",
            return_value=solver_inst,
        ):
            realloc_inst: MagicMock | None = None
            if with_reallocator:
                realloc_inst = MagicMock(spec=DynamicReallocator)
                realloc_inst.request_allocation.return_value = [(0, 0)]
                realloc_inst.report_bda.return_value = SolverState.RE_EVALUATING
                realloc_inst.current_assignments = [(0, 0)]
                realloc_inst.state = SolverState.IDLE
                with patch(
                    "apex_autopilot_optimization.simulation.swarm_runner.DynamicReallocator",
                    return_value=realloc_inst,
                ):
                    yield runner, bridges, sims, solver_inst, realloc_inst, bda_events
            else:
                yield runner, bridges, sims, solver_inst, None, bda_events


def _space_out(bridges: dict[int, MagicMock]) -> None:
    """Put vehicles far apart so the safety filter does not hold them all."""
    for i, b in bridges.items():
        b.get_state.return_value = StateVector(
            pose=Pose3D(float(i) * 50.0, 0.0, 0.0),
            velocity=Velocity3D(0, 0, 0),
            timestamp=time.time(),
        )


class TestSwarmRunnerWTAIntegration:
    """Integration of TieredWTASolver into the SwarmRunner batch mission loop."""

    def test_wta_assignments_applied_as_formation_setpoints(self) -> None:
        """Solver weapon->target assignments drive controls toward target poses."""
        with _wta_mocked(2) as (runner, bridges, sims, solver, _, bda_events):
            _space_out(bridges)
            problems = {i: _make_problem(i) for i in range(2)}
            result = runner.run_wta_batch_mission(
                problems=problems, config=_make_config(), max_steps=2
            )

        assert result.success is True
        assert set(result.per_vehicle) == {0, 1}
        assert all(r.success for r in result.per_vehicle.values())

        # Setpoint = target 0 pose (10, 0, 5); vehicles far away -> full throttle.
        for b in bridges.values():
            ctrl = b.send_control.call_args.args[0]
            assert ctrl.throttle == pytest.approx(1.0)

        # Solver ran per vehicle, every cycle, time-boxed under the budget.
        assert solver.solve.call_count == 4  # 2 vehicles x 2 cycles
        for call in solver.solve.call_args_list:
            assert call.kwargs["time_limit_ms"] <= 70.0

        # Reports + swarm rollup.
        assert set(runner.wta_cycle_reports) == {0, 1}
        assert all(len(reports) == 2 for reports in runner.wta_cycle_reports.values())
        assert runner.wta_cycle_reports[0][0]["assignments"] == [(0, 0)]
        assert result.swarm["wta_latency_over_budget"] == 0
        assert result.swarm["wta_cycle_budget_ms"] == 100.0
        for b in bridges.values():
            b.disconnect.assert_called_once()
        for s in sims.values():
            s.disconnect.assert_called_once()

    def test_wta_solver_failure_isolated_to_one_vehicle(self) -> None:
        """Solver exception on one vehicle holds it; the other completes the mission."""
        calls = {"n": 0}

        def flaky(*args: object, **kwargs: object) -> WTAResult:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("solver down")
            return _WTA_OK

        with _wta_mocked(2, solver_side_effect=flaky) as (
            runner,
            bridges,
            sims,
            solver,
            _,
            _bda_events,
        ):
            _space_out(bridges)
            problems = {i: _make_problem(i) for i in range(2)}
            result = runner.run_wta_batch_mission(
                problems=problems, config=_make_config(), max_steps=1
            )

        assert solver.solve.call_count == 2
        # Slot 0: solver failed -> hold control (throttle 0). Slot 1: solved -> full throttle.
        assert bridges[0].send_control.call_args.args[0].throttle == 0.0
        assert bridges[1].send_control.call_args.args[0].throttle == pytest.approx(1.0)
        # Partial failure did not abort the swarm.
        assert result.per_vehicle[0].success is True
        assert result.per_vehicle[1].success is True

    def test_wta_bda_reports_and_triggers_reallocation(self) -> None:
        """BDA event is reported; residual re-evaluation triggers re-solve."""
        bda = BDAEvent(cycle=1, killed_target_ids=[0], damage_updates={})
        bda_events_param: dict[int, list[BDAEvent | None]] = {0: [None, bda]}
        with _wta_mocked(1, with_reallocator=True, bda_events=bda_events_param) as (
            runner,
            bridges,
            sims,
            solver,
            realloc,
            _bda_events,
        ):
            _space_out(bridges)
            problems = {0: _make_problem(0)}
            result = runner.run_wta_batch_mission(
                problems=problems,
                config=_make_config(),
                max_steps=2,
                bda_events=bda_events_param,
            )

        assert realloc is not None
        realloc.report_bda.assert_called_once_with([0], {})
        realloc.reallocate_on_residual.assert_called_once()
        assert realloc.request_allocation.call_count >= 1
        assert result.per_vehicle[0].success is True
        assert runner.wta_cycle_reports[0][1]["killed_targets"] == [0]
        assert runner.wta_cycle_reports[0][1]["reallocated"] is True

    def test_wta_cycle_respects_100ms_budget(self) -> None:
        """Every cycle stays under the 100 ms budget; solver is time-boxed."""
        with _wta_mocked(3) as (runner, bridges, sims, solver, _, _bda_events):
            _space_out(bridges)
            problems = {i: _make_problem(i) for i in range(3)}
            result = runner.run_wta_batch_mission(
                problems=problems,
                config=_make_config(),
                max_steps=5,
                cycle_budget_ms=100.0,
            )

        assert result.swarm["wta_latency_over_budget"] == 0
        for slot in range(3):
            for report in runner.wta_cycle_reports[slot]:
                assert report["cycle_lat_ms"] < 100.0
        for call in solver.solve.call_args_list:
            assert call.kwargs["time_limit_ms"] == pytest.approx(70.0)

    def test_wta_zero_vehicles_returns_failure(self) -> None:
        runner = SwarmRunner()
        result = runner.run_wta_batch_mission(problems={}, config=_make_config())
        assert result.success is False
        assert result.per_vehicle == {}
        assert result.message == "No vehicles in WTA swarm mission"

    def test_wta_vehicle_step_failure_others_continue(self) -> None:
        """One sim step failure marks that vehicle failed; the rest complete."""
        with _mocked_backends(3, step_ok=True) as (runner, bridges, sims):
            _space_out(bridges)
            sims[1].step.return_value = False  # slot 1 dies on first step
            solver_inst = MagicMock(spec=TieredWTASolver)
            solver_inst.solve.return_value = _WTA_OK
            with patch(
                "apex_autopilot_optimization.simulation.swarm_runner.TieredWTASolver",
                return_value=solver_inst,
            ):
                problems = {i: _make_problem(i) for i in range(3)}
                result = runner.run_wta_batch_mission(
                    problems=problems, config=_make_config(), max_steps=3
                )

        assert result.per_vehicle[0].success is True
        assert result.per_vehicle[1].success is False
        assert result.per_vehicle[2].success is True
        for b in bridges.values():
            b.disconnect.assert_called_once()

    def test_wta_abort_on_any_failure_stops_swarm(self) -> None:
        with _mocked_backends(3, step_ok=True) as (runner, bridges, sims):
            _space_out(bridges)
            sims[1].step.return_value = False
            solver_inst = MagicMock(spec=TieredWTASolver)
            solver_inst.solve.return_value = _WTA_OK
            with patch(
                "apex_autopilot_optimization.simulation.swarm_runner.TieredWTASolver",
                return_value=solver_inst,
            ):
                problems = {i: _make_problem(i) for i in range(3)}
                result = runner.run_wta_batch_mission(
                    problems=problems,
                    config=_make_config(),
                    max_steps=3,
                    abort_on_any_failure=True,
                )

        assert result.per_vehicle[1].success is False
        for b in bridges.values():
            b.disconnect.assert_called_once()
