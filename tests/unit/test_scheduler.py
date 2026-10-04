"""Tests for the task scheduling system."""
from __future__ import annotations

import time

from apex_autopilot_optimization.scheduler import (
    JobQueue,
    ScheduleConfig,
    ScheduledTask,
    TaskPriority,
    TaskScheduler,
)


class TestTaskPriority:
    """Tests for TaskPriority enum."""

    def test_priority_members_exist(self) -> None:
        assert TaskPriority.CRITICAL is not None
        assert TaskPriority.HIGH is not None
        assert TaskPriority.NORMAL is not None
        assert TaskPriority.LOW is not None
        assert TaskPriority.BACKGROUND is not None

    def test_priority_ordering(self) -> None:
        assert TaskPriority.CRITICAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.LOW
        assert TaskPriority.LOW < TaskPriority.BACKGROUND

    def test_priority_distinct_values(self) -> None:
        values = {p.value for p in TaskPriority}
        assert len(values) == 5


class TestScheduledTask:
    """Tests for ScheduledTask dataclass."""

    def test_creation_with_all_fields(self) -> None:
        task = ScheduledTask(
            id="task-1",
            name="test_task",
            priority=TaskPriority.HIGH,
            scheduled_time=1000.0,
            deadline=2000.0,
            payload={"key": "value"},
            status="pending",
        )
        assert task.id == "task-1"
        assert task.name == "test_task"
        assert task.priority == TaskPriority.HIGH
        assert task.scheduled_time == 1000.0
        assert task.deadline == 2000.0
        assert task.payload == {"key": "value"}
        assert task.status == "pending"

    def test_creation_with_minimal_fields(self) -> None:
        task = ScheduledTask(
            id="task-2",
            name="minimal",
            priority=TaskPriority.NORMAL,
            scheduled_time=500.0,
        )
        assert task.id == "task-2"
        assert task.name == "minimal"
        assert task.priority == TaskPriority.NORMAL
        assert task.scheduled_time == 500.0
        assert task.deadline is None
        assert task.payload == {}
        assert task.status == "pending"


class TestTaskScheduler:
    """Tests for TaskScheduler schedule/cancel/get operations."""

    def test_schedule_task(self) -> None:
        scheduler = TaskScheduler()
        task = ScheduledTask(
            id="t1",
            name="job",
            priority=TaskPriority.NORMAL,
            scheduled_time=time.time() + 10,
        )
        scheduler.schedule(task)
        assert scheduler.get_task("t1") is task

    def test_schedule_multiple_tasks(self) -> None:
        scheduler = TaskScheduler()
        for i in range(3):
            scheduler.schedule(
                ScheduledTask(
                    id=f"t{i}",
                    name=f"job{i}",
                    priority=TaskPriority.NORMAL,
                    scheduled_time=time.time() + 10,
                )
            )
        assert scheduler.get_task("t0") is not None
        assert scheduler.get_task("t1") is not None
        assert scheduler.get_task("t2") is not None

    def test_cancel_task(self) -> None:
        scheduler = TaskScheduler()
        task = ScheduledTask(
            id="t1",
            name="job",
            priority=TaskPriority.NORMAL,
            scheduled_time=time.time() + 10,
        )
        scheduler.schedule(task)
        scheduler.cancel("t1")
        assert scheduler.get_task("t1") is None

    def test_cancel_nonexistent_task(self) -> None:
        scheduler = TaskScheduler()
        scheduler.cancel("nonexistent")
        assert scheduler.get_task("nonexistent") is None

    def test_get_nonexistent_task(self) -> None:
        scheduler = TaskScheduler()
        assert scheduler.get_task("missing") is None

    def test_get_pending_tasks(self) -> None:
        scheduler = TaskScheduler()
        scheduler.schedule(
            ScheduledTask(
                id="t1",
                name="job1",
                priority=TaskPriority.NORMAL,
                scheduled_time=time.time() + 10,
            )
        )
        scheduler.schedule(
            ScheduledTask(
                id="t2",
                name="job2",
                priority=TaskPriority.HIGH,
                scheduled_time=time.time() + 20,
            )
        )
        pending = scheduler.get_pending_tasks()
        assert len(pending) == 2
        ids = {t.id for t in pending}
        assert ids == {"t1", "t2"}

    def test_get_pending_tasks_empty(self) -> None:
        scheduler = TaskScheduler()
        assert scheduler.get_pending_tasks() == []

    def test_get_tasks_by_priority(self) -> None:
        scheduler = TaskScheduler()
        scheduler.schedule(
            ScheduledTask(
                id="t1",
                name="job1",
                priority=TaskPriority.HIGH,
                scheduled_time=time.time() + 10,
            )
        )
        scheduler.schedule(
            ScheduledTask(
                id="t2",
                name="job2",
                priority=TaskPriority.LOW,
                scheduled_time=time.time() + 10,
            )
        )
        scheduler.schedule(
            ScheduledTask(
                id="t3",
                name="job3",
                priority=TaskPriority.HIGH,
                scheduled_time=time.time() + 10,
            )
        )
        high_tasks = scheduler.get_tasks_by_priority(TaskPriority.HIGH)
        assert len(high_tasks) == 2
        assert all(t.priority == TaskPriority.HIGH for t in high_tasks)

    def test_get_tasks_by_priority_empty(self) -> None:
        scheduler = TaskScheduler()
        assert scheduler.get_tasks_by_priority(TaskPriority.CRITICAL) == []

    def test_run_due_tasks(self) -> None:
        scheduler = TaskScheduler()
        now = time.time()
        scheduler.schedule(
            ScheduledTask(
                id="past",
                name="past_job",
                priority=TaskPriority.NORMAL,
                scheduled_time=now - 10,
            )
        )
        scheduler.schedule(
            ScheduledTask(
                id="future",
                name="future_job",
                priority=TaskPriority.NORMAL,
                scheduled_time=now + 1000,
            )
        )
        run_tasks = scheduler.run_due_tasks()
        assert len(run_tasks) == 1
        assert run_tasks[0].id == "past"

    def test_run_due_tasks_marks_status(self) -> None:
        scheduler = TaskScheduler()
        scheduler.schedule(
            ScheduledTask(
                id="t1",
                name="job",
                priority=TaskPriority.NORMAL,
                scheduled_time=time.time() - 5,
            )
        )
        scheduler.run_due_tasks()
        task = scheduler.get_task("t1")
        assert task is not None
        assert task.status == "running"

    def test_run_due_tasks_empty_when_none_due(self) -> None:
        scheduler = TaskScheduler()
        scheduler.schedule(
            ScheduledTask(
                id="t1",
                name="job",
                priority=TaskPriority.NORMAL,
                scheduled_time=time.time() + 1000,
            )
        )
        assert scheduler.run_due_tasks() == []

    def test_get_scheduler_stats(self) -> None:
        scheduler = TaskScheduler()
        scheduler.schedule(
            ScheduledTask(
                id="t1",
                name="job1",
                priority=TaskPriority.NORMAL,
                scheduled_time=time.time() + 10,
            )
        )
        scheduler.schedule(
            ScheduledTask(
                id="t2",
                name="job2",
                priority=TaskPriority.HIGH,
                scheduled_time=time.time() - 10,
            )
        )
        scheduler.run_due_tasks()
        stats = scheduler.get_scheduler_stats()
        assert stats["total_scheduled"] == 2
        assert stats["total_run"] == 1
        assert stats["pending_count"] == 1

    def test_get_scheduler_stats_empty(self) -> None:
        scheduler = TaskScheduler()
        stats = scheduler.get_scheduler_stats()
        assert stats["total_scheduled"] == 0
        assert stats["total_run"] == 0
        assert stats["pending_count"] == 0


