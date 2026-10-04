"""Extended Kalman Filter for vehicle state estimation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from apex_autopilot_optimization.core.types import (
    Pose3D,
    StateVector,
    Velocity3D,
)


@dataclass(frozen=True, slots=True)
class EKFConfig:
    """Configuration for EKF estimator."""

    state_dim: int = 12
    measurement_dim: int = 6
    process_noise: float = 0.01
    measurement_noise: float = 0.1


class EKFEstimator:
    """Extended Kalman Filter for 12-state vehicle estimation.

    State vector: [x, y, z, roll, pitch, yaw, vx, vy, vz, vroll, vpitch, vyaw]
    Measurement: [x, y, z, roll, pitch, yaw]
    """

    def __init__(self, config: EKFConfig | None = None) -> None:
        self.config = config or EKFConfig()
        self._state = np.zeros(self.config.state_dim, dtype=np.float64)
        self._covariance = np.eye(self.config.state_dim, dtype=np.float64)
        self._process_noise = np.eye(self.config.state_dim, dtype=np.float64) * self.config.process_noise
        self._measurement_noise = np.eye(self.config.measurement_dim, dtype=np.float64) * self.config.measurement_noise

    def predict(self, dt: float) -> None:
        """Prediction step using constant velocity model."""
        # State transition matrix for constant velocity model
        F = np.eye(self.config.state_dim, dtype=np.float64)
        # Position += velocity * dt
        for i in range(6):
            F[i, i + 6] = dt

        # Predict state
        self._state = F @ self._state

        # Predict covariance
        self._covariance = F @ self._covariance @ F.T + self._process_noise

    def update(self, measurement: NDArray[np.float64]) -> None:
        """Update step with measurement."""
        # Measurement matrix (we observe position and orientation)
        H = np.zeros((self.config.measurement_dim, self.config.state_dim), dtype=np.float64)
        for i in range(6):
            H[i, i] = 1.0

        # Innovation
        y = measurement - H @ self._state

        # Innovation covariance
        S = H @ self._covariance @ H.T + self._measurement_noise

        # Kalman gain
        K = self._covariance @ H.T @ np.linalg.inv(S)

        # Update state
        self._state = self._state + K @ y

        # Update covariance (Joseph form for numerical stability)
        I_KH = np.eye(self.config.state_dim) - K @ H
        self._covariance = I_KH @ self._covariance @ I_KH.T + K @ self._measurement_noise @ K.T

    def get_state(self) -> StateVector:
        """Get current state estimate as StateVector."""
        return StateVector(
            pose=Pose3D(
                x=float(self._state[0]),
                y=float(self._state[1]),
                z=float(self._state[2]),
                roll=float(self._state[3]),
                pitch=float(self._state[4]),
                yaw=float(self._state[5]),
            ),
            velocity=Velocity3D(
                vx=float(self._state[6]),
                vy=float(self._state[7]),
                vz=float(self._state[8]),
                vroll=float(self._state[9]),
                vpitch=float(self._state[10]),
                vyaw=float(self._state[11]),
            ),
        )

    def get_covariance(self) -> NDArray[np.float64]:
        """Get current covariance matrix."""
        return self._covariance.copy()

    def reset(self) -> None:
        """Reset filter to initial state."""
        self._state = np.zeros(self.config.state_dim, dtype=np.float64)
        self._covariance = np.eye(self.config.state_dim, dtype=np.float64)
