"""Tests for the memory profiling module."""

import time
import tracemalloc

import pytest

from apex_autopilot_optimization.memory import (
    MemoryLeakDetector,
    MemoryProfileResult,
    MemorySnapshot,
    compare_snapshots,
    profile_memory,
    take_snapshot,
)


def _snap(current: int, peak: int | None = None, ts: int = 0) -> MemorySnapshot:
    return MemorySnapshot(
        timestamp=ts,
        peak_bytes=peak if peak is not None else current,
        current_bytes=current,
        top_allocations=[],
    )


class TestMemorySnapshot:
    """Tests for the MemorySnapshot dataclass."""

    def test_snapshot_fields(self):
        snap = MemorySnapshot(
            timestamp=123,
            peak_bytes=2048,
            current_bytes=1024,
            top_allocations=[{"file": "a.py", "line": 1, "size_bytes": 10, "count": 1}],
        )
        assert snap.timestamp == 123
        assert snap.peak_bytes == 2048
        assert snap.current_bytes == 1024
        assert len(snap.top_allocations) == 1

    def test_snapshot_defaults(self):
        snap = MemorySnapshot(timestamp=1, peak_bytes=2, current_bytes=2)
        assert snap.top_allocations == []

    def test_snapshot_peak_not_below_current(self):
        # A well-formed snapshot never has peak below current.
        snap = _snap(current=512, peak=512)
        assert snap.peak_bytes >= snap.current_bytes


class TestTakeSnapshot:
    """Tests for take_snapshot()."""

    def test_snapshot_activates_tracing(self):
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        snap = take_snapshot()
        try:
            assert tracemalloc.is_tracing() is True
        finally:
            tracemalloc.stop()
        assert isinstance(snap, MemorySnapshot)

    def test_snapshot_field_ranges(self):
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        try:
            snap = take_snapshot()
        finally:
            tracemalloc.stop()
        assert snap.timestamp > 0
        assert snap.peak_bytes >= 0
        assert snap.current_bytes >= 0
        assert snap.peak_bytes >= snap.current_bytes

    def test_snapshot_top_allocations_structure(self):
        try:
            _ = [bytearray(1024) for _ in range(8)]
            snap = take_snapshot(top_n=3)
        finally:
            tracemalloc.stop()
        assert isinstance(snap.top_allocations, list)
        assert len(snap.top_allocations) <= 3
        for entry in snap.top_allocations:
            assert isinstance(entry, dict)
            assert {"file", "line", "size_bytes", "count"} <= set(entry.keys())
            assert isinstance(entry["size_bytes"], int)
            assert entry["size_bytes"] >= 0
            assert isinstance(entry["count"], int)
            assert entry["count"] > 0

    def test_snapshot_monotonic_traceable_growth(self):
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        hold = None
        try:
            before = take_snapshot()
            hold = [bytearray(64 * 1024) for _ in range(20)]
            after = take_snapshot()
            assert after.current_bytes > before.current_bytes
        finally:
            tracemalloc.stop()
            del hold


class TestCompareSnapshots:
    """Tests for compare_snapshots()."""

    def test_positive_growth(self):
        before = _snap(current=1000, peak=1000)
        after = _snap(current=2500, peak=2500)
        result = compare_snapshots(before, after)
        assert result["peak_delta_bytes"] == 1500
        assert result["current_delta_bytes"] == 1500
        assert result["growth_rate"] == pytest.approx(1.5)

    def test_zero_base_growth_rate(self):
        before = _snap(current=0, peak=0)
        after = _snap(current=100, peak=100)
        result = compare_snapshots(before, after)
        assert result["growth_rate"] == 0.0
        assert result["current_delta_bytes"] == 100

    def test_negative_growth(self):
        before = _snap(current=4000, peak=4000)
        after = _snap(current=1000, peak=4000)
        result = compare_snapshots(before, after)
        assert result["current_delta_bytes"] == -3000
        assert result["growth_rate"] == pytest.approx(-0.75)
        assert result["peak_delta_bytes"] == 0

    def test_no_growth(self):
        before = _snap(current=777, peak=999)
        after = _snap(current=777, peak=999)
        result = compare_snapshots(before, after)
        assert result["peak_delta_bytes"] == 0
        assert result["current_delta_bytes"] == 0
        assert result["growth_rate"] == 0.0

    def test_result_keys(self):
        result = compare_snapshots(_snap(current=1, peak=1), _snap(current=2, peak=2))
        assert set(result.keys()) == {"peak_delta_bytes", "current_delta_bytes", "growth_rate"}


