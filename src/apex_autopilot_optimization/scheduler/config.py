"""Configuration for the task scheduler."""
from __future__ import annotations

from dataclasses import dataclass

from apex_autopilot_optimization.scheduler.scheduler import TaskPriority


@dataclass
class ScheduleConfig:
    """Configuration for the task scheduler."""

    max_concurrent_tasks: int = 10
    default_priority: TaskPriority = TaskPriority.NORMAL
    task_timeout_seconds: float = 60.0
    retry_failed: bool = False
    max_retries: int = 0
