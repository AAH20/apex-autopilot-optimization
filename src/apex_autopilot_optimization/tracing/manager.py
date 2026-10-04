"""Tracing manager for creating and managing spans."""

from __future__ import annotations

import uuid
from typing import Any

from apex_autopilot_optimization.tracing.config import TracingConfig
from apex_autopilot_optimization.tracing.span import SpanStatus, TraceSpan


class TracingManager:
    """Manages span creation, storage, and retrieval.

    Provides a centralized interface for creating spans, ending them,
    and querying trace data.
    """

    def __init__(self, config: TracingConfig | None = None) -> None:
        self._config = config or TracingConfig()
        self._spans: dict[str, TraceSpan] = {}
        self._traces: dict[str, list[str]] = {}

    def start_span(
        self,
        operation: str,
        parent: TraceSpan | None = None,
    ) -> TraceSpan:
        """Start a new span.

        Args:
            operation: Name of the operation.
            parent: Optional parent span.

        Returns:
            The newly created TraceSpan.
        """
        trace_id = parent.trace_id if parent else str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent.span_id if parent else None,
            operation=operation,
            start_time=__import__("time").time(),
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        self._spans[span_id] = span
        if trace_id not in self._traces:
            self._traces[trace_id] = []
        self._traces[trace_id].append(span_id)
        return span

    def end_span(self, span: TraceSpan, status: SpanStatus = SpanStatus.OK) -> None:
        """End a span.

        Args:
            span: The span to end.
            status: Final status of the span.
        """
        if span.end_time is None:
            span.end_time = __import__("time").time()
        span.status = status

    def get_span(self, span_id: str) -> TraceSpan | None:
        """Retrieve a span by ID.

        Args:
            span_id: The span identifier.

        Returns:
            The TraceSpan or None if not found.
        """
        return self._spans.get(span_id)

    def get_trace(self, trace_id: str) -> list[TraceSpan]:
        """Get all spans belonging to a trace.

        Args:
            trace_id: The trace identifier.

        Returns:
            List of TraceSpan objects in the trace.
        """
        span_ids = self._traces.get(trace_id, [])
        return [self._spans[sid] for sid in span_ids if sid in self._spans]

    def get_traces(self) -> dict[str, list[TraceSpan]]:
        """Get all traces.

        Returns:
            Dict mapping trace_id to list of spans.
        """
        return {
            trace_id: [self._spans[sid] for sid in span_ids if sid in self._spans]
            for trace_id, span_ids in self._traces.items()
        }

    def clear_traces(self) -> None:
        """Clear all stored traces and spans."""
        self._spans.clear()
        self._traces.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get tracing statistics.

        Returns:
            Dict with counts of traces, spans, statuses, tags, and logs.
        """
        all_spans = list(self._spans.values())
        finished = [s for s in all_spans if s.is_finished()]
        errors = [s for s in all_spans if s.status == SpanStatus.ERROR]
        total_tags = sum(len(s.tags) for s in all_spans)
        total_logs = sum(len(s.logs) for s in all_spans)
        return {
            "total_traces": len(self._traces),
            "total_spans": len(all_spans),
            "finished_spans": len(finished),
            "unfinished_spans": len(all_spans) - len(finished),
            "error_spans": len(errors),
            "total_tags": total_tags,
            "total_logs": total_logs,
        }
