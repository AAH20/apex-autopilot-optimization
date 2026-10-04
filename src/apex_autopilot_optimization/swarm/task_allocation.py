"""Swarm task allocation algorithms for multi-agent coordination."""

from __future__ import annotations

from dataclasses import dataclass, field

from apex_autopilot_optimization.core.types import Pose3D, VehicleType


@dataclass(frozen=True, slots=True)
class TaskAllocationConfig:
    """Configuration for task allocation."""

    algorithm: str = "greedy"
    max_tasks_per_agent: int = 10
    communication_range: float = 100.0


@dataclass(slots=True)
class Task:
    """Task to be assigned to an agent."""

    id: int
    position: Pose3D
    priority: float = 1.0
    assigned_agent: int | None = None


@dataclass(slots=True)
class Agent:
    """Agent that can be assigned tasks."""

    id: int
    position: Pose3D
    vehicle_type: VehicleType
    assigned_tasks: list[int] = field(default_factory=list)


class TaskAllocator:
    """Greedy task allocator for multi-agent systems.

    Assigns tasks to agents based on distance and priority.
    Uses a greedy algorithm that assigns highest priority tasks first
    to the nearest available agent.
    """

    def __init__(self, config: TaskAllocationConfig | None = None) -> None:
        self.config = config or TaskAllocationConfig()

    def allocate(
        self,
        agents: list[Agent],
        tasks: list[Task],
    ) -> list[tuple[int, int]]:
        """Allocate tasks to agents.

        Returns list of (agent_id, task_id) pairs.
        """
        if not agents or not tasks:
            return []

        # Sort tasks by priority (highest first)
        sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)

        # Track assignments and agent task counts
        assignments: list[tuple[int, int]] = []
        agent_task_counts: dict[int, int] = {agent.id: 0 for agent in agents}

        for task in sorted_tasks:
            # Find best agent for this task (nearest with capacity)
            best_agent = self._find_best_agent(task, agents, agent_task_counts)
            if best_agent is not None:
                assignments.append((best_agent.id, task.id))
                agent_task_counts[best_agent.id] += 1
                task.assigned_agent = best_agent.id
                best_agent.assigned_tasks.append(task.id)

        return assignments

    def _find_best_agent(
        self,
        task: Task,
        agents: list[Agent],
        agent_task_counts: dict[int, int],
    ) -> Agent | None:
        """Find the best agent for a task based on distance and capacity."""
        best_agent: Agent | None = None
        best_distance = float("inf")

        for agent in agents:
            # Check if agent has capacity
            if agent_task_counts[agent.id] >= self.config.max_tasks_per_agent:
                continue

            # Check communication range
            distance = agent.position.distance_to(task.position)
            if distance > self.config.communication_range:
                continue

            if distance < best_distance:
                best_distance = distance
                best_agent = agent

        return best_agent
