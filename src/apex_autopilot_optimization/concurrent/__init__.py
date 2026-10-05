"""Concurrent execution utilities for apex-autopilot-optimization.

This package provides thread-safe wrappers, a thread-pool-based async
executor, and a parallel planner that runs multiple planners concurrently
and returns the best result.
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import Generic, TypeVar

from apex_autopilot_optimization.concurrent.async_executor import AsyncExecutor
from apex_autopilot_optimization.concurrent.parallel_planner import (
    ParallelPlanner,
    ThreadPoolConfig,
)
from apex_autopilot_optimization.concurrent.thread_safety import (
    ThreadSafeDict,
    ThreadSafeList,
    ThreadSafeWrapper,
)

_T = TypeVar("_T")


class ConcurrentFuture(Generic[_T]):
    """A thin wrapper around :class:`concurrent.futures.Future`.

    Provides a uniform interface for retrieving results from asynchronous
    operations, with optional timeout and exception propagation.
    """

    def __init__(self, future: Future[_T]) -> None:
        self._future = future

    def result(self, timeout: float | None = None) -> _T:
        """Return the result, blocking until available or *timeout* expires."""
        return self._future.result(timeout=timeout)

    def done(self) -> bool:
        """Return ``True`` if the future has completed."""
        return self._future.done()

    def exception(self, timeout: float | None = None) -> BaseException | None:
        """Return the exception raised by the callable, if any."""
        return self._future.exception(timeout=timeout)

    def cancel(self) -> bool:
        """Attempt to cancel the future."""
        return self._future.cancel()

    def cancelled(self) -> bool:
        """Return ``True`` if the future was cancelled."""
        return self._future.cancelled()

    def running(self) -> bool:
        """Return ``True`` if the future is currently running."""
        return self._future.running()


__all__ = [
    "AsyncExecutor",
    "ConcurrentFuture",
    "ParallelPlanner",
    "ThreadPoolConfig",
    "ThreadSafeDict",
    "ThreadSafeList",
    "ThreadSafeWrapper",
]
