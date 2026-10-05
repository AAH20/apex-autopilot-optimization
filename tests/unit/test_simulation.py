"""Tests for simulation integration package."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apex_autopilot_optimization.simulation import (
    SimulationConfig,
    SimulationInterface,
    SimulationResult,
    SimulationRunner,
)
from apex_autopilot_optimization.simulation.interface import SimulationBackend


class TestSimulationInterface:
    """Tests for SimulationInterface ABC enforcement."""

    def test_cannot_instantiate_abc(self) -> None:
        """SimulationInterface is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            SimulationInterface()  # type: ignore[abstract]

    def test_abstract_methods_defined(self) -> None:
        """SimulationInterface defines all required abstract methods."""
        expected = {
            "connect",
            "disconnect",
            "get_state",
            "send_control",
            "arm",
            "set_mode",
            "reset",
            "step",
        }
        actual = set(SimulationInterface.__abstractmethods__)
        assert expected.issubset(actual)

    def test_is_connected_is_property(self) -> None:
        """is_connected is a property on the interface."""
        assert isinstance(SimulationInterface.__dict__["is_connected"], property)

    def test_time_scale_is_property(self) -> None:
        """time_scale is a property on the interface."""
        assert isinstance(SimulationInterface.__dict__["time_scale"], property)

    def test_partial_subclass_still_abstract(self) -> None:
        """A subclass missing some abstract methods remains abstract."""

        class PartialSim(SimulationInterface):
            def connect(self, connection_string: str) -> bool:
                return True

            def disconnect(self) -> bool:
                return True

        with pytest.raises(TypeError):
            PartialSim()  # type: ignore[abstract]

    def test_full_subclass_instantiable(self) -> None:
        """A complete subclass can be instantiated."""

        class CompleteSim(SimulationInterface):
            def connect(self, connection_string: str) -> bool:
                return True

            def disconnect(self) -> bool:
                return True

            def get_state(self):
                return None

            def send_control(self, control) -> bool:
                return True

            def arm(self) -> bool:
                return True

            def set_mode(self, mode: str) -> bool:
                return True

            def reset(self) -> bool:
                return True

            def step(self, dt: float) -> bool:
                return True

            @property
            def is_connected(self) -> bool:
                return True

            @property
            def time_scale(self) -> float:
                return 1.0

        sim = CompleteSim()
        assert sim.is_connected is True
        assert sim.time_scale == 1.0


class TestSimulationConfig:
    """Tests for SimulationConfig dataclass."""

    def test_creation_with_all_fields(self) -> None:
        config = SimulationConfig(
            backend="gazebo",
            connection_string="localhost:11345",
            lockstep=True,
            time_scale=2.0,
            vehicle_type="multirotor",
            model="iris",
        )
        assert config.backend == "gazebo"
        assert config.connection_string == "localhost:11345"
        assert config.lockstep is True
        assert config.time_scale == 2.0
        assert config.vehicle_type == "multirotor"
        assert config.model == "iris"

    def test_creation_with_defaults(self) -> None:
        config = SimulationConfig()
        assert config.backend == ""
        assert config.connection_string == ""
        assert config.lockstep is False
        assert config.time_scale == 1.0
        assert config.vehicle_type == ""
        assert config.model == ""

    def test_creation_partial(self) -> None:
        config = SimulationConfig(backend="airsim", time_scale=0.5)
        assert config.backend == "airsim"
        assert config.time_scale == 0.5
        assert config.lockstep is False


class TestSimulationResult:
    """Tests for SimulationResult dataclass."""

    def test_creation_with_all_fields(self) -> None:
        result = SimulationResult(
            success=True,
            trajectory=[1.0, 2.0, 3.0],
            metrics={"distance": 10.0},
            duration_seconds=5.5,
            message="Mission complete",
        )
        assert result.success is True
        assert result.trajectory == [1.0, 2.0, 3.0]
        assert result.metrics == {"distance": 10.0}
        assert result.duration_seconds == 5.5
        assert result.message == "Mission complete"

    def test_creation_with_defaults(self) -> None:
        result = SimulationResult()
        assert result.success is False
        assert result.trajectory == []
        assert result.metrics == {}
        assert result.duration_seconds == 0.0
        assert result.message == ""

    def test_creation_failure_result(self) -> None:
        result = SimulationResult(
            success=False,
            message="Connection failed",
        )
        assert result.success is False
        assert result.message == "Connection failed"


