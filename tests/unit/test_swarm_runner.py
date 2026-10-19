"""Unit tests for SwarmRunner and supporting swarm orchestration classes.

Mirroring tests/unit/test_simulation.py style: pytest, MagicMock(spec=...),
patch("...runner.SimulationInterface", ...) and
patch("...integration.mavlink.MAVLinkBridge", ...).

These tests exercise the swarm layer with mocked backends so no Gazebo/PX4 is required.
"""

from __future__ import annotations

import socket
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
from apex_autopilot_optimization.integration.mavlink import MAVLinkBridge
from apex_autopilot_optimization.simulation.config import SimulationConfig
from apex_autopilot_optimization.simulation.interface import SimulationInterface


class TestSwarmConnectionManager:
    """Tests for SwarmConnectionManager port namespacing and connect/disconnect."""

    def _make_config(self) -> SimulationConfig:
        return SimulationConfig(
            backend="mock",
            connection_string="mock://test",
            lockstep=False,
            time_scale=1.0,
            vehicle_type="multirotor",
            model="test_model",
        )

    def test_port_namespacing_formulas(self) -> None:
        """master_port(i) == 5760 + i*10, sitl_port(i) == 5501 + i*10."""
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        assert mgr.master_port(0) == 5760
        assert mgr.master_port(1) == 5770
        assert mgr.master_port(3) == 5790
        assert mgr.sitl_port(0) == 5501
        assert mgr.sitl_port(2) == 5521
        assert mgr.connection_string(0) == "udp:127.0.0.1:5760"
        assert mgr.connection_string(2) == "udp:127.0.0.1:5780"

    def test_connect_all_creates_one_bridge_per_slot(self) -> None:
        """N mocked bridges, each connect() called with correct string, system_id == i."""
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        bridges: dict[int, MagicMock] = {}
        with patch(
            "apex_autopilot_optimization.simulation.swarm_runner.MAVLinkBridge"
        ) as bridge_cls:
            for i in range(3):
                inst = MagicMock(spec=MAVLinkBridge)
                inst.connect.return_value = True
                inst.system_id = i
                inst.is_connected.return_value = True
                bridge_cls.return_value = inst
                bridges[i] = inst
                ok = mgr._connect_slot(i, base_master_port=5760)
                assert ok is True
                inst.connect.assert_called_once_with(mgr.connection_string(i))
                assert mgr.get_bridge(i) is inst

        assert len({id(b) for b in bridges.values()}) == 3

    def test_connect_all_partial_failure_continues(self) -> None:
        """One bridge connect() returns False; others still connected; per-slot map."""
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        results: dict[int, bool] = {}
        with patch(
            "apex_autopilot_optimization.simulation.swarm_runner.MAVLinkBridge"
        ) as bridge_cls:
            for i in range(3):
                inst = MagicMock(spec=MAVLinkBridge)
                inst.system_id = i
                inst.is_connected.return_value = i != 1
                inst.connect.return_value = i != 1  # slot 1 fails
                bridge_cls.return_value = inst
                results[i] = mgr._connect_slot(i, base_master_port=5760)

        assert results[0] is True
        assert results[1] is False
        assert results[2] is True
        assert mgr.is_connected(0) is True
        assert mgr.is_connected(1) is False
        assert mgr.is_connected(2) is True

    def test_disconnect_all_closes_even_on_failure(self) -> None:
        """One bridge disconnect() raises; rest still closed; no exception propagates."""
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        with patch(
            "apex_autopilot_optimization.simulation.swarm_runner.MAVLinkBridge"
        ) as bridge_cls:
            inst0 = MagicMock(spec=MAVLinkBridge)
            inst0.disconnect.return_value = True
            inst1 = MagicMock(spec=MAVLinkBridge)
            inst1.disconnect.side_effect = RuntimeError("boom")
            inst2 = MagicMock(spec=MAVLinkBridge)
            inst2.disconnect.return_value = True
            bridge_cls.side_effect = [inst0, inst1, inst2]
            for i in range(3):
                mgr._connect_slot(i, base_master_port=5760)

        results = mgr.disconnect_all()
        assert results["bridge_0"] is True
        assert results["bridge_1"] is False
        assert results["bridge_2"] is True
        inst0.disconnect.assert_called_once()
        inst1.disconnect.assert_called_once()
        inst2.disconnect.assert_called_once()

    def test_health_check_all_quarantines_unhealthy(self) -> None:
        """health_check_all() returns per-slot health; unhealthy excluded."""
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        with patch(
            "apex_autopilot_optimization.simulation.swarm_runner.MAVLinkBridge"
        ) as bridge_cls:
            inst0 = MagicMock(spec=MAVLinkBridge)
            inst0.is_connected.return_value = True
            inst1 = MagicMock(spec=MAVLinkBridge)
            inst1.is_connected.return_value = False
            inst2 = MagicMock(spec=MAVLinkBridge)
            inst2.is_connected.return_value = True
            bridge_cls.side_effect = [inst0, inst1, inst2]
            for i in range(3):
                mgr._connect_slot(i, base_master_port=5760)

        health = mgr.health_check_all()
        assert health[0] is True
        assert health[1] is False
        assert health[2] is True
        assert mgr.get_healthy_slots() == [0, 2]

    def test_bind_test_refuses_occupied_port(self) -> None:
        """bind_test returns False for a port already bound."""
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmConnectionManager,
        )

        mgr = SwarmConnectionManager()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 5760))
        try:
            assert mgr.bind_test(5760) is False
        finally:
            sock.close()
        assert mgr.bind_test(5770) is True


