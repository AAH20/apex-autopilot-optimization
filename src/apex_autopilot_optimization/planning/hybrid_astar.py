"""Hybrid A* path planning for non-holonomic vehicles."""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass

import numpy as np

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
class HybridAStarConfig:
    """Configuration for Hybrid A* planner."""

    max_iterations: int = 1000
    step_size: float = 1.0
    steering_angle: float = 0.5
    wheelbase: float = 2.5


@dataclass(slots=True)
class _HybridNode:
    """Internal Hybrid A* search node."""

    x: float
    y: float
    theta: float
    g_cost: float = 0.0
    h_cost: float = 0.0
    parent: _HybridNode | None = None

    @property
    def f_cost(self) -> float:
        return self.g_cost + self.h_cost

    def __lt__(self, other: _HybridNode) -> bool:
        return self.f_cost < other.f_cost

    def state(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.theta)


class HybridAStarPlanner:
    """Hybrid A* planner for non-holonomic vehicles (Ackermann steering).

    Combines discrete graph search with continuous state space sampling.
    Suitable for ground vehicles with kinematic constraints.
    """

    def __init__(self, config: HybridAStarConfig | None = None) -> None:
        self.config = config or HybridAStarConfig()

    def plan(self, problem: PlanningProblem) -> PlanningResult:
        """Plan a path from start to goal using Hybrid A*."""
        start_time = time.perf_counter()

        start = problem.start.pose
        goal = problem.goal.pose

        # Check if start equals goal
        if math.hypot(start.x - goal.x, start.y - goal.y) < 0.5:
            state = StateVector(
                pose=Pose3D(x=start.x, y=start.y, z=start.z),
                velocity=Velocity3D(0, 0, 0),
            )
            trajectory = self._build_trajectory([state], problem)
            elapsed = (time.perf_counter() - start_time) * 1000
            return PlanningResult(
                success=True,
                trajectory=trajectory,
                computation_time_ms=elapsed,
                iterations=0,
                cost=0.0,
            )

        # Initialize search
        root = _HybridNode(x=start.x, y=start.y, theta=start.yaw)
        root.h_cost = self._heuristic(root, goal)

        open_set: list[_HybridNode] = [root]
        closed_set: set[tuple[int, int, int]] = set()
        iterations = 0

        # Discretization resolution for closed set
        xy_res = 0.5
        theta_res = 0.2

        def _discretize(n: _HybridNode) -> tuple[int, int, int]:
            return (
                int(round(n.x / xy_res)),
                int(round(n.y / xy_res)),
                int(round(n.theta / theta_res)),
            )

        while open_set and iterations < self.config.max_iterations:
            iterations += 1
            current = heapq.heappop(open_set)

            # Check if goal reached
            if math.hypot(current.x - goal.x, current.y - goal.y) < 1.0:
                path = self._reconstruct_path(current)
                states = [self._pos_to_state(x, y, theta, problem) for x, y, theta in path]
                trajectory = self._build_trajectory(states, problem)
                cost = self._compute_path_cost(path)
                elapsed = (time.perf_counter() - start_time) * 1000
                return PlanningResult(
                    success=True,
                    trajectory=trajectory,
                    computation_time_ms=elapsed,
                    iterations=iterations,
                    cost=cost,
                )

            closed_set.add(_discretize(current))

            # Generate successors
            for successor in self._successors(current, problem):
                if _discretize(successor) in closed_set:
                    continue

                successor.h_cost = self._heuristic(successor, goal)
                heapq.heappush(open_set, successor)

        elapsed = (time.perf_counter() - start_time) * 1000
        return PlanningResult(
            success=False,
            computation_time_ms=elapsed,
            iterations=iterations,
            message="No path found within iteration limit",
        )

    def _successors(
        self,
        node: _HybridNode,
        problem: PlanningProblem,
    ) -> list[_HybridNode]:
        """Generate successor states with steering angles."""
        successors = []
        for steer in [-self.config.steering_angle, 0.0, self.config.steering_angle]:
            # Bicycle model kinematics
            new_theta = node.theta + (self.config.step_size / self.config.wheelbase) * math.tan(
                steer
            )
            new_x = node.x + self.config.step_size * math.cos(new_theta)
            new_y = node.y + self.config.step_size * math.sin(new_theta)

            # Check collision
            if self._is_collision(new_x, new_y, problem):
                continue

            move_cost = self.config.step_size * (1.0 + 0.1 * abs(steer))
            successor = _HybridNode(
                x=new_x,
                y=new_y,
                theta=new_theta,
                g_cost=node.g_cost + move_cost,
                parent=node,
            )
            successors.append(successor)

        return successors

    def _heuristic(self, node: _HybridNode, goal: Pose3D) -> float:
        """Euclidean distance heuristic."""
        return math.hypot(node.x - goal.x, node.y - goal.y)

    def _is_collision(
        self,
        x: float,
        y: float,
        problem: PlanningProblem,
    ) -> bool:
        """Check if position collides with any obstacle."""
        for obs in problem.obstacles:
            if obs.get("type") == "sphere":
                center = obs["center"]
                radius = float(obs["radius"])
                if math.hypot(x - center[0], y - center[1]) <= radius:
                    return True
        return False

    def _reconstruct_path(self, node: _HybridNode) -> list[tuple[float, float, float]]:
        """Reconstruct path from goal node."""
        path: list[tuple[float, float, float]] = []
        current: _HybridNode | None = node
        while current is not None:
            path.append((current.x, current.y, current.theta))
            current = current.parent
        return list(reversed(path))

    def _compute_path_cost(self, path: list[tuple[float, float, float]]) -> float:
        """Compute total path length."""
        if len(path) < 2:
            return 0.0
        total = 0.0
        for i in range(1, len(path)):
            dx = path[i][0] - path[i - 1][0]
            dy = path[i][1] - path[i - 1][1]
            total += math.hypot(dx, dy)
        return total

    def _pos_to_state(
        self,
        x: float,
        y: float,
        theta: float,
        problem: PlanningProblem,
    ) -> StateVector:
        """Convert position to StateVector."""
        return StateVector(
            pose=Pose3D(x=x, y=y, z=0, yaw=theta),
            velocity=Velocity3D(0, 0, 0),
        )

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

        dt = problem.time_horizon_s / max(n - 1, 1)
        timestamps = np.array([i * dt for i in range(n)], dtype=np.float64)
        controls = [ControlInput() for _ in range(n)]

        return Trajectory(
            states=states,
            controls=controls,
            timestamps=timestamps,
            vehicle_type=problem.vehicle_type,
        )
