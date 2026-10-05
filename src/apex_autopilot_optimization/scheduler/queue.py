"""Job queue for task scheduling."""

from __future__ import annotations

from collections import deque
from typing import Any

from apex_autopilot_optimization.scheduler.scheduler import ScheduledTask


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
