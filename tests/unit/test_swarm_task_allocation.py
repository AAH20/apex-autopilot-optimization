"""Tests for swarm task allocation algorithms."""

from __future__ import annotations

from apex_autopilot_optimization.core.types import (
    Pose3D,
    VehicleType,
)
from apex_autopilot_optimization.swarm.task_allocation import (
    Agent,
    Task,
    TaskAllocationConfig,
    TaskAllocator,
)


class TestTaskAllocationConfig:
    """Tests for TaskAllocationConfig."""

    def test_defaults(self) -> None:
        config = TaskAllocationConfig()
        assert config.algorithm == "greedy"
        assert config.max_tasks_per_agent == 10
        assert config.communication_range == 100.0

    def test_custom_values(self) -> None:
        config = TaskAllocationConfig(algorithm="auction", max_tasks_per_agent=5)
        assert config.algorithm == "auction"
        assert config.max_tasks_per_agent == 5


class TestTask:
    """Tests for Task dataclass."""

    def test_creation(self) -> None:
        task = Task(id=1, position=Pose3D(x=1, y=2, z=3), priority=1.0)
        assert task.id == 1
        assert task.position.x == 1
        assert task.priority == 1.0
        assert task.assigned_agent is None


class TestAgent:
    """Tests for Agent dataclass."""

    def test_creation(self) -> None:
        agent = Agent(
            id=1,
            position=Pose3D(x=0, y=0, z=0),
            vehicle_type=VehicleType.UAV_MULTIROTOR,
        )
        assert agent.id == 1
        assert agent.position.x == 0
        assert agent.vehicle_type == VehicleType.UAV_MULTIROTOR
        assert agent.assigned_tasks == []


class TestTaskAllocator:
    """Tests for TaskAllocator."""

    def _make_agent(self, agent_id: int, x: float, y: float) -> Agent:
        return Agent(
            id=agent_id,
            position=Pose3D(x=x, y=y, z=0),
            vehicle_type=VehicleType.UAV_MULTIROTOR,
        )

    def _make_task(self, task_id: int, x: float, y: float) -> Task:
        return Task(id=task_id, position=Pose3D(x=x, y=y, z=0), priority=1.0)

    def test_allocation_basic(self) -> None:
        allocator = TaskAllocator()
        agents = [self._make_agent(1, 0, 0), self._make_agent(2, 10, 0)]
        tasks = [self._make_task(1, 5, 0), self._make_task(2, 15, 0)]
        result = allocator.allocate(agents, tasks)
        assert result is not None
        assert len(result) == 2

    def test_allocation_assigns_all_tasks(self) -> None:
        allocator = TaskAllocator()
        agents = [self._make_agent(1, 0, 0), self._make_agent(2, 10, 0)]
        tasks = [self._make_task(1, 5, 0), self._make_task(2, 15, 0)]
        result = allocator.allocate(agents, tasks)
        assigned_tasks = {task_id for _, task_id in result}
        assert assigned_tasks == {1, 2}

    def test_allocation_respects_max_tasks(self) -> None:
        allocator = TaskAllocator(config=TaskAllocationConfig(max_tasks_per_agent=1))
        agents = [self._make_agent(1, 0, 0)]
        tasks = [self._make_task(1, 5, 0), self._make_task(2, 10, 0)]
        result = allocator.allocate(agents, tasks)
        # With max_tasks_per_agent=1, only 1 task should be assigned
        assert len(result) == 1

    def test_allocation_empty_agents(self) -> None:
        allocator = TaskAllocator()
        tasks = [self._make_task(1, 5, 0)]
        result = allocator.allocate([], tasks)
        assert result == []

    def test_allocation_empty_tasks(self) -> None:
        allocator = TaskAllocator()
        agents = [self._make_agent(1, 0, 0)]
        result = allocator.allocate(agents, [])
        assert result == []

    def test_allocation_returns_agent_task_pairs(self) -> None:
        allocator = TaskAllocator()
        agents = [self._make_agent(1, 0, 0)]
        tasks = [self._make_task(1, 5, 0)]
        result = allocator.allocate(agents, tasks)
        assert len(result) == 1
        agent_id, task_id = result[0]
        assert agent_id == 1
        assert task_id == 1

    def test_allocation_with_priorities(self) -> None:
        allocator = TaskAllocator(config=TaskAllocationConfig(max_tasks_per_agent=1))
        agents = [self._make_agent(1, 0, 0)]
        tasks = [
            Task(id=1, position=Pose3D(x=5, y=0, z=0), priority=0.5),
            Task(id=2, position=Pose3D(x=10, y=0, z=0), priority=1.0),
        ]
        result = allocator.allocate(agents, tasks)
        # Higher priority task should be assigned first
        assert len(result) == 1
        _, task_id = result[0]
        assert task_id == 2

    def test_allocation_multiple_agents_multiple_tasks(self) -> None:
        allocator = TaskAllocator()
        agents = [
            self._make_agent(1, 0, 0),
            self._make_agent(2, 10, 0),
            self._make_agent(3, 20, 0),
        ]
        tasks = [
            self._make_task(1, 5, 0),
            self._make_task(2, 15, 0),
            self._make_task(3, 25, 0),
        ]
        result = allocator.allocate(agents, tasks)
        assert len(result) == 3
        # Each agent should get exactly one task
        agent_ids = {agent_id for agent_id, _ in result}
        assert len(agent_ids) == 3
