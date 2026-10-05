"""Simulation runner for mission execution."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from apex_autopilot_optimization.simulation.config import SimulationConfig
from apex_autopilot_optimization.simulation.interface import SimulationInterface
from apex_autopilot_optimization.simulation.result import SimulationResult


class _NoOpPlanner:
    """Fallback planner used when no components are supplied to run_batch.

    Returns ``None`` so the mission loop terminates immediately, making a
    component-free batch run a backend connectivity smoke test.
    """

    def plan(self, problem: Any, state: Any) -> Any:
        return None


class _NoOpController:
    """Fallback controller that produces no control input."""

    def compute_control(self, state: Any, plan: Any) -> Any:
        return None


class _NoOpSafetyFilter:
    """Fallback safety filter that passes control through unchanged."""

    def filter(self, state: Any, control: Any, obstacles: Any) -> Any:
        return control


class _NoOpOptimizer:
    """Fallback optimizer that performs no optimization."""

    def optimize(self, *args: Any, **kwargs: Any) -> Any:
        return None


class _NoOpEstimator:
    """Fallback state estimator that performs no estimation."""

    def estimate(self, *args: Any, **kwargs: Any) -> Any:
        return None


def _default_components() -> dict[str, Any]:
    """Build the default no-op component set for component-free batch runs."""
    return {
        "planner": _NoOpPlanner(),
        "optimizer": _NoOpOptimizer(),
        "safety": _NoOpSafetyFilter(),
        "controller": _NoOpController(),
        "estimator": _NoOpEstimator(),
    }


class SimulationRunner:
    """Executes simulation missions using a SimulationInterface backend.

    Orchestrates the full mission loop: connect, arm, plan, control,
    safety-check, step, and disconnect. Tracks statistics across runs.
    """

    def __init__(self) -> None:
        self._total_missions: int = 0
        self._successful_missions: int = 0
        self._failed_missions: int = 0
        self._total_duration_seconds: float = 0.0

    def run_mission(
        self,
        problem: Any,
        planner: Any,
        optimizer: Any,
        safety: Any,
        controller: Any,
        estimator: Any,
        config: SimulationConfig,
        sim_factory: Callable[[], SimulationInterface] | None = None,
    ) -> SimulationResult:
        """Execute a single simulation mission.

        Args:
            problem: The planning problem definition.
            planner: Path/trajectory planner instance.
            optimizer: Trajectory optimizer instance.
            safety: Safety filter instance.
            controller: Controller instance.
            estimator: State estimator instance.
            config: Simulation configuration.
            sim_factory: Optional factory returning a concrete
                SimulationInterface implementation. When ``None``, the
                module-level ``SimulationInterface`` symbol is used, which
                production callers can monkeypatch or replace with a
                backend-specific factory (e.g. Gazebo, AirSim).

        Returns:
            SimulationResult with outcome and metrics.
        """
        start = time.perf_counter()
        self._total_missions += 1

        sim = (sim_factory or SimulationInterface)()

        try:
            if not sim.connect(config.connection_string):
                self._failed_missions += 1
                return SimulationResult(
                    success=False,
                    message=f"Failed to connect to {config.connection_string}",
                )

            sim.time_scale = config.time_scale

            if not sim.arm():
                self._failed_missions += 1
                return SimulationResult(
                    success=False,
                    message="Failed to arm vehicle",
                )

            if not sim.set_mode("GUIDED"):
                self._failed_missions += 1
                return SimulationResult(
                    success=False,
                    message="Failed to set GUIDED mode",
                )

            trajectory: list[Any] = []
            dt = 0.05
            max_steps = 1000

            for _ in range(max_steps):
                state = sim.get_state()
                if state is None:
                    break

                trajectory.append(state)

                plan = planner.plan(problem, state)
                if plan is None:
                    break

                control = controller.compute_control(state, plan)
                filtered = safety.filter(state, control, [])

                if not sim.send_control(filtered):
                    self._failed_missions += 1
                    return SimulationResult(
                        success=False,
                        trajectory=trajectory,
                        message="Failed to send control",
                    )

                if not sim.step(dt):
                    self._failed_missions += 1
                    return SimulationResult(
                        success=False,
                        trajectory=trajectory,
                        message="Simulation step failed",
                    )

            duration = time.perf_counter() - start
            self._total_duration_seconds += duration
            self._successful_missions += 1

            return SimulationResult(
                success=True,
                trajectory=trajectory,
                metrics={"steps": len(trajectory)},
                duration_seconds=duration,
                message="Mission completed successfully",
            )

        finally:
            sim.disconnect()

    def run_batch(
        self,
        problems: list[Any],
        config: SimulationConfig,
        sim_factory: Callable[[], SimulationInterface] | None = None,
        **components: Any,
    ) -> list[SimulationResult]:
        """Execute a batch of simulation missions.

        Args:
            problems: List of planning problem definitions.
            config: Simulation configuration.
            sim_factory: Optional factory returning a concrete
                SimulationInterface implementation (see run_mission).
            **components: Optional planner/optimizer/safety/controller/
                estimator instances. When omitted, no-op fallbacks are used,
                making the batch run a backend connectivity smoke test.

        Returns:
            List of SimulationResult, one per problem.
        """
        factory = sim_factory or SimulationInterface
        comps = _default_components()
        comps.update(components)

        results: list[SimulationResult] = []
        for problem in problems:
            result = self.run_mission(
                problem=problem,
                planner=comps["planner"],
                optimizer=comps["optimizer"],
                safety=comps["safety"],
                controller=comps["controller"],
                estimator=comps["estimator"],
                config=config,
                sim_factory=factory,
            )
            results.append(result)
        return results

    def get_runner_stats(self) -> dict[str, Any]:
        """Get cumulative runner statistics.

        Returns:
            Dictionary with total_missions, successful_missions,
            failed_missions, and total_duration_seconds.
        """
        return {
            "total_missions": self._total_missions,
            "successful_missions": self._successful_missions,
            "failed_missions": self._failed_missions,
            "total_duration_seconds": self._total_duration_seconds,
        }
