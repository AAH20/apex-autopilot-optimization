"""Async executor for running callables in a thread pool."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Iterable, TypeVar

_T = TypeVar("_T")
_R = TypeVar("_R")


class AsyncExecutor:
    """A thin wrapper around :class:`~concurrent.futures.ThreadPoolExecutor`.

    Provides ``submit``, ``map``, and ``shutdown`` for fire-and-forget and
    batch execution of callables in a managed thread pool.
    """

    def __init__(
        self,
        max_workers: int = 4,
        thread_name_prefix: str = "apex-async",
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )

    def submit(self, func: Callable[..., _R], *args: Any, **kwargs: Any) -> Future[_R]:
        """Submit *func* for execution with the given arguments.

        Returns a :class:`~concurrent.futures.Future` representing the result.
        """
        return self._executor.submit(func, *args, **kwargs)

    def map(self, func: Callable[[_T], _R], items: Iterable[_T]) -> list[_R]:
        """Apply *func* to each item in *items* and return results in order."""
        return list(self._executor.map(func, items))

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the executor, optionally waiting for pending tasks."""
        self._executor.shutdown(wait=wait)