class TestProfileMemory:
    """Tests for the profile_memory decorator."""

    def test_profile_result_fields(self):
        @profile_memory
        def allocate():
            return [bytearray(1024) for _ in range(64)]

        try:
            result = allocate()
        finally:
            tracemalloc.stop()
        assert isinstance(result, MemoryProfileResult)
        assert result.function_name == "allocate"
        assert result.peak_bytes > 0
        assert result.execution_time_ms >= 0.0

    def test_profile_preserves_metadata(self):
        @profile_memory
        def named():
            """Docstring survives wrapping."""

        assert named.__name__ == "named"
        assert named.__doc__ == "Docstring survives wrapping."

    def test_profile_resets_peak_when_already_tracing(self):
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        tracemalloc.start()
        try:
            _ = [bytearray(256 * 1024) for _ in range(64)]  # large pre-existing peak
            big_peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert big_peak > 0

        @profile_memory
        def small():
            return [bytearray(128) for _ in range(4)]

        try:
            result = small()
        finally:
            tracemalloc.stop()
        # peak reflects only the profiled call, not the pre-existing peak
        assert result.peak_bytes < big_peak

    def test_profile_stops_tracing_if_it_started_it(self):
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        try:

            @profile_memory
            def f():
                return None

            result = f()
            assert result.function_name == "f"
            assert tracemalloc.is_tracing() is False
        finally:
            tracemalloc.stop()

    def test_profile_times_slow_function(self):
        @profile_memory
        def slow():
            time.sleep(0.01)
            return None

        try:
            result = slow()
        finally:
            tracemalloc.stop()
        assert result.execution_time_ms >= 5.0


class TestMemoryLeakDetector:
    """Tests for MemoryLeakDetector."""

    def test_init_validation(self):
        with pytest.raises(ValueError):
            MemoryLeakDetector(window=1)
        with pytest.raises(ValueError):
            MemoryLeakDetector(threshold=-0.1)
        ok = MemoryLeakDetector(threshold=0.0, window=2)
        assert ok.snapshot_count == 0

    def test_detects_leak_above_threshold(self):
        detector = MemoryLeakDetector(threshold=1.0, window=3)
        detector.add_snapshot(_snap(current=1000, peak=1000, ts=1))
        detector.add_snapshot(_snap(current=2500, peak=2500, ts=2))
        assert detector.last_growth_rate() == pytest.approx(1.5)
        assert detector.detect_leak() is True

    def test_no_leak_below_threshold(self):
        detector = MemoryLeakDetector(threshold=2.0, window=3)
        detector.add_snapshot(_snap(current=1000, peak=1000, ts=1))
        detector.add_snapshot(_snap(current=1500, peak=1500, ts=2))
        assert detector.detect_leak() is False

    def test_no_leak_without_snapshots(self):
        detector = MemoryLeakDetector(threshold=0.5, window=3)
        assert detector.detect_leak() is False
        assert detector.last_growth_rate() is None

    def test_no_leak_with_single_snapshot(self):
        detector = MemoryLeakDetector(threshold=0.5, window=3)
        detector.add_snapshot(_snap(current=1000, peak=1000))
        assert detector.detect_leak() is False
        assert detector.last_growth_rate() is None

    def test_window_is_bounded(self):
        detector = MemoryLeakDetector(threshold=0.5, window=3)
        for i in range(10):
            detector.add_snapshot(_snap(current=1000 + i, peak=1000 + i, ts=i))
        assert detector.snapshot_count == 3

    def test_window_uses_oldest_and_newest(self):
        detector = MemoryLeakDetector(threshold=0.5, window=3)
        for i in range(5):
            detector.add_snapshot(_snap(current=1000 + i * 100, peak=1000 + i * 100, ts=i))
        assert detector.snapshot_count == 3
        # retained window is [1200, 1300, 1400]; growth from oldest to newest
        assert detector.last_growth_rate() == pytest.approx(200 / 1200)

    def test_reset_clears_snapshots(self):
        detector = MemoryLeakDetector(threshold=0.5, window=3)
        detector.add_snapshot(_snap(current=1000, peak=1000))
        detector.reset()
        assert detector.snapshot_count == 0
        assert detector.detect_leak() is False

    def test_real_snapshot_integration(self):
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        hold = None
        try:
            tracemalloc.start()
            detector = MemoryLeakDetector(threshold=0.01, window=2)
            detector.add_snapshot(take_snapshot())
            hold = [bytearray(32 * 1024) for _ in range(32)]
            detector.add_snapshot(take_snapshot())
            assert detector.snapshot_count == 2
            assert detector.detect_leak() is True
            assert detector.last_growth_rate() is not None
        finally:
            tracemalloc.stop()
            del hold