class TestJobQueue:
    """Tests for JobQueue operations."""

    def _make_task(self, task_id: str, priority: TaskPriority = TaskPriority.NORMAL) -> ScheduledTask:
        return ScheduledTask(
            id=task_id,
            name=f"job_{task_id}",
            priority=priority,
            scheduled_time=time.time(),
        )

    def test_enqueue_dequeue(self) -> None:
        queue = JobQueue()
        task = self._make_task("t1")
        queue.enqueue(task)
        dequeued = queue.dequeue()
        assert dequeued is task

    def test_dequeue_empty_queue(self) -> None:
        queue = JobQueue()
        assert queue.dequeue() is None

    def test_peek(self) -> None:
        queue = JobQueue()
        task = self._make_task("t1")
        queue.enqueue(task)
        assert queue.peek() is task

    def test_peek_does_not_remove(self) -> None:
        queue = JobQueue()
        queue.enqueue(self._make_task("t1"))
        queue.peek()
        assert queue.get_queue_size() == 1

    def test_peek_empty_queue(self) -> None:
        queue = JobQueue()
        assert queue.peek() is None

    def test_fifo_order(self) -> None:
        queue = JobQueue()
        t1 = self._make_task("t1")
        t2 = self._make_task("t2")
        queue.enqueue(t1)
        queue.enqueue(t2)
        assert queue.dequeue() is t1
        assert queue.dequeue() is t2

    def test_get_queue_size(self) -> None:
        queue = JobQueue()
        assert queue.get_queue_size() == 0
        queue.enqueue(self._make_task("t1"))
        queue.enqueue(self._make_task("t2"))
        assert queue.get_queue_size() == 2

    def test_is_empty(self) -> None:
        queue = JobQueue()
        assert queue.is_empty() is True
        queue.enqueue(self._make_task("t1"))
        assert queue.is_empty() is False

    def test_clear_queue(self) -> None:
        queue = JobQueue()
        queue.enqueue(self._make_task("t1"))
        queue.enqueue(self._make_task("t2"))
        queue.clear_queue()
        assert queue.is_empty() is True
        assert queue.get_queue_size() == 0

    def test_get_queue_stats(self) -> None:
        queue = JobQueue()
        queue.enqueue(self._make_task("t1", TaskPriority.HIGH))
        queue.enqueue(self._make_task("t2", TaskPriority.LOW))
        stats = queue.get_queue_stats()
        assert stats["size"] == 2
        assert stats["is_empty"] is False

    def test_get_queue_stats_empty(self) -> None:
        queue = JobQueue()
        stats = queue.get_queue_stats()
        assert stats["size"] == 0
        assert stats["is_empty"] is True


class TestScheduleConfig:
    """Tests for ScheduleConfig dataclass."""

    def test_creation_with_all_fields(self) -> None:
        config = ScheduleConfig(
            max_concurrent_tasks=5,
            default_priority=TaskPriority.HIGH,
            task_timeout_seconds=30.0,
            retry_failed=True,
            max_retries=3,
        )
        assert config.max_concurrent_tasks == 5
        assert config.default_priority == TaskPriority.HIGH
        assert config.task_timeout_seconds == 30.0
        assert config.retry_failed is True
        assert config.max_retries == 3

    def test_default_values(self) -> None:
        config = ScheduleConfig()
        assert config.max_concurrent_tasks > 0
        assert config.default_priority == TaskPriority.NORMAL
        assert config.task_timeout_seconds > 0
        assert config.retry_failed is False
        assert config.max_retries >= 0
