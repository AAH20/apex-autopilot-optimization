"""100-vehicle swarm scalability test suite.

All tests run with mocked ``MAVLinkBridge`` + ``SimulationInterface`` backends
(the spec's no-op fallback path, §3), so no Gazebo/PX4 is required. Gazebo SITL
is practically limited to under 10 vehicles (~4 GB RAM per instance, spec §14),
so the 100-vehicle scale point is validated here with simulated backends while
exercising the real ``SwarmRunner`` step loop: per-vehicle plan/control, the
O(N^2) pairwise safety filter, formation setpoints, per-cycle latency tracking,
and the guaranteed teardown.

Timing thresholds below are regression gates grounded in measured runs on this
host (see benchmark/swarm_scalability_benchmark.py for the full sweep):
N=100 mocked wall time is ~100 ms/cycle (~50 ms p95 as the runner measures it),
dominated by the O(N^2) safety filter and per-vehicle stats recording.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from apex_autopilot_optimization.core.types import (
    ControlInput,
    PlanningProblem,
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.simulation.config import SimulationConfig
from apex_autopilot_optimization.simulation.interface import SimulationInterface
from apex_autopilot_optimization.simulation.swarm_runner import SwarmMissionResult

# --------------------------------------------------------------------------- # helpers
# --------------------------------------------------------------------------- #


@contextmanager
def mocked_swarm_backends(
    n: int,
    *,
    start_slot: int = 0,
    spacing_m: float = 10.0,
    fail_step_slot: int | None = None,
    step_ok: bool = True,
):
    """Context manager providing mocked backends for ``n`` vehicle slots.

    Yields ``(bridges, sims)`` dicts keyed by slot. Patches stay active for the
    duration of the ``with`` block so ``SwarmRunner`` instantiates the mocked
    backends internally (same style as tests/unit/test_swarm_runner.py).
    """
    bridges: dict[int, MagicMock] = {}
    sims: dict[int, MagicMock] = {}
    bridge_mocks: list[MagicMock] = []
    sim_mocks: list[MagicMock] = []
    now = time.time()

    for i in range(start_slot, start_slot + n):
        b = MagicMock()
        b.connect.return_value = True
        b.arm.return_value = True
        b.set_mode.return_value = True
        b.get_state.return_value = StateVector(
            pose=Pose3D(float(i) * spacing_m, 0.0, 0.0),
            velocity=Velocity3D(0, 0, 0),
            timestamp=now,
        )
        b.send_control.return_value = True
        b.is_connected.return_value = True
        b.disconnect.return_value = True
        b.system_id = i
        bridges[i] = b
        bridge_mocks.append(b)

        s = MagicMock(spec=SimulationInterface)
        s.connect.return_value = True
        s.arm.return_value = True
        s.set_mode.return_value = True
        s.get_state.return_value = StateVector(
            pose=Pose3D(float(i), 0.0, 0.0), velocity=Velocity3D(0, 0, 0), timestamp=now
        )
        ok = step_ok and i != fail_step_slot
        s.step.return_value = ok
        s.disconnect.return_value = True
        s.is_connected = True
        s.time_scale = 1.0
        sims[i] = s
        sim_mocks.append(s)

    with (
        patch(
            "apex_autopilot_optimization.simulation.swarm_runner.MAVLinkBridge",
            side_effect=iter(bridge_mocks),
        ),
        patch(
            "apex_autopilot_optimization.simulation.swarm_runner.SimulationInterface",
            side_effect=iter(sim_mocks),
        ),
    ):
        yield bridges, sims


def make_config() -> SimulationConfig:
    return SimulationConfig(
        backend="mock",
        connection_string="mock://test",
        lockstep=False,
        time_scale=1.0,
        vehicle_type="multirotor",
        model="test_model",
    )


def make_problems(slots) -> dict[int, MagicMock]:
    return {slot: MagicMock(spec=PlanningProblem) for slot in slots}


def mission_wall_ms(
    runner, problems, config, steps: int, **kwargs
) -> tuple[float, SwarmMissionResult]:
    """Run a mission and return (wall_ms, result)."""
    start = time.perf_counter()
    result = runner.run_swarm_mission(problems=problems, config=config, max_steps=steps, **kwargs)
    return (time.perf_counter() - start) * 1000.0, result


# --------------------------------------------------------------------------- #
# port namespacing at scale
# --------------------------------------------------------------------------- #


class TestSwarmScalabilityPorts:
    """Port namespacing must stay unique and bindable up to slot 99 (N=100)."""

    def test_port_namespacing_to_slot_99(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        master = [mgr.master_port(i) for i in range(100)]
        sitl = [mgr.sitl_port(i) for i in range(100)]
        assert mgr.master_port(0) == 5760
        assert mgr.master_port(99) == 6750  # 5760 + 99*10
        assert mgr.sitl_port(0) == 5501
        assert mgr.sitl_port(99) == 6491  # 5501 + 99*10
        assert len(set(master)) == 100 and len(set(sitl)) == 100  # unique
        assert set(master).isdisjoint(sitl)  # the two families never collide
        for i in range(100):
            assert mgr.connection_string(i) == f"udp:127.0.0.1:{5760 + i * 10}"

    def test_all_100_vehicle_ports_bindable(self) -> None:
        """bind_test must succeed for every master/SITL port of a 100-vehicle swarm."""
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        for i in range(100):
            assert mgr.bind_test(mgr.master_port(i)) is True, f"master port {i} not bindable"
            assert mgr.bind_test(mgr.sitl_port(i)) is True, f"sitl port {i} not bindable"


# --------------------------------------------------------------------------- # state store at scale
# --------------------------------------------------------------------------- #


class TestSwarmStateStoreScale:
    def test_snapshot_covers_all_100_slots(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmStateStore

        store = SwarmStateStore()
        now = time.time()
        for i in range(100):
            store.update(
                i,
                StateVector(
                    pose=Pose3D(float(i), 0.0, 0.0),
                    velocity=Velocity3D(0, 0, 0),
                    timestamp=now,
                ),
            )
        snap = store.snapshot()
        assert len(snap) == 100
        assert set(snap.keys()) == set(range(100))

    def test_staleness_detection_at_scale(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmStateStore

        store = SwarmStateStore()
        now = time.time()
        for i in range(100):
            ts = now - 100.0 if i % 2 == 0 else now
            store.update(
                i,
                StateVector(
                    pose=Pose3D(0.0, 0.0, 0.0),
                    velocity=Velocity3D(0, 0, 0),
                    timestamp=ts,
                ),
            )
        stale = store.stale_slots(max_age_s=1.0)
        assert len(stale) == 50
        assert set(stale) == {i for i in range(100) if i % 2 == 0}
        assert store.is_fresh(1, max_age_s=1.0) is True
        assert store.is_fresh(0, max_age_s=1.0) is False


# --------------------------------------------------------------------------- #
# safety filter at scale
# --------------------------------------------------------------------------- #


class TestSwarmSafetyFilterScale:
    def _store_100(self, close_pair: bool = False):
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmStateStore

        store = SwarmStateStore()
        now = time.time()
        for i in range(100):
            x = 0.0 if (close_pair and i in (0, 1)) else float(i) * 10.0
            store.update(
                i,
                StateVector(pose=Pose3D(x, 0.0, 0.0), velocity=Velocity3D(0, 0, 0), timestamp=now),
            )
        return store

    def test_no_spurious_violations_100_vehicles(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmSafetyFilter

        store = self._store_100(close_pair=False)
        filt = SwarmSafetyFilter(min_separation_m=2.0)
        controls = {i: ControlInput(throttle=0.8) for i in range(100)}
        report = filt.filter(store, controls)
        assert report.violation_count == 0
        assert report.collision_events == []
        assert all(c.throttle == 0.8 for c in report.filtered_controls.values())

    def test_collisions_detected_among_100(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmSafetyFilter

        store = self._store_100(close_pair=True)
        filt = SwarmSafetyFilter(min_separation_m=2.0)
        controls = {i: ControlInput(throttle=0.8) for i in range(100)}
        report = filt.filter(store, controls)
        assert report.violation_count > 0
        assert (0, 1) in report.collision_events or (1, 0) in report.collision_events
        assert report.filtered_controls[0].throttle == 0.0
        assert report.filtered_controls[1].throttle == 0.0
        # vehicles farther apart are untouched
        assert report.filtered_controls[99].throttle == 0.8

    def test_safety_filter_latency_at_100(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmSafetyFilter

        store = self._store_100(close_pair=False)
        filt = SwarmSafetyFilter(min_separation_m=2.0)
        controls = {i: ControlInput(throttle=0.5) for i in range(100)}
        samples: list[float] = []
        for _ in range(50):
            start = time.perf_counter()
            filt.filter(store, controls)
            samples.append((time.perf_counter() - start) * 1000.0)
        samples.sort()
        mean_ms = sum(samples) / len(samples)
        p95_ms = samples[int(0.95 * len(samples)) - 1]
        print(
            f"\nsafety filter N=100: mean={mean_ms:.2f} ms p95={p95_ms:.2f} ms "
            f"max={samples[-1]:.2f} ms"
        )
        assert mean_ms < 50.0  # O(N^2) pairwise layer must stay well under the cycle budget
        assert p95_ms < 100.0


# --------------------------------------------------------------------------- # SwarmRunner at N=100
# --------------------------------------------------------------------------- #


class TestSwarmRunnerScale100:
    STEPS = 20
    N = 100

    def test_100_vehicle_mission_all_connect_and_complete(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        slots = list(range(self.N))
        with mocked_swarm_backends(self.N, spacing_m=10.0) as (bridges, sims):
            runner = SwarmRunner()
            wall_ms, result = mission_wall_ms(
                runner, make_problems(slots), make_config(), steps=self.STEPS
            )

        assert result.success is True
        assert len(result.per_vehicle) == self.N
        assert all(r.success for r in result.per_vehicle.values())
        assert result.makespan_seconds == pytest.approx(self.STEPS * 0.05, abs=1e-9)
        swarm = result.swarm
        assert swarm["total_missions"] == self.N * self.STEPS
        assert swarm["successful_missions"] == self.N * self.STEPS
        assert swarm["failed_missions"] == 0
        assert swarm["success_rate"] == 1.0
        assert swarm["connected_vehicles"] == self.N
        assert swarm["total_safety_violations"] == 0  # 10 m spacing > 2 m min separation
        # guaranteed teardown: every bridge and sim disconnected exactly once
        for b in bridges.values():
            b.disconnect.assert_called_once()
        for s in sims.values():
            s.disconnect.assert_called_once()
        per_cycle = wall_ms / self.STEPS
        print(
            f"\nN={self.N}: wall={wall_ms:.1f} ms over {self.STEPS} steps "
            f"({per_cycle:.1f} ms/step), runner p95 cycle={swarm['p95_cycle_latency_ms']:.1f} ms"
        )
        assert per_cycle < 200.0  # regression gate: full cycle incl. stats recording
        assert swarm["p95_cycle_latency_ms"] < 150.0  # runner-instrumented cycle p95

    def test_100_vehicle_cycle_latency_budget(self) -> None:
        """Per-cycle wall time at N=100 must stay inside a sane envelope.

        The Hivemind reference budget is <100 ms end-to-end per cycle; the
        control+safety portion targets <50 ms. With mocked backends the runner
        measures ~50 ms p95 (instrumented) / ~100 ms wall at N=100; the gate
        below is a regression guard, not a pass/fail on real hardware.
        """
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        slots = list(range(self.N))
        with mocked_swarm_backends(self.N, spacing_m=10.0) as (bridges, sims):
            runner = SwarmRunner()
            wall_ms, result = mission_wall_ms(
                runner, make_problems(slots), make_config(), steps=self.STEPS
            )

        per_cycle = wall_ms / self.STEPS
        assert per_cycle < 200.0
        assert result.swarm["p95_cycle_latency_ms"] < 150.0
        assert result.success is True

    def test_100_vehicle_partial_failure_isolation(self) -> None:
        """One failing vehicle must not abort the remaining 99."""
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        slots = list(range(self.N))
        with mocked_swarm_backends(self.N, spacing_m=10.0, fail_step_slot=50) as (bridges, sims):
            runner = SwarmRunner()
            result = runner.run_swarm_mission(
                problems=make_problems(slots), config=make_config(), max_steps=self.STEPS
            )

        assert result.success is False
        assert len(result.per_vehicle) == self.N
        assert result.per_vehicle[50].success is False
        assert all(r.success for slot, r in result.per_vehicle.items() if slot != 50)
        swarm = result.swarm
        # Stats are recorded per completed step; slot 50 is removed from the
        # step loop before cycle 0's stats recording, so it never contributes a
        # failed step record (existing runner semantics).
        assert swarm["total_missions"] == (self.N - 1) * self.STEPS
        assert swarm["successful_missions"] == (self.N - 1) * self.STEPS
        assert swarm["failed_missions"] == 0
        assert swarm["success_rate"] == 1.0
        for b in bridges.values():
            b.disconnect.assert_called_once()
        for s in sims.values():
            s.disconnect.assert_called_once()

    def test_abort_on_any_failure_halts_swarm_at_scale(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        slots = list(range(self.N))
        with mocked_swarm_backends(self.N, spacing_m=10.0, fail_step_slot=1) as (bridges, sims):
            runner = SwarmRunner()
            result = runner.run_swarm_mission(
                problems=make_problems(slots),
                config=make_config(),
                max_steps=self.STEPS,
                abort_on_any_failure=True,
            )

        assert result.success is False
        assert result.per_vehicle[1].success is False
        # aborted early: makespan is a single step, not the full mission
        assert result.makespan_seconds == pytest.approx(0.05, abs=1e-9)
        for b in bridges.values():
            b.disconnect.assert_called_once()
        for s in sims.values():
            s.disconnect.assert_called_once()

    def test_100_vehicle_formation_all_formations(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner
        from apex_autopilot_optimization.swarm.formation import FormationConfig

        slots = list(range(self.N))
        for formation_type in ("line", "wedge", "hexagon"):
            with mocked_swarm_backends(self.N, spacing_m=10.0) as (bridges, sims):
                runner = SwarmRunner()
                result = runner.run_swarm_mission(
                    problems=make_problems(slots),
                    config=make_config(),
                    max_steps=5,
                    formation=FormationConfig(formation_type=formation_type, spacing=2.0),
                )
                assert result.success is True
                assert len(result.per_vehicle) == self.N
                assert result.formation_deviation_m >= 0.0
                for b in bridges.values():
                    b.disconnect.assert_called_once()
                for s in sims.values():
                    s.disconnect.assert_called_once()

    def test_scalability_sweep_success_rates(self) -> None:
        """Every swarm size 1..100 (sampled) completes with mocked backends."""
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        for n in (1, 10, 50, 100):
            slots = list(range(n))
            steps = 10 if n < 100 else 20
            with mocked_swarm_backends(n, spacing_m=10.0) as (bridges, sims):
                runner = SwarmRunner()
                result = runner.run_swarm_mission(
                    problems=make_problems(slots), config=make_config(), max_steps=steps
                )
            assert result.success is True, f"N={n} failed"
            assert len(result.per_vehicle) == n
            assert all(r.success for r in result.per_vehicle.values())
            for b in bridges.values():
                b.disconnect.assert_called_once()
            for s in sims.values():
                s.disconnect.assert_called_once()


# --------------------------------------------------------------------------- #
# backward compatibility
# --------------------------------------------------------------------------- #


class TestSwarmScalabilityBackwardCompat:
    def test_single_vehicle_still_works(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        with mocked_swarm_backends(1, spacing_m=10.0) as (bridges, sims):
            runner = SwarmRunner()
            result = runner.run_swarm_mission(
                problems=make_problems([0]), config=make_config(), max_steps=5
            )
        assert result.success is True
        assert len(result.per_vehicle) == 1
        assert result.per_vehicle[0].success is True
        bridges[0].disconnect.assert_called_once()
        sims[0].disconnect.assert_called_once()
