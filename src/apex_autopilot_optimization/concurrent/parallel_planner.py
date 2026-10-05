"""Parallel planner that runs multiple planners concurrently."""

from __future__ import annotations

from concurrent.futures import Future, as_completed
from dataclasses import dataclass
from typing import Any, Protocol

from apex_autopilot_optimization.concurrent.async_executor import AsyncExecutor


class _PlannerLike(Protocol):
    """Protocol for objects that have a ``plan`` method."""

    def plan(self, problem: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class ThreadPoolConfig:
    """Configuration for the thread pool used by :class:`ParallelPlanner`."""

    max_workers: int = 4
    thread_name_prefix: str = "apex-worker"
    timeout_seconds: float = 30.0


class ParallelPlanner:
    """Runs multiple planners concurrently and returns the best result.

    Each planner's ``plan`` method is submitted to a thread pool.  Results
    are collected as they complete:

    * If at least one planner succeeds, the result with the **lowest cost**
      is returned.
    * If all planners fail, ``None`` is returned.

    A planner result is considered successful when it is not ``None`` and
    not an instance of :class:`Exception`.  The cost is extracted from the
    ``cost`` attribute of the result; if the attribute is absent the cost
    defaults to ``0.0``.
    """

    def __init__(
        self,
        planners: list[_PlannerLike],
        config: ThreadPoolConfig | None = None,
    ) -> None:
        self._planners = list(planners)
        self._config = config or ThreadPoolConfig()

    def plan(self, problem: Any) -> Any:
        """Run all planners concurrently and return the best successful result.

        Returns ``None`` when *planners* is empty or every planner fails.
        """
        if not self._planners:
            return None

        executor = AsyncExecutor(
            max_workers=self._config.max_workers,
            thread_name_prefix=self._config.thread_name_prefix,
        )
        try:
            futures: list[Future[Any]] = [executor.submit(p.plan, problem) for p in self._planners]
            results: list[Any] = []
            for future in as_completed(futures, timeout=self._config.timeout_seconds):
                try:
                    result = future.result()
                except Exception:
                    continue
                if self._is_success(result):
                    results.append(result)

            if not results:
                return None

            return min(results, key=self._extract_cost)
        finally:
            executor.shutdown(wait=True)

    @staticmethod
    def _is_success(result: Any) -> bool:
        """Return ``True`` if *result* represents a successful planner outcome.

        A result is considered a failure when it is ``None``, an
        :class:`Exception`, or has a ``success`` attribute that is ``False``.
        """
        if result is None or isinstance(result, Exception):
            return False
        success = getattr(result, "success", True)
        return bool(success)

    @staticmethod
    def _extract_cost(result: Any) -> float:
        """Extract a numeric cost from a planner result.

        Falls back to ``0.0`` when the result has no ``cost`` attribute.
        """
        cost = getattr(result, "cost", 0.0)
        if isinstance(cost, int | float):
            return float(cost)
        return 0.0
