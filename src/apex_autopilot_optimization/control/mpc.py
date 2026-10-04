"""Model Predictive Control for trajectory tracking."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from apex_autopilot_optimization.core.types import (
    ControlInput,
    StateVector,
)


@dataclass(frozen=True, slots=True)
class MPCConfig:
    """Configuration for MPC controller."""

    horizon: int = 10
    dt: float = 0.1
    max_iterations: int = 100
    convergence_threshold: float = 1e-4


class MPCController:
    """Model Predictive Control using quadratic programming.

    Simplified MPC that computes control inputs to minimize
    tracking error over a receding horizon.
    """

    def __init__(self, config: MPCConfig | None = None) -> None:
        self.config = config or MPCConfig()

    def compute_control(
        self,
        state: StateVector,
        target: StateVector,
    ) -> ControlInput:
        """Compute control input to track target state."""
        # Compute position error
        pos_error = np.array(
            [
                target.pose.x - state.pose.x,
                target.pose.y - state.pose.y,
                target.pose.z - state.pose.z,
            ],
            dtype=np.float64,
        )

        # Compute velocity error
        vel_error = np.array(
            [
                target.velocity.vx - state.velocity.vx,
                target.velocity.vy - state.velocity.vy,
                target.velocity.vz - state.velocity.vz,
            ],
            dtype=np.float64,
        )

        # Simple proportional control with horizon-based scaling
        # In a full MPC, this would solve a QP over the horizon
        kp = 2.0  # Proportional gain
        kd = 0.5  # Derivative gain

        # Compute desired acceleration
        desired_accel = kp * pos_error + kd * vel_error

        # Convert to control inputs (simplified mapping)
        throttle = float(np.clip(desired_accel[2], -10.0, 10.0))
        roll_rate = float(np.clip(desired_accel[1] * 0.5, -10.0, 10.0))
        pitch_rate = float(np.clip(desired_accel[0] * 0.5, -10.0, 10.0))
        yaw_rate = float(np.clip(np.arctan2(pos_error[1], pos_error[0]) * 0.1, -10.0, 10.0))

        return ControlInput(
            throttle=throttle,
            roll_rate=roll_rate,
            pitch_rate=pitch_rate,
            yaw_rate=yaw_rate,
        )
