"""Pipeline for chaining algorithm stages in autopilot optimization."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from apex_autopilot_optimization.core.types import (
    ControlInput,
    PlanningProblem,
    PlanningResult,
    StateVector,
)
from apex_autopilot_optimization.safety.cbf import CBFFilter

T = TypeVar("T")
U = TypeVar("U")


class PipelineStage(ABC, Generic[T, U]):
    """Abstract base class for a pipeline stage.

    Each stage has a name and a run(input) -> output method.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def run(self, input_data: T) -> U:
        """Execute this stage and return the result."""
        ...


class Pipeline:
    """Chains multiple pipeline stages together.

    Executes stages in order, passing each stage's output as the next
    stage's input. Tracks execution time per stage.
    """

    def __init__(self, stages: list[PipelineStage[Any, Any]] | None = None) -> None:
        self.stages: list[PipelineStage[Any, Any]] = list(stages) if stages is not None else []
        self.stage_execution_times: dict[str, float] = {}

    def add_stage(self, stage: PipelineStage[Any, Any]) -> None:
        """Add a stage to the end of the pipeline."""
        self.stages.append(stage)

    def run(self, input_data: Any) -> Any:
        """Execute all stages in order and return the final result."""
        result = input_data
        self.stage_execution_times.clear()
        for stage in self.stages:
            start_time = time.perf_counter()
            result = stage.run(result)
            elapsed = time.perf_counter() - start_time
            self.stage_execution_times[stage.name] = elapsed
        return result


class PlanningStage(PipelineStage[PlanningProblem, PlanningResult]):
    """Pipeline stage that wraps a planner."""

    def __init__(self, planner: Any, name: str = "planning") -> None:
        super().__init__(name)
        self.planner = planner

    def run(self, input_data: PlanningProblem) -> PlanningResult:
        return self.planner.plan(input_data)


class OptimizationStage(PipelineStage[PlanningProblem, PlanningResult]):
    """Pipeline stage that wraps an optimizer."""

    def __init__(self, optimizer: Any, name: str = "optimization") -> None:
        super().__init__(name)
        self.optimizer = optimizer

    def run(self, input_data: PlanningProblem) -> PlanningResult:
        return self.optimizer.optimize(input_data)


class SafetyStage(PipelineStage[tuple[StateVector, ControlInput, list[dict]], ControlInput]):
    """Pipeline stage that wraps a CBF safety filter."""

    def __init__(self, cbf_filter: CBFFilter, name: str = "safety") -> None:
        super().__init__(name)
        self.cbf_filter = cbf_filter

    def run(self, input_data: tuple[StateVector, ControlInput, list[dict]]) -> ControlInput:
        state, control, obstacles = input_data
        return self.cbf_filter.filter(state, control, obstacles)