class TestSwarmStateStore:
    """Tests for SwarmStateStore distributed per-vehicle state with freshness TTL."""

    def test_update_snapshot_get(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmStateStore,
        )

        store = SwarmStateStore()
        s0 = StateVector(pose=Pose3D(1, 2, 3), velocity=Velocity3D(0, 0, 0))
        s1 = StateVector(pose=Pose3D(4, 5, 6), velocity=Velocity3D(0, 0, 0))
        store.update(0, s0)
        store.update(1, s1)

        snap = store.snapshot()
        assert set(snap.keys()) == {0, 1}
        assert snap[0] is s0
        assert snap[1] is s1
        assert store.get(0) is s0
        assert store.get(5) is None

    def test_is_fresh_and_stale_slots(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmStateStore,
        )

        store = SwarmStateStore()
        old = StateVector(
            pose=Pose3D(0, 0, 0),
            velocity=Velocity3D(0, 0, 0),
            timestamp=time.time() - 100.0,
        )
        fresh = StateVector(
            pose=Pose3D(0, 0, 0),
            velocity=Velocity3D(0, 0, 0),
            timestamp=time.time(),
        )
        store.update(0, old)
        store.update(1, fresh)

        assert store.is_fresh(0, max_age_s=1.0) is False
        assert store.is_fresh(1, max_age_s=1.0) is True
        assert store.stale_slots(max_age_s=1.0) == [0]
        assert store.stale_slots(max_age_s=200.0) == []


class TestFormationSetpointGenerator:
    """Tests for FormationSetpointGenerator wrapping swarm/formation.py."""

    def test_compute_setpoints_line(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            FormationSetpointGenerator,
        )
        from apex_autopilot_optimization.swarm.formation import FormationConfig

        gen = FormationSetpointGenerator(FormationConfig(formation_type="line", spacing=2.0))
        leader = StateVector(pose=Pose3D(10, 0, 5), velocity=Velocity3D(0, 0, 0))
        positions = gen.compute_setpoints(leader, 4)
        assert len(positions) == 4
        assert positions[0].x == pytest.approx(10.0)
        assert positions[1].x == pytest.approx(8.0)
        assert positions[3].x == pytest.approx(4.0)
        for pos in positions:
            assert pos.z == pytest.approx(5.0)

    def test_slot_setpoint_indexing(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            FormationSetpointGenerator,
        )
        from apex_autopilot_optimization.swarm.formation import FormationConfig

        gen = FormationSetpointGenerator(FormationConfig(formation_type="wedge", spacing=3.0))
        leader = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        all_positions = gen.compute_setpoints(leader, 3)
        assert gen.slot_setpoint(0, leader, 3) == all_positions[0]
        assert gen.slot_setpoint(1, leader, 3) == all_positions[1]
        assert gen.slot_setpoint(2, leader, 3) == all_positions[2]

    def test_unknown_formation_falls_back_to_line(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            FormationSetpointGenerator,
        )
        from apex_autopilot_optimization.swarm.formation import FormationConfig

        gen = FormationSetpointGenerator(FormationConfig(formation_type="bogus"))
        leader = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        positions = gen.compute_setpoints(leader, 2)
        assert len(positions) == 2


