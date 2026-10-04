"""Tests for the profiling module."""

import json
import time

import pytest

from apex_autopilot_optimization.profiling import (
    ProfileResult,
    export_stats,
    get_top_consumers,
    profile_context,
    profile_function,
)


class TestProfileResult:
    """Tests for the ProfileResult dataclass."""

    def test_dataclass_fields(self):
        result = ProfileResult(
            function_name="fn",
            execution_time_ms=1.5,
            call_count=3,
            timestamp=1700000000,
        )
        assert result.function_name == "fn"
        assert result.execution_time_ms == 1.5
        assert result.call_count == 3
        assert result.timestamp == 1700000000

    def test_dataclass_positional_order(self):
        result = ProfileResult("a", 0.0, 1, 0)
        assert result.function_name == "a"
        assert result.execution_time_ms == 0.0
        assert result.call_count == 1
        assert result.timestamp == 0


class TestProfileFunction:
    """Tests for the profile_function decorator."""

    def test_decorator_records_timing(self):
        @profile_function
        def add(a, b):
            return a + b

        result = add(2, 3)
        assert result == 5
        results = add.profile_results
        assert len(results) == 1
        entry = results[0]
        assert entry.function_name == "add"
        assert entry.execution_time_ms >= 0.0
        assert entry.call_count == 1
        assert isinstance(entry.timestamp, int)
        assert entry.timestamp > 0

    def test_decorator_increments_call_count(self):
        @profile_function
        def noop():
            pass

        noop()
        noop()
        noop()
        results = noop.profile_results
        assert len(results) == 3
        assert [r.call_count for r in results] == [1, 2, 3]

    def test_decorator_records_slow_call(self):
        @profile_function
        def slow():
            time.sleep(0.01)
            return "done"

        assert slow() == "done"
        results = slow.profile_results
        assert len(results) == 1
        assert results[0].execution_time_ms >= 5.0

    def test_decorator_preserves_function_metadata(self):
        @profile_function
        def documented():
            """Docstring here."""

        assert documented.__name__ == "documented"
        assert documented.__doc__ == "Docstring here."

    def test_decorator_handles_exceptions_and_records(self):
        @profile_function
        def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            boom()
        results = boom.profile_results
        assert len(results) == 1
        assert results[0].function_name == "boom"

    def test_decorator_passes_args_kwargs(self):
        @profile_function
        def combine(a, b, scale=1):
            return (a + b) * scale

        assert combine(1, 2, scale=3) == 9
        assert combine.profile_results[0].call_count == 1

    def test_decorated_functions_are_independent(self):
        @profile_function
        def first():
            return 1

        @profile_function
        def second():
            return 2

        first()
        assert len(first.profile_results) == 1
        assert len(second.profile_results) == 0
        assert first.profile_results[0].function_name == "first"


class TestProfileContext:
    """Tests for the profile_context context manager."""

    def test_context_manager_records_block(self):
        results: list[ProfileResult] = []
        with profile_context("block", results):
            total = sum(range(100))
        assert total == 4950
        assert len(results) == 1
        entry = results[0]
        assert entry.function_name == "block"
        assert entry.execution_time_ms >= 0.0
        assert entry.timestamp > 0

    def test_context_manager_times_sleep(self):
        results: list[ProfileResult] = []
        with profile_context("sleeper", results):
            time.sleep(0.02)
        assert results[0].execution_time_ms >= 10.0

    def test_context_manager_records_on_exception(self):
        results: list[ProfileResult] = []
        with pytest.raises(RuntimeError), profile_context("exploding", results):
            raise RuntimeError("fail")
        assert len(results) == 1
        assert results[0].function_name == "exploding"

    def test_context_manager_without_results_list(self):
        with profile_context("standalone") as result:
            pass
        assert result.function_name == "standalone"
        assert result.execution_time_ms >= 0.0

    def test_context_manager_reusable_name(self):
        results: list[ProfileResult] = []
        for _ in range(3):
            with profile_context("repeat", results):
                pass
        assert len(results) == 3
        assert all(r.function_name == "repeat" for r in results)


class TestGetTopConsumers:
    """Tests for get_top_consumers ranking."""

    def test_top_consumers_sorts_by_time(self):
        results = [
            ProfileResult("fast", 1.0, 1, 1),
            ProfileResult("slow", 50.0, 1, 1),
            ProfileResult("medium", 10.0, 1, 1),
        ]
        top = get_top_consumers(results, 2)
        assert [r.function_name for r in top] == ["slow", "medium"]

    def test_top_consumers_n_larger_than_list(self):
        results = [ProfileResult("only", 5.0, 1, 1)]
        assert len(get_top_consumers(results, 10)) == 1

    def test_top_consumers_empty_list(self):
        assert get_top_consumers([], 5) == []

    def test_top_consumers_n_zero(self):
        results = [ProfileResult("a", 5.0, 1, 1)]
        assert get_top_consumers(results, 0) == []

    def test_top_consumers_does_not_mutate_input(self):
        results = [
            ProfileResult("b", 2.0, 1, 1),
            ProfileResult("a", 1.0, 1, 1),
        ]
        get_top_consumers(results, 2)
        assert [r.function_name for r in results] == ["b", "a"]


class TestExportStats:
    """Tests for export_stats JSON serialization."""

    def test_export_writes_valid_json(self, tmp_path):
        results = [
            ProfileResult("fn_a", 1.25, 2, 1700000000),
            ProfileResult("fn_b", 3.5, 1, 1700000001),
        ]
        out = tmp_path / "stats.json"
        export_stats(results, str(out))

        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {
            "function_name": "fn_a",
            "execution_time_ms": 1.25,
            "call_count": 2,
            "timestamp": 1700000000,
        }
        assert data[1]["function_name"] == "fn_b"
        assert data[1]["execution_time_ms"] == 3.5

    def test_export_empty_results(self, tmp_path):
        out = tmp_path / "empty.json"
        export_stats([], str(out))
        assert json.loads(out.read_text(encoding="utf-8")) == []

    def test_export_roundtrip(self, tmp_path):
        results = [ProfileResult("x", 0.5, 7, 123)]
        out = tmp_path / "rt.json"
        export_stats(results, str(out))
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded[0]["function_name"] == results[0].function_name
        assert loaded[0]["call_count"] == results[0].call_count
        assert loaded[0]["timestamp"] == results[0].timestamp
        assert loaded[0]["execution_time_ms"] == results[0].execution_time_ms

    def test_export_overwrites_existing_file(self, tmp_path):
        out = tmp_path / "stats.json"
        out.write_text('{"stale": true}', encoding="utf-8")
        export_stats([ProfileResult("fresh", 1.0, 1, 1)], str(out))
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "stale" not in data[0]
        assert data[0]["function_name"] == "fresh"


class TestProfilingIntegration:
    """End-to-end checks combining decorator, context manager, and ranking."""

    def test_decorator_results_feed_top_consumers(self):
        @profile_function
        def fast():
            pass

        @profile_function
        def slow():
            time.sleep(0.02)

        fast()
        slow()
        combined = fast.profile_results + slow.profile_results
        top = get_top_consumers(combined, 1)
        assert top[0].function_name == "slow"

    def test_context_results_feed_export(self, tmp_path):
        results: list[ProfileResult] = []
        with profile_context("block", results):
            pass
        out = tmp_path / "ctx.json"
        export_stats(results, str(out))
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data[0]["function_name"] == "block"
