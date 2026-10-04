"""Performance profiling utilities for apex-autopilot-optimization.

Provides lightweight, production-safe profiling helpers:
- ``profile_function``: decorator recording execution time and call counts.
- ``profile_context``: context manager timing a block of code.
- ``ProfileResult``: dataclass capturing a single profile measurement.
- ``get_top_consumers``: rank profile results by execution time.
- ``export_stats``: persist profile results as JSON.
"""

from __future__ import annotations

import contextlib
import functools
import json
import time
import time as _time
from dataclasses import asdict, dataclass
from typing import Callable, Generator, TypeVar

F = TypeVar("F", bound=Callable[..., object])

__all__ = [
    "ProfileResult",
    "export_stats",
    "get_top_consumers",
    "profile_context",
    "profile_function",
]


@dataclass
class ProfileResult:
    """A single profile measurement for a function or code block.

    Attributes:
        function_name: Name of the profiled function or block.
        execution_time_ms: Wall-clock execution time in milliseconds.
        call_count: Number of times the target has been profiled.
        timestamp: POSIX timestamp (seconds since epoch) of the measurement.
    """

    function_name: str
    execution_time_ms: float
    call_count: int
    timestamp: int


def profile_function(func: F) -> F:
    """Decorator that records execution time and call count of a function.

    The wrapped function gains a ``profile_results`` attribute holding the list
    of :class:`ProfileResult` entries accumulated across calls. Each call
    appends one result; the result is also returned on the function's normal
    path and propagated on exceptions (the measurement is still recorded).

    Args:
        func: The function to profile.

    Returns:
        The wrapped function with profiling instrumentation.
    """
    call_count = 0
    results: list[ProfileResult] = []

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            results.append(
                ProfileResult(
                    function_name=func.__name__,
                    execution_time_ms=elapsed_ms,
                    call_count=call_count,
                    timestamp=int(_time.time()),
                )
            )

    wrapper.profile_results = results  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


@contextlib.contextmanager
def profile_context(name: str, results: list[ProfileResult] | None = None) -> Generator[ProfileResult, None, None]:
    """Context manager that records the execution time of a code block.

    Args:
        name: Label stored in ``ProfileResult.function_name``.
        results: Optional list to which the recorded :class:`ProfileResult`
            will be appended. When ``None`` the result is only yielded.

    Yields:
        The :class:`ProfileResult` for the block once it completes. The
        yielded instance is yielded before its final timing fields are
        populated; use ``results`` (or the yielded value after the block)
        for the finished measurement.

    Raises:
        Exception: Re-raises any exception raised by the wrapped block after
            recording the measurement.
    """
    start = time.perf_counter()
    result = ProfileResult(
        function_name=name,
        execution_time_ms=0.0,
        call_count=1,
        timestamp=int(_time.time()),
    )
    try:
        yield result
    finally:
        result.execution_time_ms = (time.perf_counter() - start) * 1000.0
        if results is not None:
            results.append(result)


def get_top_consumers(results: list[ProfileResult], n: int) -> list[ProfileResult]:
    """Return the top ``n`` profile results ranked by execution time.

    Sorting is by ``execution_time_ms`` in descending order. Ties break by
    the order results appear in the input (stable sort).

    Args:
        results: Profile results to rank.
        n: Maximum number of results to return. Values larger than
            ``len(results)`` return the full sorted list; negative values
            behave like ``0``.

    Returns:
        A new list containing at most ``n`` results, slowest first.
    """
    ordered = sorted(results, key=lambda r: r.execution_time_ms, reverse=True)
    return ordered[: max(n, 0)]


def export_stats(results: list[ProfileResult], path: str) -> None:
    """Export profile results to a JSON file.

    The file contains a list of serialized :class:`ProfileResult` dicts with
    keys ``function_name``, ``execution_time_ms``, ``call_count`` and
    ``timestamp``. Existing files at ``path`` are overwritten.

    Args:
        results: Profile results to export.
        path: Destination file path (str or os.PathLike).

    Raises:
        TypeError: If ``results`` contains non-ProfileResult items.
        OSError: If the file cannot be written.
    """
    payload = [asdict(r) for r in results]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