class TestSwarmSafetyFilter:
    """Tests for SwarmSafetyFilter: collision avoidance, geofence, no-fly, RTL."""

    def _make_states(self) -> dict[int, StateVector]:
        now = time.time()
        return {
            0: StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0), timestamp=now),
            1: StateVector(pose=Pose3D(1, 0, 0), velocity=Velocity3D(0, 0, 0), timestamp=now),
        }

    def test_collision_avoidance_zeroes_controls(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmSafetyFilter,
            SwarmStateStore,
        )

        store = SwarmStateStore()
        states = self._make_states()
        store.update(0, states[0])
        store.update(1, states[1])

        filt = SwarmSafetyFilter(min_separation_m=2.0)
        controls = {
            0: ControlInput(throttle=0.8, roll_rate=0.1),
            1: ControlInput(throttle=0.8, roll_rate=0.1),
        }
        report = filt.filter(store, controls)
        assert report.violation_count > 0
        assert len(report.collision_events) == 1
        assert (0, 1) in report.collision_events or (1, 0) in report.collision_events
        assert report.filtered_controls[0].throttle < 0.8
        assert report.filtered_controls[1].throttle < 0.8

    def test_no_collision_when_far_apart(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmSafetyFilter,
            SwarmStateStore,
        )

        store = SwarmStateStore()
        store.update(0, StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0)))
        store.update(1, StateVector(pose=Pose3D(100, 0, 0), velocity=Velocity3D(0, 0, 0)))

        filt = SwarmSafetyFilter(min_separation_m=2.0)
        controls = {0: ControlInput(throttle=0.5), 1: ControlInput(throttle=0.5)}
        report = filt.filter(store, controls)
        assert report.violation_count == 0
        assert report.collision_events == []
        assert report.filtered_controls[0].throttle == 0.5

    def test_geofence_violation_hold(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmSafetyFilter,
            SwarmStateStore,
        )

        store = SwarmStateStore()
        store.update(0, StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0)))

        filt = SwarmSafetyFilter(
            min_separation_m=2.0,
            geofence=((-10, -10), (10, -10), (10, 10), (-10, 10)),
            z_min=0.0,
            z_max=10.0,
        )
        controls = {0: ControlInput(throttle=0.5)}
        report = filt.filter(store, controls)
        assert report.violation_count == 0

        store.update(0, StateVector(pose=Pose3D(100, 0, 0), velocity=Velocity3D(0, 0, 0)))
        report = filt.filter(store, controls)
        assert report.violation_count > 0
        assert report.filtered_controls[0].throttle == 0.0

    def test_no_fly_zone_hold(self) -> None:
        from apex_autopilot_optimization.simulation.swarm_runner import (
            ExclusionZone,
            SwarmSafetyFilter,
            SwarmStateStore,
        )

        store = SwarmStateStore()
        store.update(0, StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0)))

        filt = SwarmSafetyFilter(
            min_separation_m=2.0,
            no_fly_zones=[ExclusionZone(center=Pose3D(5, 0, 0), radius_m=2.0)],
        )
        controls = {0: ControlInput(throttle=0.5)}
        report = filt.filter(store, controls)
        assert report.violation_count == 0

        store.update(0, StateVector(pose=Pose3D(5, 0, 0), velocity=Velocity3D(0, 0, 0)))
        report = filt.filter(store, controls)
        assert report.violation_count > 0
        assert report.filtered_controls[0].throttle == 0.0


