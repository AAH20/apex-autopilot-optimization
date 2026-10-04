"""Swarm formation control algorithms."""

from __future__ import annotations

import math
from dataclasses import dataclass

from apex_autopilot_optimization.core.types import (
    Pose3D,
    StateVector,
)


@dataclass(frozen=True, slots=True)
class FormationConfig:
    """Configuration for formation control."""

    formation_type: str = "line"
    spacing: float = 2.0
    max_agents: int = 10


class FormationController:
    """Formation controller for multi-agent systems.

    Computes target positions for agents in various formation patterns:
    line, wedge, hexagon.
    """

    def __init__(self, config: FormationConfig | None = None) -> None:
        self.config = config or FormationConfig()

    def compute_formation_positions(
        self,
        leader: StateVector,
        num_agents: int,
    ) -> list[Pose3D]:
        """Compute target positions for all agents in formation."""
        if num_agents <= 0:
            return []

        positions: list[Pose3D] = []

        if self.config.formation_type == "line":
            positions = self._line_formation(leader, num_agents)
        elif self.config.formation_type == "wedge":
            positions = self._wedge_formation(leader, num_agents)
        elif self.config.formation_type == "hexagon":
            positions = self._hexagon_formation(leader, num_agents)
        else:
            positions = self._line_formation(leader, num_agents)

        return positions

    def _line_formation(self, leader: StateVector, num_agents: int) -> list[Pose3D]:
        """Line formation: agents spaced along x-axis behind leader."""
        positions = []
        for i in range(num_agents):
            x = leader.pose.x - i * self.config.spacing
            y = leader.pose.y
            z = leader.pose.z
            positions.append(Pose3D(x=x, y=y, z=z))
        return positions

    def _wedge_formation(self, leader: StateVector, num_agents: int) -> list[Pose3D]:
        """Wedge formation: V-shape behind leader."""
        positions = []
        for i in range(num_agents):
            row = (i + 1) // 2
            side = 1 if i % 2 == 0 else -1
            x = leader.pose.x - row * self.config.spacing
            y = leader.pose.y + side * row * self.config.spacing * 0.5
            z = leader.pose.z
            positions.append(Pose3D(x=x, y=y, z=z))
        return positions

    def _hexagon_formation(self, leader: StateVector, num_agents: int) -> list[Pose3D]:
        """Hexagon formation: agents arranged in hexagonal pattern."""
        positions = []
        # Center agent
        positions.append(Pose3D(x=leader.pose.x, y=leader.pose.y, z=leader.pose.z))

        # Ring agents
        ring = 1
        while len(positions) < num_agents:
            agents_in_ring = 6 * ring
            for i in range(agents_in_ring):
                if len(positions) >= num_agents:
                    break
                angle = 2 * math.pi * i / agents_in_ring
                x = leader.pose.x + ring * self.config.spacing * math.cos(angle)
                y = leader.pose.y + ring * self.config.spacing * math.sin(angle)
                z = leader.pose.z
                positions.append(Pose3D(x=x, y=y, z=z))
            ring += 1

        return positions[:num_agents]
