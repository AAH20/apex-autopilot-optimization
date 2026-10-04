"""PRM (Probabilistic Roadmap) path planning algorithm."""

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
class PRMConfig:
    """Configuration for PRM planner."""

    num_samples: int = 100
    nearest_neighbors: int = 5
    max_iterations: int = 10


@dataclass(slots=True)
class _PRMNode:
    """Internal PRM graph node."""

    position: NDArray[np.float64]
    neighbors: list[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.neighbors is None:
            self.neighbors = []


class PRMPlanner:
    """PRM path planner using probabilistic roadmaps.

    Samples random points in free space, connects nearby points to form a roadmap,
    then finds shortest path from start to goal using Dijkstra's algorithm.
    """

    def __init__(self, config: PRMConfig | None = None) -> None:
        self.config = config or PRMConfig()

    def plan(self, problem: PlanningProblem) -> PlanningResult:
        """Plan a path from start to goal using PRM."""
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
        if np.linalg.norm(start_pos - goal_pos) < 0.1:
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

        # Compute bounding box
        min_bound = np.minimum(start_pos, goal_pos) - 5.0
        max_bound = np.maximum(start_pos, goal_pos) + 5.0

        # Build roadmap
        nodes = self._build_roadmap(min_bound, max_bound, problem)

        # Add start and goal to roadmap
        start_idx = len(nodes)
        nodes.append(_PRMNode(position=start_pos))
        goal_idx = len(nodes)
        nodes.append(_PRMNode(position=goal_pos))

        # Connect start and goal to nearby nodes
        self._connect_node(start_idx, nodes, problem)
        self._connect_node(goal_idx, nodes, problem)

        # Find shortest path using Dijkstra
        path_indices = self._dijkstra(start_idx, goal_idx, nodes)

        elapsed = (time.perf_counter() - start_time) * 1000

        if path_indices is None:
            return PlanningResult(
                success=False,
                computation_time_ms=elapsed,
                iterations=self.config.max_iterations,
                message="No path found",
            )

        # Reconstruct path
        path = [nodes[i].position for i in path_indices]
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

    def _build_roadmap(
        self,
        min_bound: NDArray[np.float64],
        max_bound: NDArray[np.float64],
        problem: PlanningProblem,
    ) -> list[_PRMNode]:
        """Build PRM roadmap by sampling random points."""
        nodes: list[_PRMNode] = []

        for _ in range(self.config.num_samples):
            # Sample random point
            random_pos = np.random.uniform(min_bound, max_bound)

            # Check collision
            if self._is_collision(random_pos, problem=problem):
                continue

            # Add node
            nodes.append(_PRMNode(position=random_pos))

        # Connect nearby nodes
        for i in range(len(nodes)):
            self._connect_node(i, nodes, problem)

        return nodes

    def _connect_node(
        self,
        node_idx: int,
        nodes: list[_PRMNode],
        problem: PlanningProblem,
    ) -> None:
        """Connect a node to its nearest neighbors."""
        if not nodes:
            return

        node = nodes[node_idx]
        distances: list[tuple[float, int]] = []

        for i, other in enumerate(nodes):
            if i == node_idx:
                continue
            dist = np.linalg.norm(node.position - other.position)
            distances.append((dist, i))

        # Sort by distance and connect to nearest neighbors
        distances.sort()
        for dist, i in distances[: self.config.nearest_neighbors]:
            # Check edge collision
            if not self._is_collision(node.position, nodes[i].position, problem):
                node.neighbors.append(i)
                nodes[i].neighbors.append(node_idx)

    def _dijkstra(
        self,
        start_idx: int,
        goal_idx: int,
        nodes: list[_PRMNode],
    ) -> list[int] | None:
        """Find shortest path using Dijkstra's algorithm."""
        import heapq

        dist = {i: float("inf") for i in range(len(nodes))}
        dist[start_idx] = 0.0
        prev: dict[int, int | None] = {start_idx: None}
        pq = [(0.0, start_idx)]

        while pq:
            d, u = heapq.heappop(pq)

            if u == goal_idx:
                # Reconstruct path
                path: list[int] = []
                current: int | None = goal_idx
                while current is not None:
                    path.append(current)
                    current = prev.get(current)
                return list(reversed(path))

            if d > dist[u]:
                continue

            for v in nodes[u].neighbors:
                new_dist = d + np.linalg.norm(nodes[u].position - nodes[v].position)
                if new_dist < dist[v]:
                    dist[v] = new_dist
                    prev[v] = u
                    heapq.heappush(pq, (new_dist, v))

        return None

    def _is_collision(
        self,
        pos: NDArray[np.float64],
        end_pos: NDArray[np.float64] | None = None,
        problem: PlanningProblem | None = None,
    ) -> bool:
        """Check if position or edge collides with any obstacle."""
        if problem is None:
            return False

        # Check single point
        if end_pos is None:
            for obs in problem.obstacles:
                if obs.get("type") == "sphere":
                    center = np.array(obs["center"], dtype=np.float64)
                    radius = float(obs["radius"])
                    if np.linalg.norm(pos - center) <= radius:
                        return True
            return False

        # Check edge (line segment)
        for obs in problem.obstacles:
            if obs.get("type") == "sphere":
                center = np.array(obs["center"], dtype=np.float64)
                radius = float(obs["radius"])
                if self._segment_sphere_intersection(pos, end_pos, center, radius):
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