class TestSwarmStatsAggregator:
    """Tests for SwarmStatsAggregator per-vehicle rollups + swarm-level stats."""

    def test_record_and_get_vehicle_stats(self) -> None:
        from apex_autopilot_optimization.simulation.result import SimulationResult
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmStatsAggregator,
        )

        agg = SwarmStatsAggregator()
        r = SimulationResult(success=True, duration_seconds=1.5, metrics={})
        agg.record_mission(
            0,
            r,
            cycle_latency_ms=10.0,
            separation_m=5.0,
            formation_deviation_m=0.2,
        )
        stats = agg.get_vehicle_stats(0)
        assert stats["missions_run"] == 1
        assert stats["missions_success"] == 1
        assert stats["missions_fail"] == 0
        assert stats["total_duration_seconds"] == 1.5
        assert stats["mean_step_latency_ms"] == 10.0
        assert stats["min_observed_separation_m"] == 5.0
        assert stats["mean_formation_deviation_m"] == 0.2

    def test_get_swarm_stats_rollup(self) -> None:
        from apex_autopilot_optimization.simulation.result import SimulationResult
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmStatsAggregator,
        )

        agg = SwarmStatsAggregator()
        agg.record_mission(0, SimulationResult(success=True, duration_seconds=2.0), 10.0, 5.0, 0.1)
        agg.record_mission(1, SimulationResult(success=False, duration_seconds=4.0), 20.0, 3.0, 0.5)
        agg.record_mission(2, SimulationResult(success=True, duration_seconds=3.0), 15.0, 4.0, 0.3)
        agg.set_connected_counts(3, 3)

        swarm = agg.get_swarm_stats()
        assert swarm["total_missions"] == 3
        assert swarm["successful_missions"] == 2
        assert swarm["failed_missions"] == 1
        assert swarm["success_rate"] == pytest.approx(2 / 3)
        assert swarm["swarm_makespan_seconds"] == pytest.approx(4.0)
        assert swarm["total_safety_violations"] == 0
        assert swarm["connected_vehicles"] == 3

    def test_get_runner_stats_backward_compat(self) -> None:
        from apex_autopilot_optimization.simulation.result import SimulationResult
        from apex_autopilot_optimization.simulation.swarm_runner import (
            SwarmStatsAggregator,
        )

        agg = SwarmStatsAggregator()
        agg.record_mission(0, SimulationResult(success=True, duration_seconds=1.0), 10.0, 5.0, 0.1)
        agg.record_mission(1, SimulationResult(success=False, duration_seconds=2.0), 10.0, 5.0, 0.1)
        stats = agg.get_runner_stats()
        assert stats["total_missions"] == 2
        assert stats["successful_missions"] == 1
        assert stats["failed_missions"] == 1
        assert stats["total_duration_seconds"] == pytest.approx(3.0)


@contextmanager
def _mocked_backends(n: int, step_ok: bool = True):
    """Context manager providing mocked MAVLinkBridge + SimulationInterface for n vehicles.

    Yields (runner, bridges, sims). Patches stay active for the duration of the
    ``with`` block so run_swarm_mission can instantiate the mocked backends.
    """
    from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

    bridges: dict[int, MagicMock] = {}
    sims: dict[int, MagicMock] = {}
    bridge_mocks: list[MagicMock] = []
    sim_mocks: list[MagicMock] = []

    for i in range(n):
        b = MagicMock()
        b.connect.return_value = True
        b.arm.return_value = True
        b.set_mode.return_value = True
        b.get_state.return_value = StateVector(
            pose=Pose3D(float(i), 0, 0),
            velocity=Velocity3D(0, 0, 0),
            timestamp=time.time(),
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
            pose=Pose3D(float(i), 0, 0),
            velocity=Velocity3D(0, 0, 0),
            timestamp=time.time(),
        )
        s.send_control.return_value = True
        s.step.return_value = step_ok
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
        runner = SwarmRunner()
        yield runner, bridges, sims


