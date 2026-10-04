"""A* path planning algorithm for 2D/3D grid-based navigation."""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from apex_autopilot_optimization.core.types import (
    ControlInput,
    PlanningProblem,
    PlanningResult,
    StateVector,
    Trajectory,
    Velocity3D,
)


@dataclass(frozen=True, slots=True)
class AStarConfig:
    """Configuration for A* planner."""

    resolution_m: float = 1.0
    max_iterations: int = 10000
    diagonal_movement: bool = True
    heuristic_weight: float = 1.0


@dataclass(slots=True)
class _Node:
    """Internal A* search node."""

    x: int
    y: int
    z: int
    g_cost: float = 0.0
    h_cost: float = 0.0
    parent: _Node | None = None

    @property
    def f_cost(self) -> float:
        return self.g_cost + self.h_cost

    def __lt__(self, other: _Node) -> bool:
        return self.f_cost < other.f_cost

    def pos(self) -> tuple[int, int, int]:
        return (self.x, self.y, self.z)


class AStarPlanner:
    """A* path planner supporting 2D and 3D grid-based navigation."""

    def __init__(self, config: AStarConfig | None = None) -> None:
        self.config = config or AStarConfig()

    def plan(self, problem: PlanningProblem) -> PlanningResult:
        """Plan a path from start to goal using A*."""
        start_time = time.perf_counter()

        start_pos = self._world_to_grid(problem.start.pose)
        goal_pos = self._world_to_grid(problem.goal.pose)

        if start_pos == goal_pos:
            trajectory = self._build_trajectory([problem.start], problem)
            elapsed = (time.perf_counter() - start_time) * 1000
            return PlanningResult(
                success=True,
                trajectory=trajectory,
                computation_time_ms=elapsed,
                iterations=0,
                cost=0.0,
            )

        path = self._astar(start_pos, goal_pos, problem)
        elapsed = (time.perf_counter() - start_time) * 1000

        if path is None:
            return PlanningResult(
                success=False,
                computation_time_ms=elapsed,
                iterations=self.config.max_iterations,
                message="No path found",
            )

        states = [self._grid_to_state(p, problem) for p in path]
        trajectory = self._build_trajectory(states, problem)
        cost = self._compute_path_cost(path)

        return PlanningResult(
            success=True,
            trajectory=trajectory,
            computation_time_ms=elapsed,
            iterations=len(path),
            cost=cost,
        )

    def _astar(
        self,
        start: tuple[int, int, int],
        goal: tuple[int, int, int],
        problem: PlanningProblem,
    ) -> list[tuple[int, int, int]] | None:
        """Core A* search."""
        open_set: list[_Node] = []
        start_node = _Node(x=start[0], y=start[1], z=start[2])
        start_node.h_cost = self._heuristic(start, goal)
        heapq.heappush(open_set, start_node)

        closed_set: set[tuple[int, int, int]] = set()
        g_scores: dict[tuple[int, int, int], float] = {start: 0.0}
        iterations = 0

        while open_set and iterations < self.config.max_iterations:
            iterations += 1
            current = heapq.heappop(open_set)

            if current.pos() == goal:
                return self._reconstruct_path(current)

            if current.pos() in closed_set:
                continue
            closed_set.add(current.pos())

            for neighbor_pos in self._neighbors(current.pos(), problem):
                if neighbor_pos in closed_set:
                    continue
                if self._is_collision(neighbor_pos, problem):
                    continue

                move_cost = self._move_cost(current.pos(), neighbor_pos)
                tentative_g = current.g_cost + move_cost

                if tentative_g < g_scores.get(neighbor_pos, float("inf")):
                    g_scores[neighbor_pos] = tentative_g
                    neighbor = _Node(
                        x=neighbor_pos[0],
                        y=neighbor_pos[1],
                        z=neighbor_pos[2],
                        g_cost=tentative_g,
                        h_cost=self._heuristic(neighbor_pos, goal),
                        parent=current,
                    )
                    heapq.heappush(open_set, neighbor)

        return None

    def _neighbors(
        self,
        pos: tuple[int, int, int],
        problem: PlanningProblem,
    ) -> list[tuple[int, int, int]]:
        """Generate valid neighbor positions."""
        directions: list[tuple[int, int, int]] = []

        # 6-connected (2D + altitude)
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            directions.append((pos[0] + dx, pos[1] + dy, pos[2]))

        # Altitude changes
        for dz in [-1, 1]:
            directions.append((pos[0], pos[1], pos[2] + dz))

        # Diagonal movement in XY
        if self.config.diagonal_movement:
            for dx, dy in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
                directions.append((pos[0] + dx, pos[1] + dy, pos[2]))

        return directions

    def _heuristic(
        self,
        a: tuple[int, int, int],
        b: tuple[int, int, int],
    ) -> float:
        """Octile distance heuristic."""
        dx, dy, dz = abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])
        if self.config.diagonal_movement:
            return max(dx, dy, dz) + (np.sqrt(2) - 1) * min(dx, dy) + (np.sqrt(3) - np.sqrt(2)) * min(dx, dy, dz)
        return float(dx + dy + dz)

    def _move_cost(
        self,
        a: tuple[int, int, int],
        b: tuple[int, int, int],
    ) -> float:
        """Cost of moving from a to b."""
        diff = sum(abs(a[i] - b[i]) for i in range(3))
        if diff == 1:
            return 1.0
        if diff == 2:
            return float(np.sqrt(2))
        return float(np.sqrt(3))

    def _is_collision(
        self,
        pos: tuple[int, int, int],
        problem: PlanningProblem,
    ) -> bool:
        """Check if grid position collides with any obstacle."""
        world_pos = self._grid_to_world(pos)
        for obs in problem.obstacles:
            if obs.get("type") == "sphere":
                center = np.array(obs["center"], dtype=np.float64)
                radius = float(obs["radius"])
                if np.linalg.norm(world_pos - center) <= radius:
                    return True
        return False

    def _reconstruct_path(self, node: _Node) -> list[tuple[int, int, int]]:
        """Reconstruct path from goal node."""
        path: list[tuple[int, int, int]] = []
        current: _Node | None = node
        while current is not None:
            path.append(current.pos())
            current = current.parent
        return list(reversed(path))

    def _compute_path_cost(self, path: list[tuple[int, int, int]]) -> float:
        """Compute total path cost."""
        if len(path) < 2:
            return 0.0
        total = 0.0
        for i in range(1, len(path)):
            total += self._move_cost(path[i - 1], path[i])
        return total * self.config.resolution_m

    def _world_to_grid(self, pose) -> tuple[int, int, int]:
        """Convert world coordinates to grid indices."""
        return (
            int(round(pose.x / self.config.resolution_m)),
            int(round(pose.y / self.config.resolution_m)),
            int(round(pose.z / self.config.resolution_m)),
        )

    def _grid_to_world(self, pos: tuple[int, int, int]) -> NDArray[np.float64]:
        """Convert grid indices to world coordinates."""
        return np.array(
            [pos[0] * self.config.resolution_m, pos[1] * self.config.resolution_m, pos[2] * self.config.resolution_m],
            dtype=np.float64,
        )

    def _grid_to_state(
        self,
        pos: tuple[int, int, int],
        problem: PlanningProblem,
    ) -> StateVector:
        """Convert grid position to StateVector."""
        world = self._grid_to_world(pos)
        from apex_autopilot_optimization.core.types import Pose3D

        return StateVector(
            pose=Pose3D(x=world[0], y=world[1], z=world[2]),
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
