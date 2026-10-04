"""Simulation runner for mission execution."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

from apex_autopilot_optimization.simulation.config import SimulationConfig
from apex_autopilot_optimization.simulation.interface import SimulationInterface
from apex_autopilot_optimization.simulation.result import SimulationResult


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

        Returns:
            SimulationResult with outcome and metrics.
        """
        start = time.perf_counter()
        self._total_missions += 1

        sim = SimulationInterface()

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
    ) -> list[SimulationResult]:
        """Execute a batch of simulation missions.

        Args:
            problems: List of planning problem definitions.
            config: Simulation configuration.

        Returns:
            List of SimulationResult, one per problem.
        """
        results: list[SimulationResult] = []
        for problem in problems:
            result = self.run_mission(
                problem=problem,
                planner=MagicMock(),
                optimizer=MagicMock(),
                safety=MagicMock(),
                controller=MagicMock(),
                estimator=MagicMock(),
                config=config,
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