class TestSimulationRunner:
    """Tests for SimulationRunner mission execution (mocked)."""

    def _make_config(self) -> SimulationConfig:
        return SimulationConfig(
            backend="mock",
            connection_string="mock://test",
            lockstep=False,
            time_scale=1.0,
            vehicle_type="multirotor",
            model="test_model",
        )

    def test_run_mission_success(self) -> None:
        """run_mission returns a SimulationResult on success."""
        runner = SimulationRunner()
        config = self._make_config()

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = True
        mock_sim.disconnect.return_value = True
        mock_sim.arm.return_value = True
        mock_sim.set_mode.return_value = True
        mock_sim.step.return_value = True
        mock_sim.get_state.return_value = MagicMock()
        mock_sim.send_control.return_value = True
        mock_sim.is_connected = True
        mock_sim.time_scale = 1.0

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            return_value=mock_sim,
        ):
            result = runner.run_mission(
                problem=MagicMock(),
                planner=MagicMock(),
                optimizer=MagicMock(),
                safety=MagicMock(),
                controller=MagicMock(),
                estimator=MagicMock(),
                config=config,
            )

        assert isinstance(result, SimulationResult)
        assert result.success is True
        mock_sim.connect.assert_called_once_with("mock://test")
        mock_sim.disconnect.assert_called_once()

    def test_run_mission_connect_failure(self) -> None:
        """run_mission returns failure result when connect fails."""
        runner = SimulationRunner()
        config = self._make_config()

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = False
        mock_sim.is_connected = False

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            return_value=mock_sim,
        ):
            result = runner.run_mission(
                problem=MagicMock(),
                planner=MagicMock(),
                optimizer=MagicMock(),
                safety=MagicMock(),
                controller=MagicMock(),
                estimator=MagicMock(),
                config=config,
            )

        assert isinstance(result, SimulationResult)
        assert result.success is False
        assert "connect" in result.message.lower()

    def test_run_mission_disconnects_on_failure(self) -> None:
        """run_mission always disconnects even on failure."""
        runner = SimulationRunner()
        config = self._make_config()

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = True
        mock_sim.arm.return_value = True
        mock_sim.set_mode.return_value = True
        mock_sim.step.return_value = False
        mock_sim.is_connected = True
        mock_sim.disconnect.return_value = True

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            return_value=mock_sim,
        ):
            result = runner.run_mission(
                problem=MagicMock(),
                planner=MagicMock(),
                optimizer=MagicMock(),
                safety=MagicMock(),
                controller=MagicMock(),
                estimator=MagicMock(),
                config=config,
            )

        assert result.success is False
        mock_sim.disconnect.assert_called_once()

    def test_run_mission_passes_time_scale(self) -> None:
        """run_mission sets time_scale on the simulation."""
        runner = SimulationRunner()
        config = self._make_config()
        config.time_scale = 3.0

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = True
        mock_sim.arm.return_value = True
        mock_sim.set_mode.return_value = True
        mock_sim.step.return_value = True
        mock_sim.is_connected = True
        mock_sim.time_scale = 1.0

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            return_value=mock_sim,
        ):
            runner.run_mission(
                problem=MagicMock(),
                planner=MagicMock(),
                optimizer=MagicMock(),
                safety=MagicMock(),
                controller=MagicMock(),
                estimator=MagicMock(),
                config=config,
            )

        assert mock_sim.time_scale == 3.0

    def test_run_batch_success(self) -> None:
        """run_batch executes multiple missions."""
        runner = SimulationRunner()
        config = self._make_config()

        problems = [MagicMock(), MagicMock(), MagicMock()]

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = True
        mock_sim.arm.return_value = True
        mock_sim.set_mode.return_value = True
        mock_sim.step.return_value = True
        mock_sim.is_connected = True
        mock_sim.time_scale = 1.0

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            return_value=mock_sim,
        ):
            results = runner.run_batch(problems, config)

        assert len(results) == 3
        assert all(isinstance(r, SimulationResult) for r in results)
        assert all(r.success for r in results)

    def test_run_batch_empty(self) -> None:
        """run_batch with empty list returns empty results."""
        runner = SimulationRunner()
        config = self._make_config()

        results = runner.run_batch([], config)
        assert results == []

    def test_run_batch_partial_failure(self) -> None:
        """run_batch continues after individual mission failures."""
        runner = SimulationRunner()
        config = self._make_config()

        problems = [MagicMock(), MagicMock()]

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = True
        mock_sim.arm.return_value = True
        mock_sim.set_mode.return_value = True
        mock_sim.step.return_value = True
        mock_sim.is_connected = True
        mock_sim.time_scale = 1.0

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_sim.connect.return_value = False
            else:
                mock_sim.connect.return_value = True
            return mock_sim

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            side_effect=side_effect,
        ):
            results = runner.run_batch(problems, config)

        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is True

    def test_get_runner_stats_initial(self) -> None:
        """get_runner_stats returns zeroed stats for a fresh runner."""
        runner = SimulationRunner()
        stats = runner.get_runner_stats()
        assert stats["total_missions"] == 0
        assert stats["successful_missions"] == 0
        assert stats["failed_missions"] == 0
        assert stats["total_duration_seconds"] == 0.0

    def test_get_runner_stats_after_missions(self) -> None:
        """get_runner_stats reflects completed missions."""
        runner = SimulationRunner()
        config = self._make_config()

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = True
        mock_sim.arm.return_value = True
        mock_sim.set_mode.return_value = True
        mock_sim.step.return_value = True
        mock_sim.is_connected = True
        mock_sim.time_scale = 1.0

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            return_value=mock_sim,
        ):
            runner.run_mission(
                problem=MagicMock(),
                planner=MagicMock(),
                optimizer=MagicMock(),
                safety=MagicMock(),
                controller=MagicMock(),
                estimator=MagicMock(),
                config=config,
            )
            runner.run_mission(
                problem=MagicMock(),
                planner=MagicMock(),
                optimizer=MagicMock(),
                safety=MagicMock(),
                controller=MagicMock(),
                estimator=MagicMock(),
                config=config,
            )

        stats = runner.get_runner_stats()
        assert stats["total_missions"] == 2
        assert stats["successful_missions"] == 2
        assert stats["failed_missions"] == 0
        assert stats["total_duration_seconds"] > 0.0

    def test_get_runner_stats_after_batch(self) -> None:
        """get_runner_stats reflects batch missions."""
        runner = SimulationRunner()
        config = self._make_config()

        problems = [MagicMock(), MagicMock(), MagicMock()]

        mock_sim = MagicMock(spec=SimulationInterface)
        mock_sim.connect.return_value = True
        mock_sim.arm.return_value = True
        mock_sim.set_mode.return_value = True
        mock_sim.step.return_value = True
        mock_sim.is_connected = True
        mock_sim.time_scale = 1.0

        with patch(
            "apex_autopilot_optimization.simulation.runner.SimulationInterface",
            return_value=mock_sim,
        ):
            runner.run_batch(problems, config)

        stats = runner.get_runner_stats()
        assert stats["total_missions"] == 3
        assert stats["successful_missions"] == 3


class TestSimulationBackend:
    """Tests for SimulationBackend enumeration."""

    def test_backend_enum_exists(self) -> None:
        """SimulationBackend enum is importable."""
        assert SimulationBackend is not None

    def test_backend_has_expected_members(self) -> None:
        """SimulationBackend has expected backend names."""
        names = {b.name for b in SimulationBackend}
        assert "GAZEBO" in names
        assert "AIRSIM" in names
        assert "JMASIM" in names

    def test_backend_values_unique(self) -> None:
        """SimulationBackend values are unique."""
        values = [b.value for b in SimulationBackend]
        assert len(values) == len(set(values))

    def test_backend_is_enum(self) -> None:
        """SimulationBackend is an Enum."""
        from enum import Enum

        assert issubclass(SimulationBackend, Enum)
