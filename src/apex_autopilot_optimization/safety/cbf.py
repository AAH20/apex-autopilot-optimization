"""Control Barrier Function safety filter for collision avoidance."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from apex_autopilot_optimization.core.types import (
    ControlInput,
    StateVector,
)


@dataclass(frozen=True, slots=True)
class CBFConfig:
    """Configuration for CBF safety filter."""

    alpha: float = 1.0
    beta: float = 1.0
    safety_margin: float = 0.5
    max_correction: float = 10.0


class CBFFilter:
    """Control Barrier Function safety filter.

    Filters control inputs to ensure collision-free operation.
    Uses a simple CBF formulation: h(x) = distance_to_obstacle - safety_margin
    """

    def __init__(self, config: CBFConfig | None = None) -> None:
        self.config = config or CBFConfig()

    def filter(
        self,
        state: StateVector,
        control: ControlInput,
        obstacles: list[dict],
    ) -> ControlInput:
        """Filter control input to ensure safety."""
        if not obstacles:
            return control

        # Compute minimum distance to any obstacle
        min_distance = self._min_distance_to_obstacles(state, obstacles)

        # Compute CBF value: h(x) = distance - safety_margin
        h = min_distance - self.config.safety_margin

        # If h > 0, we're safe — pass through
        if h > 0:
            return control

        # If h <= 0, we're in danger — apply correction
        correction = self._compute_correction(h, state, obstacles)

        # Apply correction to control
        return ControlInput(
            throttle=max(0.0, control.throttle - correction),
            roll_rate=control.roll_rate,
            pitch_rate=control.pitch_rate,
            yaw_rate=control.yaw_rate,
            timestamp=control.timestamp,
        )

    def _min_distance_to_obstacles(
        self,
        state: StateVector,
        obstacles: list[dict],
    ) -> float:
        """Compute minimum distance from state to any obstacle."""
        pos = np.array([state.pose.x, state.pose.y, state.pose.z], dtype=np.float64)
        min_dist = float("inf")

        for obs in obstacles:
            if obs.get("type") == "sphere":
                center = np.array(obs["center"], dtype=np.float64)
                radius = float(obs["radius"])
                dist = np.linalg.norm(pos - center) - radius
                min_dist = min(min_dist, dist)

        return min_dist

    def _compute_correction(
        self,
        h: float,
        state: StateVector,
        obstacles: list[dict],
    ) -> float:
        """Compute control correction based on CBF value."""
        # Simple proportional correction: more negative h = more correction
        correction = -h * self.config.alpha
        return min(correction, self.config.max_correction)
