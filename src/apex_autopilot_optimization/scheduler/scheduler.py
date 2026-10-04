"""Task scheduling system for apex-autopilot-optimization."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class TaskPriority(IntEnum):
    """Priority levels for scheduled tasks."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class ScheduledTask:
    """A task to be scheduled for execution."""
    id: str
    name: str
    priority: TaskPriority
    scheduled_time: float
    deadline: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"


@dataclass
class ScheduleConfig:
    """Configuration for the task scheduler."""
    max_concurrent_tasks: int = 10
    default_priority: TaskPriority = TaskPriority.NORMAL
    task_timeout_seconds: float = 60.0
    retry_failed: bool = False
    max_retries: int = 0


class TaskScheduler:
    """Manages scheduling and execution of tasks."""

    def __init__(self, config: ScheduleConfig | None = None) -> None:
        self._config = config or ScheduleConfig()
        self._tasks: dict[str, ScheduledTask] = {}
        self._total_scheduled: int = 0
        self._total_run: int = 0

    def schedule(self, task: ScheduledTask) -> None:
        """Schedule a task for execution."""
        self._tasks[task.id] = task
        self._total_scheduled += 1

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> None:
        """Cancel a scheduled task."""
        self._tasks.pop(task_id, None)

    def get_pending_tasks(self) -> list[ScheduledTask]:
        """Get all pending tasks."""
        return [t for t in self._tasks.values() if t.status == "pending"]

    def get_tasks_by_priority(self, priority: TaskPriority) -> list[ScheduledTask]:
        """Get all tasks with the given priority."""
        return [t for t in self._tasks.values() if t.priority == priority]

    def run_due_tasks(self) -> list[ScheduledTask]:
        """Run all tasks whose scheduled time has passed."""
        now = time.time()
        due_tasks = [
            t for t in self._tasks.values()
            if t.status == "pending" and t.scheduled_time <= now
        ]
        for task in due_tasks:
            task.status = "running"
            self._total_run += 1
        return due_tasks

    def get_scheduler_stats(self) -> dict[str, int]:
        """Get scheduler statistics."""
        return {
            "total_scheduled": self._total_scheduled,
            "total_run": self._total_run,
            "pending_count": len(self.get_pending_tasks()),
        }


class JobQueue:
    """FIFO queue for job execution."""

    def __init__(self) -> None:
        self._queue: deque[ScheduledTask] = deque()

    def enqueue(self, task: ScheduledTask) -> None:
        """Add a task to the queue."""
        self._queue.append(task)

    def dequeue(self) -> ScheduledTask | None:
        """Remove and return the first task, or None if empty."""
        if not self._queue:
            return None
        return self._queue.popleft()

    def peek(self) -> ScheduledTask | None:
        """Return the first task without removing it, or None if empty."""
        if not self._queue:
            return None
        return self._queue[0]

    def get_queue_size(self) -> int:
        """Return the number of tasks in the queue."""
        return len(self._queue)

    def is_empty(self) -> bool:
        """Return True if the queue is empty."""
        return len(self._queue) == 0

    def clear_queue(self) -> None:
        """Remove all tasks from the queue."""
        self._queue.clear()

    def get_queue_stats(self) -> dict[str, Any]:
        """Return queue statistics."""
        return {
            "size": self.get_queue_size(),
            "is_empty": self.is_empty(),
        }
