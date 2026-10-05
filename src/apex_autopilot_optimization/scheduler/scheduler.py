"""Task scheduling system for apex-autopilot-optimization."""
from __future__ import annotations

import time
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


class TaskScheduler:
    """Manages scheduling and execution of tasks."""

    def __init__(self, config: Any | None = None) -> None:
        if config is None:
            from apex_autopilot_optimization.scheduler.config import ScheduleConfig

            config = ScheduleConfig()
        self._config = config
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
            t for t in self._tasks.values() if t.status == "pending" and t.scheduled_time <= now
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
