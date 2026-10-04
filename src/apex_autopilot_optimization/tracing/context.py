"""Trace context propagation."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

_local = threading.local()


@dataclass(slots=True)
class TraceContext:
    """Trace context for propagation across module boundaries.

    Attributes:
        trace_id: Unique identifier for the trace.
        span_id: Identifier of the current span.
        baggage: Key-value pairs propagated across service boundaries.
    """

    trace_id: str
    span_id: str
    baggage: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def inject(context: TraceContext, carrier: dict[str, str]) -> None:
        """Inject context into a carrier dict.

        Args:
            context: The trace context to inject.
            carrier: Mutable dict to populate with context headers.
        """
        carrier["x-trace-id"] = context.trace_id
        carrier["x-span-id"] = context.span_id
        for key, value in context.baggage.items():
            carrier[f"x-baggage-{key}"] = str(value)

    @staticmethod
    def extract(carrier: dict[str, str]) -> TraceContext:
        """Extract context from a carrier dict.

        Args:
            carrier: Dict containing trace context headers.

        Returns:
            Reconstructed TraceContext.
        """
        trace_id = carrier.get("x-trace-id", "")
        span_id = carrier.get("x-span-id", "")
        baggage: dict[str, Any] = {}
        for key, value in carrier.items():
            if key.startswith("x-baggage-"):
                baggage_key = key[len("x-baggage-"):]
                baggage[baggage_key] = value
        return TraceContext(trace_id=trace_id, span_id=span_id, baggage=baggage)

    @staticmethod
    def get_current_context() -> TraceContext | None:
        """Get the current thread-local trace context.

        Returns:
            The current TraceContext or None if not set.
        """
        return getattr(_local, "current_context", None)

    @staticmethod
    def set_current_context(context: TraceContext | None) -> None:
        """Set the current thread-local trace context.

        Args:
            context: The TraceContext to set, or None to clear.
        """
        _local.current_context = context
