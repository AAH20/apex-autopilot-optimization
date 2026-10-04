"""Tests for Pipeline, PipelineStage, and concrete stage implementations."""

from __future__ import annotations

from typing import cast

import pytest

from apex_autopilot_optimization.core.types import (
    ControlInput,
    PlanningProblem,
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.pipeline import (
    OptimizationStage,
    Pipeline,
    PipelineStage,
    PlanningStage,
    SafetyStage,
)
from apex_autopilot_optimization.safety.cbf import CBFFilter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyPlanner:
    """Minimal planner stub for testing."""

    def __init__(self, result: str = "planned") -> None:
        self.result = result
        self.call_count = 0

    def plan(self, problem: object) -> str:
        self.call_count += 1
        return self.result


class _DummyOptimizer:
    """Minimal optimizer stub for testing."""

    def __init__(self, result: str = "optimized") -> None:
        self.result = result
        self.call_count = 0

    def optimize(self, problem: object) -> str:
        self.call_count += 1
        return self.result


class _EchoStage(PipelineStage[str, str]):
    """Simple stage that echoes its input with a prefix."""

    def __init__(self, name: str, prefix: str = "") -> None:
        super().__init__(name)
        self.prefix = prefix

    def run(self, input_data: str) -> str:
        return f"{self.prefix}{input_data}"


class _FailStage(PipelineStage[str, str]):
    """Stage that always raises an error."""

    def run(self, input_data: str) -> str:
        raise RuntimeError("stage failure")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmptyPipeline:
    """Tests for an empty pipeline."""

    def test_run_returns_input_unchanged(self) -> None:
        pipeline = Pipeline()
        result = pipeline.run("hello")
        assert result == "hello"

    def test_no_stages(self) -> None:
        pipeline = Pipeline()
        assert len(pipeline.stages) == 0

    def test_no_execution_times(self) -> None:
        pipeline = Pipeline()
        pipeline.run("test")
        assert pipeline.stage_execution_times == {}


class TestSingleStage:
    """Tests for a pipeline with one stage."""

    def test_single_stage_output(self) -> None:
        stage = _EchoStage("echo", prefix=">>")
        pipeline = Pipeline([stage])
        result = pipeline.run("data")
        assert result == ">>data"

    def test_single_stage_execution_time_recorded(self) -> None:
        stage = _EchoStage("echo")
        pipeline = Pipeline([stage])
        pipeline.run("x")
        assert "echo" in pipeline.stage_execution_times
        assert pipeline.stage_execution_times["echo"] >= 0.0


class TestMultiStageChain:
    """Tests for chaining multiple stages."""

    def test_two_stages_chain(self) -> None:
        s1 = _EchoStage("first", prefix="A:")
        s2 = _EchoStage("second", prefix="B:")
        pipeline = Pipeline([s1, s2])
        result = pipeline.run("input")
        assert result == "B:A:input"

    def test_three_stages_chain(self) -> None:
        s1 = _EchoStage("s1", prefix="1:")
        s2 = _EchoStage("s2", prefix="2:")
        s3 = _EchoStage("s3", prefix="3:")
        pipeline = Pipeline([s1, s2, s3])
        result = pipeline.run("x")
        assert result == "3:2:1:x"

    def test_all_execution_times_recorded(self) -> None:
        s1 = _EchoStage("alpha")
        s2 = _EchoStage("beta")
        s3 = _EchoStage("gamma")
        pipeline = Pipeline([s1, s2, s3])
        pipeline.run("x")
        assert set(pipeline.stage_execution_times.keys()) == {"alpha", "beta", "gamma"}
        for t in pipeline.stage_execution_times.values():
            assert t >= 0.0

    def test_add_stage_method(self) -> None:
        pipeline = Pipeline()
        pipeline.add_stage(_EchoStage("a", prefix="A:"))
        pipeline.add_stage(_EchoStage("b", prefix="B:"))
        result = pipeline.run("x")
        assert result == "B:A:x"

    def test_stage_order_preserved(self) -> None:
        order: list[str] = []

        class _OrderStage(PipelineStage[str, str]):
            def __init__(self, name: str) -> None:
                super().__init__(name)

            def run(self, input_data: str) -> str:
                order.append(self.name)
                return input_data

        pipeline = Pipeline([_OrderStage("first"), _OrderStage("second"), _OrderStage("third")])
        pipeline.run("x")
        assert order == ["first", "second", "third"]


class TestErrorHandling:
    """Tests for error propagation in pipeline stages."""

    def test_error_propagates(self) -> None:
        pipeline = Pipeline([_EchoStage("ok"), _FailStage("fail")])
        with pytest.raises(RuntimeError, match="stage failure"):
            pipeline.run("x")

    def test_error_in_first_stage(self) -> None:
        pipeline = Pipeline([_FailStage("fail"), _EchoStage("ok")])
        with pytest.raises(RuntimeError, match="stage failure"):
            pipeline.run("x")

    def test_execution_times_cleared_on_each_run(self) -> None:
        stage = _EchoStage("s")
        pipeline = Pipeline([stage])
        pipeline.run("a")
        assert "s" in pipeline.stage_execution_times
        pipeline.run("b")
        assert "s" in pipeline.stage_execution_times
        assert len(pipeline.stage_execution_times) == 1


class TestPlanningStage:
    """Tests for PlanningStage."""

    def test_wraps_planner(self) -> None:
        planner = _DummyPlanner(result="path")
        stage = PlanningStage(planner, name="plan")
        result = stage.run(cast(PlanningProblem, object()))
        assert result == "path"
        assert planner.call_count == 1

    def test_default_name(self) -> None:
        planner = _DummyPlanner()
        stage = PlanningStage(planner)
        assert stage.name == "planning"

    def test_custom_name(self) -> None:
        planner = _DummyPlanner()
        stage = PlanningStage(planner, name="my_planner")
        assert stage.name == "my_planner"


class TestOptimizationStage:
    """Tests for OptimizationStage."""

    def test_wraps_optimizer(self) -> None:
        optimizer = _DummyOptimizer(result="trajectory")
        stage = OptimizationStage(optimizer, name="opt")
        result = stage.run(cast(PlanningProblem, object()))
        assert result == "trajectory"
        assert optimizer.call_count == 1

    def test_default_name(self) -> None:
        optimizer = _DummyOptimizer()
        stage = OptimizationStage(optimizer)
        assert stage.name == "optimization"


class TestSafetyStage:
    """Tests for SafetyStage."""

    def test_wraps_cbf_filter(self) -> None:
        cbf = CBFFilter()
        stage = SafetyStage(cbf, name="safety_check")
        state = StateVector(pose=Pose3D(x=0, y=0, z=0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.5)
        obstacles: list[dict] = []
        result = stage.run((state, control, obstacles))
        assert isinstance(result, ControlInput)
        assert result.throttle == pytest.approx(0.5, abs=0.01)

    def test_default_name(self) -> None:
        cbf = CBFFilter()
        stage = SafetyStage(cbf)
        assert stage.name == "safety"

    def test_near_obstacle_correction(self) -> None:
        cbf = CBFFilter()
        stage = SafetyStage(cbf)
        state = StateVector(pose=Pose3D(x=1.0, y=0, z=0), velocity=Velocity3D(0, 0, 0))
        control = ControlInput(throttle=0.8)
        obstacles = [{"type": "sphere", "center": [2.0, 0, 0], "radius": 1.0}]
        result = stage.run((state, control, obstacles))
        assert result.throttle < 0.8


class TestPipelineStageAbstract:
    """Tests for PipelineStage abstract base class."""

    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            PipelineStage("test")  # type: ignore[abstract]

    def test_subclass_must_implement_run(self) -> None:
        class _Incomplete(PipelineStage[str, str]):
            pass

        with pytest.raises(TypeError):
            _Incomplete("bad")  # type: ignore[abstract]


class TestExecutionTimeTracking:
    """Tests for per-stage execution time tracking."""

    def test_times_are_non_negative(self) -> None:
        pipeline = Pipeline(
            [
                _EchoStage("a"),
                _EchoStage("b"),
                _EchoStage("c"),
            ]
        )
        pipeline.run("x")
        for name, t in pipeline.stage_execution_times.items():
            assert t >= 0.0, f"Negative time for stage {name}"

    def test_times_are_float(self) -> None:
        pipeline = Pipeline([_EchoStage("s")])
        pipeline.run("x")
        assert isinstance(pipeline.stage_execution_times["s"], float)

    def test_total_time_greater_than_zero(self) -> None:
        pipeline = Pipeline([_EchoStage("s")])
        pipeline.run("x")
        total = sum(pipeline.stage_execution_times.values())
        assert total > 0.0

    def test_times_accumulate_across_stages(self) -> None:
        pipeline = Pipeline([_EchoStage("a"), _EchoStage("b")])
        pipeline.run("x")
        total = sum(pipeline.stage_execution_times.values())
        assert total >= pipeline.stage_execution_times["a"]
        assert total >= pipeline.stage_execution_times["b"]
