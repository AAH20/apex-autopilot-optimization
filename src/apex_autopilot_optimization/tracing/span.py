"""Span status enum and TraceSpan dataclass."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class SpanStatus(Enum):
    """Span lifecycle status."""

    UNSET = auto()
    OK = auto()
    ERROR = auto()


@dataclass(slots=True)
class TraceSpan:
    """Represents a single operation within a trace.

    Attributes:
        trace_id: Unique identifier for the trace this span belongs to.
        span_id: Unique identifier for this span.
        parent_span_id: Identifier of the parent span, or None for root spans.
        operation: Name of the operation being traced.
        start_time: Unix timestamp when the span started.
        end_time: Unix timestamp when the span ended, or None if unfinished.
        status: Current status of the span.
        tags: Key-value metadata attached to the span.
        logs: Ordered list of log events recorded on the span.
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation: str
    start_time: float
    end_time: float | None
    status: SpanStatus
    tags: dict[str, Any]
    logs: list[dict[str, Any]]

    def set_tag(self, key: str, value: Any) -> None:
        """Set a tag on the span."""
        self.tags[key] = value

    def log_event(self, event: str, payload: dict[str, Any]) -> None:
        """Record a log event on the span."""
        self.logs.append(
            {
                "timestamp": time.time(),
                "event": event,
                "payload": payload,
            }
        )

    def finish(self, status: SpanStatus = SpanStatus.OK) -> None:
        """Mark the span as finished.

        Args:
            status: Final status of the span (defaults to OK).
        """
        if self.end_time is None:
            self.end_time = time.time()
        self.status = status

    def is_finished(self) -> bool:
        """Return True if the span has been finished."""
        return self.end_time is not None

    def get_duration_ms(self) -> float:
        """Return the span duration in milliseconds.

        For unfinished spans, returns the elapsed time since start.
        """
        end = self.end_time if self.end_time is not None else time.time()
        return (end - self.start_time) * 1000.0