class TestSwarmRunner:
    """Tests for SwarmRunner end-to-end swarm mission execution (mocked)."""

    def _make_config(self) -> SimulationConfig:
        return SimulationConfig(
            backend="mock",
            connection_string="mock://test",
            lockstep=False,
            time_scale=1.0,
            vehicle_type="multirotor",
            model="test_model",
        )

    def _make_problems(self, n: int) -> dict[int, MagicMock]:
        return {i: MagicMock(spec=PlanningProblem) for i in range(n)}

    def test_run_swarm_mission_success_mocked(self) -> None:
        """N=3, all mocked OK -> per-vehicle success + swarm rollup non-empty."""
        with _mocked_backends(3, step_ok=True) as (runner, bridges, sims):
            problems = self._make_problems(3)
            config = self._make_config()

            result = runner.run_swarm_mission(problems=problems, config=config)

        assert result is not None
        assert len(result.per_vehicle) == 3
        assert all(r.success for r in result.per_vehicle.values())
        assert result.swarm["total_missions"] >= 3
        for b in bridges.values():
            b.disconnect.assert_called_once()
        for s in sims.values():
            s.disconnect.assert_called_once()

    def test_run_swarm_mission_one_vehicle_fails_others_continue(self) -> None:
        """Vehicle 1 step fails; vehicles 0 and 2 complete."""
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        bridges: dict[int, MagicMock] = {}
        sims: dict[int, MagicMock] = {}
        bridge_mocks: list[MagicMock] = []
        sim_mocks: list[MagicMock] = []

        for i in range(3):
            b = MagicMock()
            b.connect.return_value = True
            b.arm.return_value = True
            b.set_mode.return_value = True
            b.get_state.return_value = StateVector(
                pose=Pose3D(float(i) * 10, 0, 0),
                velocity=Velocity3D(0, 0, 0),
                timestamp=time.time(),
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
                pose=Pose3D(float(i), 0, 0),
                velocity=Velocity3D(0, 0, 0),
                timestamp=time.time(),
            )
            s.send_control.return_value = True
            s.step.return_value = i != 1  # slot 1 fails to step
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
            runner = SwarmRunner()
            problems = self._make_problems(3)
            config = self._make_config()
            result = runner.run_swarm_mission(problems=problems, config=config)

        assert result.per_vehicle[0].success is True
        assert result.per_vehicle[1].success is False
        assert result.per_vehicle[2].success is True
        for b in bridges.values():
            b.disconnect.assert_called_once()

    def test_abort_on_any_failure_stops_swarm(self) -> None:
        """abort_on_any_failure flag -> failures recorded; slot 1 fails."""
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        bridges: dict[int, MagicMock] = {}
        bridge_mocks: list[MagicMock] = []
        sim_mocks: list[MagicMock] = []

        for i in range(3):
            b = MagicMock()
            b.connect.return_value = True
            b.arm.return_value = True
            b.set_mode.return_value = True
            b.get_state.return_value = StateVector(
                pose=Pose3D(float(i) * 10, 0, 0),
                velocity=Velocity3D(0, 0, 0),
                timestamp=time.time(),
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
                pose=Pose3D(float(i), 0, 0),
                velocity=Velocity3D(0, 0, 0),
                timestamp=time.time(),
            )
            s.send_control.return_value = True

            def make_step(slot):
                def step(dt):
                    return slot != 1  # slot 1 fails

                return step

            s.step.side_effect = make_step(i)
            s.disconnect.return_value = True
            s.is_connected = True
            s.time_scale = 1.0
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
            runner = SwarmRunner()
            problems = self._make_problems(3)
            config = self._make_config()
            result = runner.run_swarm_mission(
                problems=problems, config=config, abort_on_any_failure=True
            )

        assert result.per_vehicle[1].success is False
        for b in bridges.values():
            b.disconnect.assert_called_once()

    def test_disconnect_all_guaranteed_teardown_on_failure(self) -> None:
        """disconnect_all() called in finally even when a vehicle crashes mid-mission."""
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        bridges: dict[int, MagicMock] = {}
        bridge_mocks: list[MagicMock] = []
        sim_mocks: list[MagicMock] = []

        for i in range(2):
            b = MagicMock()
            b.connect.return_value = True
            b.arm.return_value = True
            b.set_mode.return_value = True
            b.get_state.return_value = StateVector(
                pose=Pose3D(float(i) * 10, 0, 0),
                velocity=Velocity3D(0, 0, 0),
                timestamp=time.time(),
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
                pose=Pose3D(float(i), 0, 0),
                velocity=Velocity3D(0, 0, 0),
                timestamp=time.time(),
            )
            s.send_control.return_value = True
            s.step.return_value = False  # fail immediately
            s.disconnect.return_value = True
            s.is_connected = True
            s.time_scale = 1.0
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
            runner = SwarmRunner()
            problems = self._make_problems(2)
            config = self._make_config()
            result = runner.run_swarm_mission(problems=problems, config=config)

        assert result is not None
        for b in bridges.values():
            b.disconnect.assert_called_once()

    def test_connect_zero_vehicles_returns_failure(self) -> None:
        """connect_all with zero vehicles -> failure SwarmMissionResult immediately."""
        from apex_autopilot_optimization.simulation.swarm_runner import SwarmRunner

        runner = SwarmRunner()
        problems: dict[int, MagicMock] = {}
        config = self._make_config()
        result = runner.run_swarm_mission(problems=problems, config=config)
        assert result is not None
        assert result.swarm["total_missions"] == 0
        assert result.per_vehicle == {}
