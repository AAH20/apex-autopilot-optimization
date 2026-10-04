"""Memory profiling utilities for apex-autopilot-optimization.

Provides tracemalloc-based memory snapshots, snapshot comparison, a
function-level memory profiling decorator, and a leak detector that
flags sustained allocation growth across multiple snapshots.
"""

from __future__ import annotations

import functools
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MemoryLeakDetector",
    "MemoryProfileResult",
    "MemorySnapshot",
    "compare_snapshots",
    "profile_memory",
    "take_snapshot",
]

DEFAULT_TOP_N = 5


@dataclass
class MemorySnapshot:
    """Point-in-time memory usage snapshot captured via tracemalloc."""

    timestamp: int
    peak_bytes: int
    current_bytes: int
    top_allocations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MemoryProfileResult:
    """Outcome of profiling a single function's memory usage."""

    function_name: str
    peak_bytes: int
    execution_time_ms: float


def _growth_rate(base_bytes: int, current_bytes: int) -> float:
    """Fractional growth of current over base; 0.0 when base is zero."""
    if base_bytes <= 0:
        return 0.0
    return (current_bytes - base_bytes) / base_bytes


def take_snapshot(top_n: int = DEFAULT_TOP_N) -> MemorySnapshot:
    """Capture a memory snapshot using tracemalloc.

    Starts tracemalloc tracing if it is not already active. The snapshot
    records the current epoch, traced peak/current byte counts, and the
    top ``top_n`` allocation sites by size.
    """
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    current, peak = tracemalloc.get_traced_memory()
    raw = tracemalloc.take_snapshot()
    top: list[dict[str, Any]] = []
    for stat in raw.statistics("lineno")[:top_n]:
        frame = stat.traceback[0] if stat.traceback else None
        top.append(
            {
                "file": frame.filename if frame is not None else "<unknown>",
                "line": frame.lineno if frame is not None else 0,
                "size_bytes": stat.size,
                "count": stat.count,
            }
        )
    return MemorySnapshot(
        timestamp=int(time.time()),
        peak_bytes=peak,
        current_bytes=current,
        top_allocations=top,
    )


def compare_snapshots(before: MemorySnapshot, after: MemorySnapshot) -> dict[str, Any]:
    """Compare two snapshots and report deltas and fractional growth.

    Returns a dict with ``peak_delta_bytes``, ``current_delta_bytes`` and
    ``growth_rate`` (fractional growth of current bytes; 0.0 when the
    before snapshot held no traced bytes).
    """
    return {
        "peak_delta_bytes": after.peak_bytes - before.peak_bytes,
        "current_delta_bytes": after.current_bytes - before.current_bytes,
        "growth_rate": _growth_rate(before.current_bytes, after.current_bytes),
    }


def profile_memory(func: Callable[..., Any]) -> Callable[..., MemoryProfileResult]:
    """Decorate ``func`` so calling it returns a MemoryProfileResult.

    The wrapped function's peak traced memory and wall-clock execution
    time are measured; the wrapped function's own return value is
    discarded in favor of the profile result.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> MemoryProfileResult:
        was_tracing = tracemalloc.is_tracing()
        if was_tracing:
            tracemalloc.reset_peak()
        else:
            tracemalloc.start()
        start = time.perf_counter()
        try:
            func(*args, **kwargs)
        finally:
            current, peak = tracemalloc.get_traced_memory()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if not was_tracing:
                tracemalloc.stop()
        return MemoryProfileResult(
            function_name=func.__name__,
            peak_bytes=peak,
            execution_time_ms=elapsed_ms,
        )

    return wrapper


class MemoryLeakDetector:
    """Detect memory leaks from sustained allocation growth.

    Keeps a bounded window of recent snapshots and reports a leak when
    the fractional growth of current bytes across the window exceeds
    ``threshold``.
    """

    def __init__(self, threshold: float = 1.0, window: int = 3) -> None:
        if threshold < 0:
            raise ValueError("threshold must be non-negative")
        if window < 2:
            raise ValueError("window must be at least 2")
        self.threshold = threshold
        self.window = window
        self._snapshots: list[MemorySnapshot] = []

    @property
    def snapshot_count(self) -> int:
        """Number of snapshots currently retained."""
        return len(self._snapshots)

    def add_snapshot(self, snapshot: MemorySnapshot) -> None:
        """Record a snapshot, retaining at most ``window`` of them."""
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self.window:
            del self._snapshots[: len(self._snapshots) - self.window]

    def last_growth_rate(self) -> float | None:
        """Fractional current-bytes growth across the retained window."""
        if len(self._snapshots) < 2:
            return None
        return _growth_rate(self._snapshots[0].current_bytes, self._snapshots[-1].current_bytes)

    def detect_leak(self) -> bool:
        """True when growth across the retained window exceeds threshold."""
        rate = self.last_growth_rate()
        if rate is None:
            return False
        return rate > self.threshold

    def reset(self) -> None:
        """Discard all retained snapshots."""
        self._snapshots.clear()
