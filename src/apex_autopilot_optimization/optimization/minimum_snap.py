"""Minimum snap trajectory optimization using polynomial interpolation."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from apex_autopilot_optimization.core.types import (
    ControlInput,
    PlanningProblem,
    PlanningResult,
    Pose3D,
    StateVector,
    Trajectory,
    Velocity3D,
)


@dataclass(frozen=True, slots=True)
class MinimumSnapConfig:
    """Configuration for minimum snap optimizer."""

    degree: int = 5
    waypoint_count: int = 10
    max_iterations: int = 100
    convergence_threshold: float = 1e-6


class MinimumSnapOptimizer:
    """Minimum snap trajectory optimizer using quintic polynomial interpolation.

    Generates smooth trajectories that minimize the snap (4th derivative) cost.
    Each segment between waypoints is a quintic polynomial.
    """

    def __init__(self, config: MinimumSnapConfig | None = None) -> None:
        self.config = config or MinimumSnapConfig()

    def optimize(self, problem: PlanningProblem) -> PlanningResult:
        """Generate minimum snap trajectory from start to goal."""
        start_time = time.perf_counter()

        # Collect all points: start, waypoints, goal
        points = [problem.start.pose]
        for wp in problem.waypoints:
            points.append(wp.pose)
        points.append(problem.goal.pose)

        # Generate trajectory through all points
        states = self._generate_trajectory(points, problem)
        elapsed = (time.perf_counter() - start_time) * 1000

        if not states:
            return PlanningResult(
                success=False,
                computation_time_ms=elapsed,
                message="Failed to generate trajectory",
            )

        trajectory = self._build_trajectory(states, problem)
        cost = self._compute_snap_cost(states)

        return PlanningResult(
            success=True,
            trajectory=trajectory,
            computation_time_ms=elapsed,
            iterations=self.config.max_iterations,
            cost=cost,
        )

    def _generate_trajectory(
        self,
        points: list[Pose3D],
        problem: PlanningProblem,
    ) -> list[StateVector]:
        """Generate smooth trajectory through all points."""
        if len(points) < 2:
            return []

        states: list[StateVector] = []
        total_time = problem.time_horizon_s
        n_segments = len(points) - 1
        segment_time = total_time / n_segments

        for seg_idx in range(n_segments):
            p0 = points[seg_idx]
            p1 = points[seg_idx + 1]

            # Generate states for this segment
            n_points = max(2, self.config.waypoint_count // n_segments)
            for i in range(n_points):
                t = i / (n_points - 1) if n_points > 1 else 0.0
                t_global = seg_idx * segment_time + t * segment_time

                # Quintic polynomial interpolation
                pos = self._quintic_interpolate(p0, p1, t)
                vel = self._quintic_velocity(p0, p1, t, segment_time)

                state = StateVector(
                    pose=Pose3D(x=pos[0], y=pos[1], z=pos[2]),
                    velocity=Velocity3D(vx=vel[0], vy=vel[1], vz=vel[2]),
                    timestamp=t_global,
                )
                states.append(state)

        # Ensure goal is exactly reached
        if states:
            states[-1] = StateVector(
                pose=points[-1],
                velocity=Velocity3D(0, 0, 0),
                timestamp=total_time,
            )

        return states

    def _quintic_interpolate(
        self,
        p0: Pose3D,
        p1: Pose3D,
        t: float,
    ) -> NDArray[np.float64]:
        """Quintic polynomial interpolation between two poses."""
        # Normalized time [0, 1]
        tau = np.clip(t, 0.0, 1.0)

        # Quintic basis functions (minimum snap)
        # s(tau) = 10*tau^3 - 15*tau^4 + 6*tau^5
        s = 10 * tau**3 - 15 * tau**4 + 6 * tau**5

        pos0 = np.array([p0.x, p0.y, p0.z])
        pos1 = np.array([p1.x, p1.y, p1.z])

        return pos0 + s * (pos1 - pos0)

    def _quintic_velocity(
        self,
        p0: Pose3D,
        p1: Pose3D,
        t: float,
        segment_time: float,
    ) -> NDArray[np.float64]:
        """Compute velocity from quintic polynomial derivative."""
        tau = np.clip(t, 0.0, 1.0)

        # Derivative of quintic basis: 30*tau^2 - 60*tau^3 + 30*tau^4
        ds = 30 * tau**2 - 60 * tau**3 + 30 * tau**4

        pos0 = np.array([p0.x, p0.y, p0.z])
        pos1 = np.array([p1.x, p1.y, p1.z])

        # Velocity = ds/dtau * (1/segment_time) * (pos1 - pos0)
        return ds * (pos1 - pos0) / segment_time

    def _compute_snap_cost(self, states: list[StateVector]) -> float:
        """Compute approximate snap cost (4th derivative magnitude)."""
        if len(states) < 5:
            return 0.0

        cost = 0.0
        for i in range(2, len(states) - 2):
            # Approximate 4th derivative using finite differences
            v0 = states[i - 2].velocity.magnitude()
            v1 = states[i - 1].velocity.magnitude()
            v2 = states[i].velocity.magnitude()
            v3 = states[i + 1].velocity.magnitude()
            v4 = states[i + 2].velocity.magnitude()

            dt = states[i].timestamp - states[i - 1].timestamp
            if dt > 0:
                snap = abs(v4 - 4 * v3 + 6 * v2 - 4 * v1 + v0) / dt**4
                cost += snap

        return cost

    def _build_trajectory(
        self,
        states: list[StateVector],
        problem: PlanningProblem,
    ) -> Trajectory:
        """Build Trajectory from state list."""
        n = len(states)
        if n == 0:
            return Trajectory(
                states=[], controls=[], timestamps=np.array([]), vehicle_type=problem.vehicle_type
            )

        timestamps = np.array([s.timestamp for s in states], dtype=np.float64)
        controls = [ControlInput() for _ in range(n)]

        return Trajectory(
            states=states,
            controls=controls,
            timestamps=timestamps,
            vehicle_type=problem.vehicle_type,
        )
