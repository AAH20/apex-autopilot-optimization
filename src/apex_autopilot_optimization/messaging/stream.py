"""Stream processing implementation."""
from __future__ import annotations

from typing import Any, Callable, Iterable


class StreamProcessor:
    """Process streams with windowing, aggregation, and filtering."""

    def __init__(self) -> None:
        self._processed = 0
        self._windows = 0

    def process_stream(
        self, stream: Iterable[Any], func: Callable[[Any], Any]
    ) -> list[Any]:
        """Apply a function to each item in the stream."""
        result = [func(item) for item in stream]
        self._processed += len(result)
        return result

    def window_by_time(
        self, events: Iterable[dict[str, Any]], window_size: float
    ) -> list[list[dict[str, Any]]]:
        """Group events into time-based windows."""
        events_list = list(events)
        if not events_list:
            return []
        windows: list[list[dict[str, Any]]] = []
        current_window: list[dict[str, Any]] = [events_list[0]]
        window_start = events_list[0]["timestamp"]
        for event in events_list[1:]:
            if event["timestamp"] - window_start <= window_size:
                current_window.append(event)
            else:
                windows.append(current_window)
                current_window = [event]
                window_start = event["timestamp"]
        windows.append(current_window)
        self._windows += len(windows)
        return windows

    def window_by_count(
        self, items: Iterable[Any], window_size: int
    ) -> list[list[Any]]:
        """Group items into fixed-size windows."""
        items_list = list(items)
        windows = [
            items_list[i : i + window_size]
            for i in range(0, len(items_list), window_size)
        ]
        self._windows += len(windows)
        return windows

    def aggregate(
        self, values: Iterable[Any], aggregator: Callable[[list[Any]], Any]
    ) -> Any:
        """Aggregate values using the provided function."""
        return aggregator(list(values))

    def filter_stream(
        self, stream: Iterable[Any], predicate: Callable[[Any], bool]
    ) -> list[Any]:
        """Filter stream items by predicate."""
        return [item for item in stream if predicate(item)]

    def get_stream_stats(self) -> dict[str, int]:
        """Get stream processing statistics."""
        return {"processed": self._processed, "windows": self._windows}
