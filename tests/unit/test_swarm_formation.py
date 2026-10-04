"""Tests for swarm formation control."""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.core.types import (
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.swarm.formation import (
    FormationConfig,
    FormationController,
)


class TestFormationConfig:
    """Tests for FormationConfig."""

    def test_defaults(self) -> None:
        config = FormationConfig()
        assert config.formation_type == "line"
        assert config.spacing == 2.0
        assert config.max_agents == 10

    def test_custom_values(self) -> None:
        config = FormationConfig(formation_type="wedge", spacing=3.0, max_agents=20)
        assert config.formation_type == "wedge"
        assert config.spacing == 3.0
        assert config.max_agents == 20


class TestFormationController:
    """Tests for FormationController."""

    def _make_state(self, x: float, y: float, z: float = 0) -> StateVector:
        return StateVector(
            pose=Pose3D(x=x, y=y, z=z),
            velocity=Velocity3D(0, 0, 0),
        )

    def test_compute_formation_positions_line(self) -> None:
        controller = FormationController()
        leader = self._make_state(0, 0, 0)
        positions = controller.compute_formation_positions(leader, 3)
        assert len(positions) == 3
        # Line formation: agents spaced behind leader (decreasing x)
        assert positions[0].x > positions[1].x > positions[2].x

    def test_compute_formation_positions_wedge(self) -> None:
        controller = FormationController(config=FormationConfig(formation_type="wedge"))
        leader = self._make_state(0, 0, 0)
        positions = controller.compute_formation_positions(leader, 3)
        assert len(positions) == 3

    def test_compute_formation_positions_single_agent(self) -> None:
        controller = FormationController()
        leader = self._make_state(0, 0, 0)
        positions = controller.compute_formation_positions(leader, 1)
        assert len(positions) == 1

    def test_compute_formation_positions_respects_spacing(self) -> None:
        controller = FormationController(config=FormationConfig(spacing=5.0))
        leader = self._make_state(0, 0, 0)
        positions = controller.compute_formation_positions(leader, 2)
        assert len(positions) == 2
        # Distance between agents should be approximately spacing
        dist = positions[0].distance_to(positions[1])
        assert dist == pytest.approx(5.0, abs=0.1)

    def test_compute_formation_positions_3d(self) -> None:
        controller = FormationController()
        leader = self._make_state(0, 0, 10)
        positions = controller.compute_formation_positions(leader, 3)
        assert len(positions) == 3
        # All agents should maintain same z as leader
        for pos in positions:
            assert pos.z == pytest.approx(10.0, abs=0.1)

    def test_compute_formation_positions_hexagon(self) -> None:
        controller = FormationController(config=FormationConfig(formation_type="hexagon"))
        leader = self._make_state(0, 0, 0)
        positions = controller.compute_formation_positions(leader, 6)
        assert len(positions) == 6

    def test_compute_formation_positions_large_formation(self) -> None:
        controller = FormationController()
        leader = self._make_state(0, 0, 0)
        positions = controller.compute_formation_positions(leader, 10)
        assert len(positions) == 10

    def test_compute_formation_positions_zero_agents(self) -> None:
        controller = FormationController()
        leader = self._make_state(0, 0, 0)
        positions = controller.compute_formation_positions(leader, 0)
        assert len(positions) == 0
