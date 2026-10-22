"""Tests for the runtime fault injection harness and ChaosExperiment.

Verifies that faults are actually injected into live component methods
(CBFFilter.filter, CombatReallocator.report_bda, PolicyEngine clock), that
they are restored after use, and that ChaosExperiment runs a scenario under a
fault schedule and reports pass/fail against safety probes -- including
detecting a real safety regression (sensor dropout hides an obstacle and CBF
fails to correct).
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from apex_autopilot_optimization.core.types import ControlInput, Pose3D, StateVector, Velocity3D
from apex_autopilot_optimization.safety.cbf import CBFConfig, CBFFilter
from apex_autopilot_optimization.simulation.combat_reallocator import CombatReallocator
from apex_autopilot_optimization.swarm.wta_solver import (
    AllocationMode,
    Target,
    TieredWTASolver,
    Weapon,
    WTAConfig,
)
from apex_autopilot_optimization.governance.policy_engine import (
    PolicyEngine,
    PolicyEngineConfig,
    Role,
    WTAAssignment,
)
from apex_autopilot_optimization.messaging.veto_manager import VetoManager
from apex_autopilot_optimization.chaos import (
    ChaosExperiment,
    FaultSchedule,
    FaultSpec,
    FaultType,
    RuntimeFaultInjector,
    Severity,
    cbf_throttle_monotonic,
)
from apex_autopilot_optimization.chaos.probes import cbf_correction_when_unsafe


def _solver() -> TieredWTASolver:
    return TieredWTASolver(WTAConfig(wta_mode="milp", milp_time_limit_ms=0))


# --------------------------------------------------------------------------- #
# RuntimeFaultInjector: faults really land on live component methods
# --------------------------------------------------------------------------- #

class TestRuntimeFaultInjector:
    def test_sensor_noise_on_cbf_filter(self) -> None:
        cbf = CBFFilter()
        state = StateVector(pose=Pose3D(1.0, 0.0, 0.0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        obstacles = [{"type": "sphere", "center": [2.0, 0.0, 0.0], "radius": 1.0}]

        injector = RuntimeFaultInjector()
        result = injector.apply(
            cbf, "filter", FaultType.SENSOR_NOISE, {"noise_std": 0.5, "seed": 1}
        )
        assert result is not None
        out = cbf.filter(state, control, obstacles)
        assert isinstance(out, ControlInput)
        assert cbf_throttle_monotonic(control, out) == []
        injector.restore_all()
        # After restore, behavior is back to the original (no fault params).
        out2 = cbf.filter(state, control, obstacles)
        assert isinstance(out2, ControlInput)

    def test_sensor_dropout_hides_obstacles(self) -> None:
        cbf = CBFFilter(config=CBFConfig(alpha=0.5, safety_margin=0.1, max_correction=10.0))
        state = StateVector(pose=Pose3D(1.0, 0.0, 0.0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.8)
        # dist = |[1,0,0]-[2,0,0]| - 1 = 0.0 <= margin 0.1 -> UNSAFE -> CBF reduces throttle.
        obstacles = [{"type": "sphere", "center": [2.0, 0.0, 0.0], "radius": 1.0}]
        baseline = cbf.filter(state, control, obstacles).throttle
        assert baseline < control.throttle  # CBF corrects when it can see the obstacle

        injector = RuntimeFaultInjector()
        injector.apply(
            cbf, "filter", FaultType.SENSOR_DROPOUT, {"dropout_prob": 1.0}
        )
        # All obstacles dropped -> CBF passes control through unchanged (0.8).
        out = cbf.filter(state, control, obstacles)
        assert out.throttle == pytest.approx(0.8, abs=1e-9)
        injector.restore_all()

    def test_actuator_failure_clamps_throttle(self) -> None:
        cbf = CBFFilter()
        state = StateVector(pose=Pose3D(0.0, 0.0, 0.0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.8)
        obstacles = [{"type": "sphere", "center": [2.0, 0.0, 0.0], "radius": 1.0}]

        injector = RuntimeFaultInjector()
        injector.apply(
            cbf, "filter", FaultType.ACTUATOR_FAILURE, {"stuck_throttle": 0.0}
        )
        out = cbf.filter(state, control, obstacles)
        assert out.throttle == pytest.approx(0.0, abs=1e-9)
        injector.restore_all()

    def test_cpu_spike_delays_call(self) -> None:
        def target():
            return 42

        injector = RuntimeFaultInjector()
        wrapped = injector  # not used; inject directly via behavior for timing
        from apex_autopilot_optimization.chaos.runtime import _bound_behavior, BEHAVIORS
        import time as _time

        fn = _bound_behavior(target, BEHAVIORS[FaultType.CPU_SPIKE], {"delay_sec": 0.05})
        start = _time.perf_counter()
        val = fn()
        elapsed = _time.perf_counter() - start
        assert val == 42
        assert elapsed >= 0.04

    def test_network_drop_on_report_bda_returns_none(self) -> None:
        weapons = [Weapon(0), Weapon(1)]
        targets = [Target(0, value=10.0), Target(1, value=1.0)]
        p = np.array([[0.9, 0.1], [0.1, 0.9]])
        cr = CombatReallocator(_solver(), weapons, targets, p, np.array([10.0, 1.0]),
                               mode=AllocationMode.SLS)
        cr.request_allocation()  # ENGAGING

        injector = RuntimeFaultInjector()
        injector.apply(cr, "report_bda", FaultType.NETWORK_DROP, {"drop_prob": 1.0})
        result = cr.report_bda([0])  # BDA dropped
        assert result is None
        injector.restore_all()

    def test_clock_drift_skews_engine_clock(self) -> None:
        engine = PolicyEngine(
            veto_manager=VetoManager(),
            hitl=None,
            config=PolicyEngineConfig(hitl_enabled=False),
            clock=time.time,
        )
        injector = RuntimeFaultInjector()
        before = engine._clock()
        injector.apply_clock_drift(engine, 5.0)
        after = engine._clock()
        assert after == pytest.approx(before + 5.0, abs=0.01)
        injector.restore_all()
        assert engine._clock() == pytest.approx(before, abs=0.01)

    def test_scope_restores_after_exit(self) -> None:
        cbf = CBFFilter()
        control = ControlInput(throttle=0.5)
        state = StateVector(pose=Pose3D(0, 0, 0), velocity=Velocity3D(0, 0, 0))
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]

        injector = RuntimeFaultInjector()
        with injector.scope():
            injector.apply(cbf, "filter", FaultType.ACTUATOR_FAILURE, {"stuck_throttle": 0.0})
            out = cbf.filter(state, control, obstacles)
            assert out.throttle == pytest.approx(0.0, abs=1e-9)
        # Restored on exit: original behavior returns.
        out = cbf.filter(state, control, obstacles)
        assert out.throttle == pytest.approx(0.5, abs=1e-9)


# --------------------------------------------------------------------------- #
# ChaosExperiment: schedule + scenario + probes -> report
# --------------------------------------------------------------------------- #

class TestChaosExperiment:
    def _cbf_components(self):
        cbf = CBFFilter(config=CBFConfig(safety_margin=0.5))
        state = StateVector(pose=Pose3D(1.0, 0.0, 0.0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        obstacles = [{"type": "sphere", "center": [2.0, 0.0, 0.0], "radius": 1.0}]
        return cbf, state, control, obstacles

    def test_sensor_noise_trials_pass_monotonic_probe(self) -> None:
        cbf, state, control, obstacles = self._cbf_components()
        captured = {}

        def scenario(injector, comps):
            captured["out"] = comps["cbf"].filter(state, control, obstacles)

        exp = ChaosExperiment("cbf-noise")
        exp.register("cbf", cbf).set_scenario(scenario)
        exp.add_probe(lambda injector, comps: cbf_throttle_monotonic(
            control, captured.get("out", ControlInput(throttle=0.0))
        ))
        sched = FaultSchedule()
        sched.add(FaultSpec(FaultType.SENSOR_NOISE, "cbf.filter", {"noise_std": 1.0, "seed": 7}))
        report = exp.run(schedule=sched, trials=10, seed=3)
        assert report.total_trials == 10
        assert report.passed + report.failed == 10
        assert report.passed == 10  # noise never increases throttle; invariant holds
        assert report.failed == 0

    def test_sensor_dropout_trials_fail_unsafe_probe(self) -> None:
        """Sensor dropout hides a close obstacle -> CBF fails to reduce throttle -> harness flags it."""
        cbf, state, control, obstacles = self._cbf_components()
        # dist = |[1,0,0]-[2,0,0]| - 1 = 0 <= margin 0.5 -> UNSAFE.
        captured = {"min_dist": 0.0, "out": None}

        def scenario(injector, comps):
            captured["out"] = comps["cbf"].filter(state, control, obstacles)

        exp = ChaosExperiment("cbf-dropout-unsafe")
        exp.register("cbf", cbf).set_scenario(scenario)
        exp.add_probe(lambda injector, comps: cbf_correction_when_unsafe(
            captured["min_dist"], 0.5, control, captured["out"]
        ))
        sched = FaultSchedule()
        sched.add(FaultSpec(FaultType.SENSOR_DROPOUT, "cbf.filter", {"dropout_prob": 1.0}))
        report = exp.run(schedule=sched, trials=6, seed=1)
        assert report.total_trials == 6
        assert report.failed == 6  # every trial: obstacle hidden, throttle not reduced
        assert report.passed == 0
        assert all("throttle not reduced" in v for r in report.results for v in r.violations)

    def test_no_faults_trials_pass(self) -> None:
        cbf, state, control, obstacles = self._cbf_components()
        captured = {}

        def scenario(injector, comps):
            captured["out"] = comps["cbf"].filter(state, control, obstacles)

        exp = ChaosExperiment("cbf-baseline")
        exp.register("cbf", cbf).set_scenario(scenario)
        exp.add_probe(lambda injector, comps: cbf_throttle_monotonic(
            control, captured.get("out", ControlInput(throttle=0.0))
        ))
        report = exp.run(trials=5, seed=9)
        assert report.passed == 5
        assert report.failed == 0

    def test_fault_spec_validation(self) -> None:
        with pytest.raises(ValueError):
            FaultSpec(FaultType.CPU_SPIKE, "x", duration_sec=-1)
        with pytest.raises(ValueError):
            FaultSpec(FaultType.CPU_SPIKE, "x", start_after_sec=-1)
        spec = FaultSpec(FaultType.SENSOR_NOISE, "cbf.filter", {"noise_std": 0.5},
                         severity=Severity.HIGH)
        assert spec.severity is Severity.HIGH
        assert spec.params == {"noise_std": 0.5}

    def test_fault_schedule_due_at(self) -> None:
        sched = FaultSchedule()
        sched.add(FaultSpec(FaultType.NETWORK_DELAY, "a", start_after_sec=0.0))
        sched.add(FaultSpec(FaultType.CPU_SPIKE, "b", start_after_sec=10.0))
        assert len(sched.due_at(0.0)) == 1
        assert len(sched.due_at(5.0)) == 1
        assert len(sched.due_at(10.0)) == 2

    def test_report_str(self) -> None:
        cbf, state, control, obstacles = self._cbf_components()
        exp = ChaosExperiment("x")
        exp.register("cbf", cbf)
        exp.set_scenario(lambda injector, comps: None)
        exp.add_probe(lambda injector, comps: [])
        report = exp.run(trials=2, seed=1)
        s = str(report)
        assert "ChaosExperiment" in s
        assert "trials: 2" in s
