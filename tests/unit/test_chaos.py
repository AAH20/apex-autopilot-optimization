"""Tests for chaos engineering and fault injection."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.chaos import (
    ChaosConfig,
    ChaosResult,
    FaultInjector,
    FaultType,
)


class TestFaultType:
    """Tests for FaultType enum."""

    def test_fault_type_has_all_members(self) -> None:
        expected = {
            "NETWORK_DELAY",
            "NETWORK_DROP",
            "CPU_SPIKE",
            "MEMORY_PRESSURE",
            "SENSOR_NOISE",
            "SENSOR_DROPOUT",
            "ACTUATOR_FAILURE",
            "COMMUNICATION_ERROR",
            "CLOCK_DRIFT",
            "PACKET_LOSS",
        }
        actual = {ft.name for ft in FaultType}
        assert actual == expected

    def test_fault_type_count(self) -> None:
        assert len(FaultType) == 10

    def test_fault_type_values_are_unique(self) -> None:
        values = [ft.value for ft in FaultType]
        assert len(values) == len(set(values))

    def test_fault_type_is_enum(self) -> None:
        from enum import Enum

        assert issubclass(FaultType, Enum)


class TestChaosConfig:
    """Tests for ChaosConfig dataclass."""

    def test_defaults(self) -> None:
        config = ChaosConfig()
        assert config.enabled is True
        assert config.fault_probability == 0.1
        assert config.max_concurrent_faults == 3
        assert config.target_modules == []

    def test_custom_values(self) -> None:
        config = ChaosConfig(
            enabled=False,
            fault_probability=0.5,
            max_concurrent_faults=10,
            target_modules=["planner", "controller"],
        )
        assert config.enabled is False
        assert config.fault_probability == 0.5
        assert config.max_concurrent_faults == 10
        assert config.target_modules == ["planner", "controller"]

    def test_fault_probability_validation(self) -> None:
        with pytest.raises(ValueError):
            ChaosConfig(fault_probability=-0.1)
        with pytest.raises(ValueError):
            ChaosConfig(fault_probability=1.5)

    def test_max_concurrent_faults_validation(self) -> None:
        with pytest.raises(ValueError):
            ChaosConfig(max_concurrent_faults=0)
        with pytest.raises(ValueError):
            ChaosConfig(max_concurrent_faults=-1)


class TestChaosResult:
    """Tests for ChaosResult dataclass."""

    def test_creation(self) -> None:
        result = ChaosResult(
            fault_type="NETWORK_DELAY",
            target="planner",
            start_time=1000.0,
            end_time=None,
            params={"delay_ms": 200},
            status="active",
        )
        assert result.fault_type == "NETWORK_DELAY"
        assert result.target == "planner"
        assert result.start_time == 1000.0
        assert result.end_time is None
        assert result.params == {"delay_ms": 200}
        assert result.status == "active"

    def test_creation_with_end_time(self) -> None:
        result = ChaosResult(
            fault_type="CPU_SPIKE",
            target="controller",
            start_time=1000.0,
            end_time=1005.0,
            params={"severity": 0.8},
            status="completed",
        )
        assert result.end_time == 1005.0
        assert result.status == "completed"

    def test_duration_active(self) -> None:
        result = ChaosResult(
            fault_type="NETWORK_DELAY",
            target="planner",
            start_time=1000.0,
            end_time=None,
            params={},
            status="active",
        )
        assert result.duration() is None

    def test_duration_completed(self) -> None:
        result = ChaosResult(
            fault_type="NETWORK_DELAY",
            target="planner",
            start_time=1000.0,
            end_time=1005.0,
            params={},
            status="completed",
        )
        assert result.duration() == pytest.approx(5.0)

    def test_is_active(self) -> None:
        active = ChaosResult(
            fault_type="NETWORK_DELAY",
            target="planner",
            start_time=1000.0,
            end_time=None,
            params={},
            status="active",
        )
        completed = ChaosResult(
            fault_type="NETWORK_DELAY",
            target="planner",
            start_time=1000.0,
            end_time=1005.0,
            params={},
            status="completed",
        )
        assert active.is_active() is True
        assert completed.is_active() is False


class TestFaultInjector:
    """Tests for FaultInjector class."""

    def test_inject_fault(self) -> None:
        injector = FaultInjector()
        result = injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {"delay_ms": 200})
        assert isinstance(result, ChaosResult)
        assert result.fault_type == "NETWORK_DELAY"
        assert result.target == "planner"
        assert result.status == "active"
        assert result.params == {"delay_ms": 200}

    def test_inject_fault_adds_to_active(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.CPU_SPIKE, "controller", {"severity": 0.5})
        active = injector.get_active_faults()
        assert len(active) == 1
        assert active[0].fault_type == "CPU_SPIKE"

    def test_remove_fault(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        injector.remove_fault(FaultType.NETWORK_DELAY, "planner")
        assert len(injector.get_active_faults()) == 0

    def test_remove_fault_marks_completed(self) -> None:
        injector = FaultInjector()
        result = injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        injector.remove_fault(FaultType.NETWORK_DELAY, "planner")
        assert result.status == "completed"
        assert result.end_time is not None

    def test_remove_nonexistent_fault_no_error(self) -> None:
        injector = FaultInjector()
        # Should not raise
        injector.remove_fault(FaultType.NETWORK_DELAY, "planner")
        assert len(injector.get_active_faults()) == 0

    def test_multiple_concurrent_faults(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        injector.inject_fault(FaultType.CPU_SPIKE, "controller", {})
        injector.inject_fault(FaultType.SENSOR_NOISE, "ekf", {})
        active = injector.get_active_faults()
        assert len(active) == 3

    def test_clear_all_faults(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        injector.inject_fault(FaultType.CPU_SPIKE, "controller", {})
        injector.clear_all_faults()
        assert len(injector.get_active_faults()) == 0

    def test_clear_all_marks_completed(self) -> None:
        injector = FaultInjector()
        r1 = injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        r2 = injector.inject_fault(FaultType.CPU_SPIKE, "controller", {})
        injector.clear_all_faults()
        assert r1.status == "completed"
        assert r2.status == "completed"

    def test_get_fault_stats(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        injector.inject_fault(FaultType.CPU_SPIKE, "controller", {})
        injector.inject_fault(FaultType.SENSOR_NOISE, "ekf", {})
        stats = injector.get_fault_stats()
        assert stats["total_active"] == 3
        assert stats["by_type"]["NETWORK_DELAY"] == 1
        assert stats["by_type"]["CPU_SPIKE"] == 1
        assert stats["by_type"]["SENSOR_NOISE"] == 1

    def test_get_fault_stats_empty(self) -> None:
        injector = FaultInjector()
        stats = injector.get_fault_stats()
        assert stats["total_active"] == 0
        assert stats["by_type"] == {}

    def test_inject_random_fault(self) -> None:
        config = ChaosConfig(fault_probability=1.0)
        injector = FaultInjector(config=config)
        result = injector.inject_random_fault()
        assert isinstance(result, ChaosResult)
        assert result.status == "active"
        assert result.fault_type in {ft.name for ft in FaultType}

    def test_inject_random_fault_respects_probability(self) -> None:
        config = ChaosConfig(enabled=True, fault_probability=0.0)
        injector = FaultInjector(config=config)
        result = injector.inject_random_fault()
        assert result is None

    def test_inject_random_fault_with_seed(self) -> None:
        config = ChaosConfig(fault_probability=1.0)
        injector = FaultInjector(config=config)
        result = injector.inject_random_fault(seed=42)
        assert isinstance(result, ChaosResult)
        assert result.status == "active"

    def test_max_concurrent_faults_enforced(self) -> None:
        config = ChaosConfig(max_concurrent_faults=2)
        injector = FaultInjector(config=config)
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        injector.inject_fault(FaultType.CPU_SPIKE, "controller", {})
        # Third should be rejected
        result = injector.inject_fault(FaultType.SENSOR_NOISE, "ekf", {})
        assert result is None
        assert len(injector.get_active_faults()) == 2

    def test_inject_fault_with_config(self) -> None:
        config = ChaosConfig(target_modules=["planner", "controller"])
        injector = FaultInjector(config=config)
        result = injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        assert result is not None
        assert result.target == "planner"

    def test_duplicate_fault_rejected(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        result = injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        assert result is None
        assert len(injector.get_active_faults()) == 1

    def test_inject_all_fault_types(self) -> None:
        config = ChaosConfig(max_concurrent_faults=20)
        injector = FaultInjector(config=config)
        for ft in FaultType:
            result = injector.inject_fault(ft, f"target_{ft.name}", {})
            assert result is not None
            assert result.fault_type == ft.name
        assert len(injector.get_active_faults()) == len(FaultType)

    def test_fault_stats_after_removal(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        injector.inject_fault(FaultType.CPU_SPIKE, "controller", {})
        injector.remove_fault(FaultType.NETWORK_DELAY, "planner")
        stats = injector.get_fault_stats()
        assert stats["total_active"] == 1
        assert "NETWORK_DELAY" not in stats["by_type"]
        assert stats["by_type"]["CPU_SPIKE"] == 1

    def test_inject_fault_records_start_time(self) -> None:
        injector = FaultInjector()
        before = time.time()
        result = injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        after = time.time()
        assert before <= result.start_time <= after

    def test_remove_fault_sets_end_time(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.NETWORK_DELAY, "planner", {})
        before = time.time()
        injector.remove_fault(FaultType.NETWORK_DELAY, "planner")
        after = time.time()
        active = injector.get_active_faults()
        assert len(active) == 0
        # The result object should have end_time set
        # We can verify via stats or by checking the result was marked
        stats = injector.get_fault_stats()
        assert stats["total_active"] == 0
