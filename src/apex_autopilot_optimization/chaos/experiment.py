"""Chaos experiment orchestration: schedule faults, run trials, verify invariants.

A :class:`ChaosExperiment` registers the components under test, a scenario
(exercising them), and safety probes.  Each trial resets state, injects the
fault schedule, runs the scenario, runs the probes, and records a
:class:`TrialResult`.  A :class:`ChaosRunReport` aggregates the trials.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from apex_autopilot_optimization.chaos.faults import FaultSchedule, FaultSpec, FaultType
from apex_autopilot_optimization.chaos.runtime import RuntimeFaultInjector

__all__ = ["TrialResult", "ChaosRunReport", "ChaosExperiment"]

ScenarioFn = Callable[[RuntimeFaultInjector, dict[str, Any]], None]
ProbeFn = Callable[[RuntimeFaultInjector, dict[str, Any]], list[str]]


@dataclass
class TrialResult:
    """Outcome of a single chaos trial."""

    trial_id: int
    faults_injected: list[str]
    passed: bool
    violations: list[str]
    duration_ms: float
    error: str | None = None

    def summary_line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        faults = ", ".join(self.faults_injected) or "(none)"
        err = f" | error: {self.error}" if self.error else ""
        return f"trial {self.trial_id}: {status} [{faults}]{err}"


@dataclass
class ChaosRunReport:
    """Aggregated results of a chaos experiment run."""

    experiment_name: str
    total_trials: int
    passed: int
    failed: int
    results: list[TrialResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total_trials if self.total_trials else 0.0

    def failures(self) -> list[TrialResult]:
        return [r for r in self.results if not r.passed]

    def __str__(self) -> str:
        lines = [
            f"ChaosExperiment '{self.experiment_name}'",
            f"  trials: {self.total_trials}  passed: {self.passed}  failed: {self.failed}  "
            f"pass_rate: {self.pass_rate:.2%}  duration: {self.duration_ms:.1f} ms",
        ]
        for r in self.results:
            lines.append("  " + r.summary_line())
        return "\n".join(lines)


class ChaosExperiment:
    """Run a scenario under a fault schedule and check safety probes.

    Example::

        exp = ChaosExperiment("cbf-under-sensor-noise")
        exp.register("cbf", cbf_filter)
        exp.set_scenario(lambda injector, comps: comps["cbf"].filter(state, ctrl, obs))
        exp.add_probe(lambda injector, comps: probes.cbf_throttle_monotonic(ctrl, last_out))
        schedule = FaultSchedule()
        schedule.add(FaultSpec(FaultType.SENSOR_NOISE, "cbf.filter", {"noise_std": 1.0}))
        report = exp.run(schedule=schedule, trials=50, seed=7)
    """

    def __init__(self, name: str, injector: RuntimeFaultInjector | None = None):
        self.name = name
        self._injector = injector or RuntimeFaultInjector()
        self._components: dict[str, Any] = {}
        self._scenario: ScenarioFn | None = None
        self._probes: list[ProbeFn] = []
        self._last_output: Any = None

    # -- registration ------------------------------------------------------
    def register(self, name: str, obj: Any) -> "ChaosExperiment":
        self._components[name] = obj
        return self

    def set_scenario(self, fn: ScenarioFn) -> "ChaosExperiment":
        self._scenario = fn
        return self

    def add_probe(self, fn: ProbeFn) -> "ChaosExperiment":
        self._probes.append(fn)
        return self

    # -- schedule injection ------------------------------------------------
    def inject_schedule(self, schedule: FaultSchedule, now_sec: float = 0.0) -> list[str]:
        """Inject every fault in ``schedule`` due at ``now_sec``.

        Returns the list of fault descriptions actually injected.
        """
        injected: list[str] = []
        for spec in schedule.due_at(now_sec):
            method = spec.target.split(".")[-1] if "." in spec.target else spec.target
            comp_name = spec.target.split(".")[0] if "." in spec.target else None
            obj = self._components.get(comp_name) if comp_name else None
            if obj is not None and hasattr(obj, method):
                result = self._injector.apply(obj, method, spec.fault_type, spec.params)
                if result is not None:
                    injected.append(f"{spec.fault_type.name}@{spec.target}")
            else:
                # Record the fault in the tracker even without a live target.
                self._injector._injector.inject_fault(spec.fault_type, spec.target, spec.params)
                injected.append(f"{spec.fault_type.name}@{spec.target}")
        return injected

    # -- run ---------------------------------------------------------------
    def run(
        self,
        schedule: FaultSchedule | None = None,
        trials: int = 10,
        seed: int | None = None,
        now_sec: float = 0.0,
    ) -> ChaosRunReport:
        """Run ``trials`` trials and return a :class:`ChaosRunReport`."""
        if self._scenario is None:
            raise ValueError("no scenario set; call set_scenario() first")

        report = ChaosRunReport(
            experiment_name=self.name,
            total_trials=trials,
            passed=0,
            failed=0,
            start_time=time.time(),
        )

        for trial in range(trials):
            self._injector.restore_all()
            trial_seed: int | None = None
            if seed is not None:
                trial_seed = random.Random(seed).randint(0, 2**31 - 1)

            faults_injected: list[str] = []
            if schedule is not None:
                faults_injected = self.inject_schedule(schedule, now_sec=now_sec)

            violations: list[str] = []
            error: str | None = None
            start = time.perf_counter()
            try:
                self._scenario(self._injector, self._components)
                for probe in self._probes:
                    violations.extend(probe(self._injector, self._components))
            except Exception as exc:  # noqa: BLE001 - capture fault-exercise failures
                error = f"{type(exc).__name__}: {exc}"
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            passed = (not error) and (not violations)
            result = TrialResult(
                trial_id=trial,
                faults_injected=faults_injected,
                passed=passed,
                violations=violations,
                duration_ms=elapsed_ms,
                error=error,
            )
            report.results.append(result)
            if passed:
                report.passed += 1
            else:
                report.failed += 1

        report.end_time = time.time()
        self._injector.restore_all()
        return report

    @property
    def injector(self) -> RuntimeFaultInjector:
        return self._injector
