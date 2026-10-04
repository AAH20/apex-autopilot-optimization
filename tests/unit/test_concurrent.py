"""Tests for the concurrent execution package."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from typing import Any

import pytest

from apex_autopilot_optimization.concurrent import (
    AsyncExecutor,
    ConcurrentFuture,
    ParallelPlanner,
    ThreadPoolConfig,
    ThreadSafeDict,
    ThreadSafeList,
    ThreadSafeWrapper,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePlanner:
    """Minimal planner stub for ParallelPlanner tests."""

    def __init__(self, name: str, result: Any, delay: float = 0.0) -> None:
        self.name = name
        self._result = result
        self._delay = delay
        self.call_count = 0

    def plan(self, problem: Any) -> Any:
        self.call_count += 1
        if self._delay:
            time.sleep(self._delay)
        return self._result


class _SuccessResult:
    def __init__(self, cost: float, name: str = "") -> None:
        self.cost = cost
        self.name = name


class _FailureResult:
    success = False


# ---------------------------------------------------------------------------
# ThreadPoolConfig
# ---------------------------------------------------------------------------


class TestThreadPoolConfig:
    """Tests for ThreadPoolConfig dataclass."""

    def test_defaults(self) -> None:
        config = ThreadPoolConfig()
        assert config.max_workers == 4
        assert config.thread_name_prefix == "apex-worker"
        assert config.timeout_seconds == 30.0

    def test_custom_values(self) -> None:
        config = ThreadPoolConfig(max_workers=8, thread_name_prefix="custom", timeout_seconds=5.0)
        assert config.max_workers == 8
        assert config.thread_name_prefix == "custom"
        assert config.timeout_seconds == 5.0


# ---------------------------------------------------------------------------
# ParallelPlanner
# ---------------------------------------------------------------------------


class TestParallelPlanner:
    """Tests for ParallelPlanner."""

    def test_returns_first_successful_result(self) -> None:
        """When one planner succeeds and another fails, the successful result is returned."""
        success = _SuccessResult(cost=1.0, name="fast")
        fast = _FakePlanner("fast", success, delay=0.01)
        slow_fail = _FakePlanner("slow_fail", _FailureResult(), delay=0.05)

        planner = ParallelPlanner([fast, slow_fail])
        result = planner.plan("problem")

        assert isinstance(result, _SuccessResult)
        assert result.cost == 1.0
        assert result.name == "fast"

    def test_returns_best_cost_when_all_succeed(self) -> None:
        """When all planners succeed, the one with the lowest cost is returned."""
        r1 = _SuccessResult(cost=10.0, name="expensive")
        r2 = _SuccessResult(cost=3.0, name="cheap")
        r3 = _SuccessResult(cost=7.0, name="medium")

        p1 = _FakePlanner("p1", r1)
        p2 = _FakePlanner("p2", r2)
        p3 = _FakePlanner("p3", r3)

        planner = ParallelPlanner([p1, p2, p3])
        result = planner.plan("problem")

        assert isinstance(result, _SuccessResult)
        assert result.cost == 3.0
        assert result.name == "cheap"

    def test_handles_all_failures(self) -> None:
        """When all planners fail, plan returns None."""
        p1 = _FakePlanner("p1", _FailureResult())
        p2 = _FakePlanner("p2", _FailureResult())

        planner = ParallelPlanner([p1, p2])
        result = planner.plan("problem")

        assert result is None

    def test_single_planner_success(self) -> None:
        ok = _SuccessResult(cost=5.0)
        p = _FakePlanner("only", ok)
        planner = ParallelPlanner([p])
        result = planner.plan("problem")
        assert isinstance(result, _SuccessResult)
        assert result.cost == 5.0

    def test_single_planner_failure(self) -> None:
        p = _FakePlanner("only", _FailureResult())
        planner = ParallelPlanner([p])
        assert planner.plan("problem") is None

    def test_empty_planner_list(self) -> None:
        planner = ParallelPlanner([])
        assert planner.plan("problem") is None

    def test_uses_config(self) -> None:
        config = ThreadPoolConfig(max_workers=2)
        p = _FakePlanner("p", _SuccessResult(cost=1.0))
        planner = ParallelPlanner([p], config=config)
        result = planner.plan("problem")
        assert isinstance(result, _SuccessResult)

    def test_planners_called_concurrently(self) -> None:
        """Verify that planners are actually invoked (call_count > 0)."""
        p1 = _FakePlanner("p1", _SuccessResult(cost=1.0))
        p2 = _FakePlanner("p2", _SuccessResult(cost=2.0))
        planner = ParallelPlanner([p1, p2])
        planner.plan("problem")
        assert p1.call_count == 1
        assert p2.call_count == 1


# ---------------------------------------------------------------------------
# AsyncExecutor
# ---------------------------------------------------------------------------


class TestAsyncExecutor:
    """Tests for AsyncExecutor."""

    def test_submit_and_collect(self) -> None:
        """submit returns a Future; result can be collected."""
        executor = AsyncExecutor(max_workers=2)
        try:
            future = executor.submit(lambda x: x * 2, 21)
            assert isinstance(future, Future)
            assert future.result(timeout=5) == 42
        finally:
            executor.shutdown()

    def test_submit_with_exception(self) -> None:
        """Exceptions raised in the worker propagate on result()."""
        executor = AsyncExecutor(max_workers=1)
        try:
            def boom() -> None:
                raise ValueError("kaboom")

            future = executor.submit(boom)
            with pytest.raises(ValueError, match="kaboom"):
                future.result(timeout=5)
        finally:
            executor.shutdown()

    def test_map(self) -> None:
        """map applies func to all items and returns results in order."""
        executor = AsyncExecutor(max_workers=4)
        try:
            results = executor.map(lambda x: x ** 2, [1, 2, 3, 4, 5])
            assert results == [1, 4, 9, 16, 25]
        finally:
            executor.shutdown()

    def test_map_empty(self) -> None:
        executor = AsyncExecutor(max_workers=2)
        try:
            assert executor.map(lambda x: x, []) == []
        finally:
            executor.shutdown()

    def test_map_with_delay(self) -> None:
        """map with a slow function still returns correct ordered results."""
        executor = AsyncExecutor(max_workers=3)
        try:
            def slow_square(x: int) -> int:
                time.sleep(0.01)
                return x * x

            results = executor.map(slow_square, [3, 1, 2])
            assert results == [9, 1, 4]
        finally:
            executor.shutdown()

    def test_shutdown_idempotent(self) -> None:
        """Calling shutdown multiple times does not raise."""
        executor = AsyncExecutor(max_workers=1)
        executor.shutdown()
        executor.shutdown()  # should not raise

    def test_multiple_submits(self) -> None:
        """Multiple submits all complete."""
        executor = AsyncExecutor(max_workers=4)
        try:
            futures = [executor.submit(lambda x, y: x + y, i, i) for i in range(10)]
            results = [f.result(timeout=5) for f in futures]
            assert results == [i + i for i in range(10)]
        finally:
            executor.shutdown()


# ---------------------------------------------------------------------------
# ThreadSafeWrapper
# ---------------------------------------------------------------------------


class TestThreadSafeWrapper:
    """Tests for ThreadSafeWrapper."""

    def test_prevents_race_conditions(self) -> None:
        """Concurrent increments on a wrapped counter produce the correct total."""
        class Counter:
            def __init__(self) -> None:
                self.value = 0

            def increment(self) -> None:
                self.value += 1

        counter = ThreadSafeWrapper(Counter())
        num_threads = 10
        increments_per_thread = 100

        threads = [
            threading.Thread(target=lambda: [counter.increment() for _ in range(increments_per_thread)])
            for _ in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter.value == num_threads * increments_per_thread

    def test_wrapped_object_methods(self) -> None:
        """Methods on the wrapped object are accessible."""
        class Greeter:
            def greet(self, name: str) -> str:
                return f"Hello, {name}"

        wrapped = ThreadSafeWrapper(Greeter())
        assert wrapped.greet("World") == "Hello, World"

    def test_wrapped_object_attributes(self) -> None:
        """Attributes on the wrapped object are accessible."""
        class Config:
            def __init__(self) -> None:
                self.setting = 42

        wrapped = ThreadSafeWrapper(Config())
        assert wrapped.setting == 42
        wrapped.setting = 99
        assert wrapped.setting == 99


# ---------------------------------------------------------------------------
# ThreadSafeDict
# ---------------------------------------------------------------------------


class TestThreadSafeDict:
    """Tests for ThreadSafeDict."""

    def test_basic_operations(self) -> None:
        d: ThreadSafeDict[str, int] = ThreadSafeDict()
        d["a"] = 1
        d["b"] = 2
        assert d["a"] == 1
        assert d["b"] == 2
        assert len(d) == 2

    def test_get_with_default(self) -> None:
        d: ThreadSafeDict[str, int] = ThreadSafeDict()
        assert d.get("missing") is None
        assert d.get("missing", 42) == 42

    def test_contains(self) -> None:
        d: ThreadSafeDict[str, int] = ThreadSafeDict()
        d["x"] = 10
        assert "x" in d
        assert "y" not in d

    def test_delete(self) -> None:
        d: ThreadSafeDict[str, int] = ThreadSafeDict()
        d["a"] = 1
        del d["a"]
        assert "a" not in d

    def test_concurrent_writes(self) -> None:
        """Multiple threads writing to ThreadSafeDict do not lose data."""
        d: ThreadSafeDict[int, int] = ThreadSafeDict()
        num_threads = 10
        items_per_thread = 100

        def writer(thread_id: int) -> None:
            for i in range(items_per_thread):
                d[thread_id * items_per_thread + i] = i

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(d) == num_threads * items_per_thread

    def test_update_and_keys(self) -> None:
        d: ThreadSafeDict[str, int] = ThreadSafeDict()
        d.update({"a": 1, "b": 2})
        assert set(d.keys()) == {"a", "b"}
        assert set(d.values()) == {1, 2}


# ---------------------------------------------------------------------------
# ThreadSafeList
# ---------------------------------------------------------------------------


class TestThreadSafeList:
    """Tests for ThreadSafeList."""

    def test_basic_operations(self) -> None:
        lst: ThreadSafeList[int] = ThreadSafeList()
        lst.append(1)
        lst.append(2)
        lst.append(3)
        assert len(lst) == 3
        assert lst[0] == 1
        assert lst[2] == 3

    def test_extend(self) -> None:
        lst: ThreadSafeList[int] = ThreadSafeList()
        lst.extend([1, 2, 3])
        assert list(lst) == [1, 2, 3]

    def test_pop(self) -> None:
        lst: ThreadSafeList[int] = ThreadSafeList([1, 2, 3])
        assert lst.pop() == 3
        assert len(lst) == 2

    def test_concurrent_appends(self) -> None:
        """Multiple threads appending to ThreadSafeList do not lose items."""
        lst: ThreadSafeList[int] = ThreadSafeList()
        num_threads = 10
        items_per_thread = 100

        def appender(thread_id: int) -> None:
            for i in range(items_per_thread):
                lst.append(thread_id * items_per_thread + i)

        threads = [threading.Thread(target=appender, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(lst) == num_threads * items_per_thread

    def test_iteration(self) -> None:
        lst: ThreadSafeList[int] = ThreadSafeList([1, 2, 3])
        collected = [x for x in lst]
        assert collected == [1, 2, 3]


# ---------------------------------------------------------------------------
# ConcurrentFuture
# ---------------------------------------------------------------------------


class TestConcurrentFuture:
    """Tests for ConcurrentFuture wrapper."""

    def test_wraps_concurrent_future(self) -> None:
        """ConcurrentFuture wraps a concurrent.futures.Future."""
        executor = AsyncExecutor(max_workers=1)
        try:
            raw = executor.submit(lambda: 42)
            cf = ConcurrentFuture(raw)
            assert cf.result(timeout=5) == 42
        finally:
            executor.shutdown()

    def test_concurrent_future_done(self) -> None:
        executor = AsyncExecutor(max_workers=1)
        try:
            raw = executor.submit(lambda: "done")
            cf = ConcurrentFuture(raw)
            assert cf.done() is True
        finally:
            executor.shutdown()

    def test_concurrent_future_exception(self) -> None:
        executor = AsyncExecutor(max_workers=1)
        try:
            def fail() -> None:
                raise RuntimeError("nope")

            raw = executor.submit(fail)
            cf = ConcurrentFuture(raw)
            with pytest.raises(RuntimeError, match="nope"):
                cf.result(timeout=5)
        finally:
            executor.shutdown()
