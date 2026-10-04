"""RRT (Rapidly-exploring Random Tree) path planning algorithm."""

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
class RRTConfig:
    """Configuration for RRT planner."""

    max_iterations: int = 1000
    step_size: float = 1.0
    goal_sample_rate: float = 0.1
    goal_tolerance: float = 1.0


@dataclass(slots=True)
class _RRTNode:
    """Internal RRT tree node."""

    position: NDArray[np.float64]
    parent: _RRTNode | None = None


class RRTPlanner:
    """RRT path planner for 3D environments.

    Uses rapidly-exploring random trees to find collision-free paths.
    Supports goal biasing and sphere obstacles.
    """

    def __init__(self, config: RRTConfig | None = None) -> None:
        self.config = config or RRTConfig()

    def plan(self, problem: PlanningProblem) -> PlanningResult:
        """Plan a path from start to goal using RRT."""
        start_time = time.perf_counter()

        start_pos = np.array(
            [problem.start.pose.x, problem.start.pose.y, problem.start.pose.z],
            dtype=np.float64,
        )
        goal_pos = np.array(
            [problem.goal.pose.x, problem.goal.pose.y, problem.goal.pose.z],
            dtype=np.float64,
        )

        # Check if start equals goal
        if np.linalg.norm(start_pos - goal_pos) < self.config.goal_tolerance:
            state = StateVector(
                pose=Pose3D(x=start_pos[0], y=start_pos[1], z=start_pos[2]),
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

        # Initialize tree with start node
        root = _RRTNode(position=start_pos)
        nodes: list[_RRTNode] = [root]

        # Compute bounding box for sampling
        min_bound = np.minimum(start_pos, goal_pos) - 5.0
        max_bound = np.maximum(start_pos, goal_pos) + 5.0

        goal_node: _RRTNode | None = None

        for iteration in range(self.config.max_iterations):
            # Sample random point (with goal biasing)
            if np.random.random() < self.config.goal_sample_rate:
                random_pos = goal_pos
            else:
                random_pos = np.random.uniform(min_bound, max_bound)

            # Find nearest node
            nearest = self._nearest_node(nodes, random_pos)

            # Steer towards random point
            new_pos = self._steer(nearest.position, random_pos)

            # Check collision
            if self._is_collision(nearest.position, new_pos, problem):
                continue

            # Add new node
            new_node = _RRTNode(position=new_pos, parent=nearest)
            nodes.append(new_node)

            # Check if goal reached
            if np.linalg.norm(new_pos - goal_pos) < self.config.goal_tolerance:
                goal_node = new_node
                break

        elapsed = (time.perf_counter() - start_time) * 1000

        if goal_node is None:
            return PlanningResult(
                success=False,
                computation_time_ms=elapsed,
                iterations=self.config.max_iterations,
                message="No path found within iteration limit",
            )

        # Reconstruct path
        path = self._reconstruct_path(goal_node)
        states = [self._pos_to_state(pos, problem) for pos in path]
        trajectory = self._build_trajectory(states, problem)
        cost = self._compute_path_cost(path)

        return PlanningResult(
            success=True,
            trajectory=trajectory,
            computation_time_ms=elapsed,
            iterations=len(nodes),
            cost=cost,
        )

    def _nearest_node(
        self,
        nodes: list[_RRTNode],
        target: NDArray[np.float64],
    ) -> _RRTNode:
        """Find nearest node to target position."""
        min_dist = float("inf")
        nearest = nodes[0]
        for node in nodes:
            dist = np.linalg.norm(node.position - target)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest

    def _steer(
        self,
        from_pos: NDArray[np.float64],
        to_pos: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Steer from one position towards another with step size limit."""
        direction = to_pos - from_pos
        dist = np.linalg.norm(direction)
        if dist < self.config.step_size:
            return to_pos
        return from_pos + (direction / dist) * self.config.step_size

    def _is_collision(
        self,
        from_pos: NDArray[np.float64],
        to_pos: NDArray[np.float64],
        problem: PlanningProblem,
    ) -> bool:
        """Check if line segment collides with any obstacle."""
        for obs in problem.obstacles:
            if obs.get("type") == "sphere":
                center = np.array(obs["center"], dtype=np.float64)
                radius = float(obs["radius"])
                if self._segment_sphere_intersection(from_pos, to_pos, center, radius):
                    return True
        return False

    def _segment_sphere_intersection(
        self,
        a: NDArray[np.float64],
        b: NDArray[np.float64],
        center: NDArray[np.float64],
        radius: float,
    ) -> bool:
        """Check if line segment AB intersects sphere."""
        ab = b - a
        ac = center - a
        ab_len_sq = np.dot(ab, ab)

        if ab_len_sq < 1e-10:
            return np.linalg.norm(ac) <= radius

        t = np.clip(np.dot(ac, ab) / ab_len_sq, 0.0, 1.0)
        closest = a + t * ab
        return np.linalg.norm(closest - center) <= radius

    def _reconstruct_path(self, goal_node: _RRTNode) -> list[NDArray[np.float64]]:
        """Reconstruct path from goal node to root."""
        path: list[NDArray[np.float64]] = []
        current: _RRTNode | None = goal_node
        while current is not None:
            path.append(current.position)
            current = current.parent
        return list(reversed(path))

    def _compute_path_cost(self, path: list[NDArray[np.float64]]) -> float:
        """Compute total path length."""
        if len(path) < 2:
            return 0.0
        total = 0.0
        for i in range(1, len(path)):
            total += np.linalg.norm(path[i] - path[i - 1])
        return float(total)

    def _pos_to_state(
        self,
        pos: NDArray[np.float64],
        problem: PlanningProblem,
    ) -> StateVector:
        """Convert position array to StateVector."""
        return StateVector(
            pose=Pose3D(x=pos[0], y=pos[1], z=pos[2]),
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
            return Trajectory(states=[], controls=[], timestamps=np.array([]), vehicle_type=problem.vehicle_type)

        dt = problem.time_horizon_s / max(n - 1, 1)
        timestamps = np.array([i * dt for i in range(n)], dtype=np.float64)
        controls = [ControlInput() for _ in range(n)]

        return Trajectory(
            states=states,
            controls=controls,
            timestamps=timestamps,
            vehicle_type=problem.vehicle_type,
        )
