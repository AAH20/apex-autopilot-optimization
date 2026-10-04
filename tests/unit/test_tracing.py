"""Tests for distributed tracing package."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.tracing import (
    SpanStatus,
    TraceContext,
    TraceSpan,
    TracingConfig,
    TracingManager,
)


# ── SpanStatus ──────────────────────────────────────────────────────────────


class TestSpanStatus:
    """Tests for SpanStatus enum."""

    def test_status_values(self) -> None:
        assert SpanStatus.OK is not None
        assert SpanStatus.ERROR is not None
        assert SpanStatus.UNSET is not None

    def test_status_distinct(self) -> None:
        assert SpanStatus.OK != SpanStatus.ERROR
        assert SpanStatus.OK != SpanStatus.UNSET
        assert SpanStatus.ERROR != SpanStatus.UNSET


# ── TraceSpan ───────────────────────────────────────────────────────────────


class TestTraceSpanCreation:
    """Tests for TraceSpan creation."""

    def test_span_creation_with_required_fields(self) -> None:
        span = TraceSpan(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            operation="test-op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        assert span.trace_id == "trace-1"
        assert span.span_id == "span-1"
        assert span.parent_span_id is None
        assert span.operation == "test-op"
        assert span.start_time == 1000.0
        assert span.end_time is None
        assert span.status == SpanStatus.UNSET
        assert span.tags == {}
        assert span.logs == []

    def test_span_creation_with_parent(self) -> None:
        span = TraceSpan(
            trace_id="trace-1",
            span_id="span-2",
            parent_span_id="span-1",
            operation="child-op",
            start_time=1001.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        assert span.parent_span_id == "span-1"

    def test_span_creation_with_end_time(self) -> None:
        span = TraceSpan(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            operation="test-op",
            start_time=1000.0,
            end_time=1005.0,
            status=SpanStatus.OK,
            tags={},
            logs=[],
        )
        assert span.end_time == 1005.0
        assert span.status == SpanStatus.OK


class TestTraceSpanFinish:
    """Tests for TraceSpan.finish()."""

    def test_finish_sets_end_time(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        assert span.end_time is None
        span.finish()
        assert span.end_time is not None
        assert span.end_time >= span.start_time

    def test_finish_sets_status_ok(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.finish()
        assert span.status == SpanStatus.OK

    def test_finish_with_explicit_status(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.finish(status=SpanStatus.ERROR)
        assert span.status == SpanStatus.ERROR

    def test_finish_is_idempotent(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.finish()
        first_end = span.end_time
        span.finish()
        assert span.end_time == first_end


class TestTraceSpanIsFinished:
    """Tests for TraceSpan.is_finished()."""

    def test_unfinished_span(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        assert not span.is_finished()

    def test_finished_span(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.finish()
        assert span.is_finished()


class TestTraceSpanDuration:
    """Tests for TraceSpan.get_duration_ms()."""

    def test_duration_unfinished_span(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        duration = span.get_duration_ms()
        assert duration >= 0.0

    def test_duration_finished_span(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=1005.0,
            status=SpanStatus.OK,
            tags={},
            logs=[],
        )
        assert span.get_duration_ms() == pytest.approx(5000.0)

    def test_duration_after_finish(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.finish()
        duration = span.get_duration_ms()
        assert duration >= 0.0


class TestTraceSpanTags:
    """Tests for TraceSpan.set_tag()."""

    def test_set_tag(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.set_tag("key", "value")
        assert span.tags["key"] == "value"

    def test_set_multiple_tags(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.set_tag("k1", "v1")
        span.set_tag("k2", 42)
        assert span.tags == {"k1": "v1", "k2": 42}

    def test_set_tag_overwrite(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={"key": "old"},
            logs=[],
        )
        span.set_tag("key", "new")
        assert span.tags["key"] == "new"


class TestTraceSpanLogs:
    """Tests for TraceSpan.log_event()."""

    def test_log_event(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.log_event("test-event", {"detail": "info"})
        assert len(span.logs) == 1
        assert span.logs[0]["event"] == "test-event"
        assert span.logs[0]["payload"] == {"detail": "info"}

    def test_log_multiple_events(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        span.log_event("e1", {})
        span.log_event("e2", {})
        assert len(span.logs) == 2

    def test_log_event_has_timestamp(self) -> None:
        span = TraceSpan(
            trace_id="t",
            span_id="s",
            parent_span_id=None,
            operation="op",
            start_time=1000.0,
            end_time=None,
            status=SpanStatus.UNSET,
            tags={},
            logs=[],
        )
        before = time.time()
        span.log_event("evt", {})
        after = time.time()
        ts = span.logs[0]["timestamp"]
        assert before <= ts <= after


# ── TraceContext ────────────────────────────────────────────────────────────


class TestTraceContextCreation:
    """Tests for TraceContext creation."""

    def test_context_creation(self) -> None:
        ctx = TraceContext(trace_id="t-1", span_id="s-1", baggage={})
        assert ctx.trace_id == "t-1"
        assert ctx.span_id == "s-1"
        assert ctx.baggage == {}

    def test_context_with_baggage(self) -> None:
        ctx = TraceContext(trace_id="t-1", span_id="s-1", baggage={"key": "val"})
        assert ctx.baggage == {"key": "val"}


class TestTraceContextInjectExtract:
    """Tests for TraceContext inject/extract."""

    def test_inject_into_empty_carrier(self) -> None:
        ctx = TraceContext(trace_id="t-1", span_id="s-1", baggage={"b": "v"})
        carrier: dict[str, str] = {}
        TraceContext.inject(ctx, carrier)
        assert carrier["x-trace-id"] == "t-1"
        assert carrier["x-span-id"] == "s-1"
        assert carrier["x-baggage-b"] == "v"

    def test_inject_into_existing_carrier(self) -> None:
        ctx = TraceContext(trace_id="t-1", span_id="s-1", baggage={})
        carrier = {"existing": "header"}
        TraceContext.inject(ctx, carrier)
        assert carrier["existing"] == "header"
        assert carrier["x-trace-id"] == "t-1"

    def test_extract_from_carrier(self) -> None:
        carrier = {
            "x-trace-id": "t-9",
            "x-span-id": "s-9",
            "x-baggage-key1": "val1",
        }
        ctx = TraceContext.extract(carrier)
        assert ctx.trace_id == "t-9"
        assert ctx.span_id == "s-9"
        assert ctx.baggage == {"key1": "val1"}

    def test_extract_from_empty_carrier(self) -> None:
        ctx = TraceContext.extract({})
        assert ctx.trace_id == ""
        assert ctx.span_id == ""
        assert ctx.baggage == {}

    def test_roundtrip(self) -> None:
        original = TraceContext(trace_id="t-1", span_id="s-1", baggage={"k": "v"})
        carrier: dict[str, str] = {}
        TraceContext.inject(original, carrier)
        restored = TraceContext.extract(carrier)
        assert restored.trace_id == original.trace_id
        assert restored.span_id == original.span_id
        assert restored.baggage == original.baggage


class TestTraceContextCurrent:
    """Tests for TraceContext get/set current context."""

    def test_set_and_get_current(self) -> None:
        ctx = TraceContext(trace_id="t-1", span_id="s-1", baggage={})
        TraceContext.set_current_context(ctx)
        current = TraceContext.get_current_context()
        assert current is not None
        assert current.trace_id == "t-1"
        assert current.span_id == "s-1"

    def test_get_current_default(self) -> None:
        TraceContext.set_current_context(None)
        current = TraceContext.get_current_context()
        assert current is None

    def test_overwrite_current(self) -> None:
        ctx1 = TraceContext(trace_id="t-1", span_id="s-1", baggage={})
        ctx2 = TraceContext(trace_id="t-2", span_id="s-2", baggage={})
        TraceContext.set_current_context(ctx1)
        TraceContext.set_current_context(ctx2)
        current = TraceContext.get_current_context()
        assert current.trace_id == "t-2"


# ── TracingConfig ───────────────────────────────────────────────────────────


class TestTracingConfig:
    """Tests for TracingConfig dataclass."""

    def test_config_creation(self) -> None:
        config = TracingConfig(
            enabled=True,
            sample_rate=1.0,
            exporter="console",
            endpoint="http://localhost:4317",
            service_name="test-service",
        )
        assert config.enabled is True
        assert config.sample_rate == 1.0
        assert config.exporter == "console"
        assert config.endpoint == "http://localhost:4317"
        assert config.service_name == "test-service"

    def test_config_defaults(self) -> None:
        config = TracingConfig()
        assert config.enabled is False
        assert config.sample_rate == 1.0
        assert config.exporter == "console"
        assert config.endpoint == ""
        assert config.service_name == "apex-autopilot"

    def test_config_custom_values(self) -> None:
        config = TracingConfig(
            enabled=True,
            sample_rate=0.5,
            exporter="otlp",
            endpoint="http://collector:4318",
            service_name="my-service",
        )
        assert config.sample_rate == 0.5
        assert config.exporter == "otlp"
        assert config.service_name == "my-service"


# ── TracingManager ──────────────────────────────────────────────────────────


class TestTracingManagerStartSpan:
    """Tests for TracingManager.start_span()."""

    def test_start_span_creates_span(self) -> None:
        manager = TracingManager()
        span = manager.start_span("test-op")
        assert span.operation == "test-op"
        assert span.span_id is not None
        assert span.trace_id is not None
        assert span.parent_span_id is None
        assert not span.is_finished()

    def test_start_span_with_parent(self) -> None:
        manager = TracingManager()
        parent = manager.start_span("parent-op")
        child = manager.start_span("child-op", parent=parent)
        assert child.parent_span_id == parent.span_id
        assert child.trace_id == parent.trace_id

    def test_start_span_generates_unique_ids(self) -> None:
        manager = TracingManager()
        s1 = manager.start_span("op1")
        s2 = manager.start_span("op2")
        assert s1.span_id != s2.span_id
        assert s1.trace_id != s2.trace_id

    def test_start_span_with_config(self) -> None:
        config = TracingConfig(enabled=True, service_name="test-svc")
        manager = TracingManager(config=config)
        span = manager.start_span("op")
        assert span.operation == "op"


class TestTracingManagerEndSpan:
    """Tests for TracingManager.end_span()."""

    def test_end_span(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        manager.end_span(span)
        assert span.is_finished()
        assert span.end_time is not None

    def test_end_span_with_error_status(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        manager.end_span(span, status=SpanStatus.ERROR)
        assert span.status == SpanStatus.ERROR

    def test_end_already_finished_span(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        manager.end_span(span)
        first_end = span.end_time
        manager.end_span(span)
        assert span.end_time == first_end


class TestTracingManagerGetSpan:
    """Tests for TracingManager.get_span()."""

    def test_get_existing_span(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        retrieved = manager.get_span(span.span_id)
        assert retrieved is not None
        assert retrieved.span_id == span.span_id

    def test_get_nonexistent_span(self) -> None:
        manager = TracingManager()
        assert manager.get_span("nonexistent") is None


class TestTracingManagerGetTrace:
    """Tests for TracingManager.get_trace()."""

    def test_get_trace(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        spans = manager.get_trace(span.trace_id)
        assert len(spans) == 1
        assert spans[0].span_id == span.span_id

    def test_get_trace_multiple_spans(self) -> None:
        manager = TracingManager()
        s1 = manager.start_span("op1")
        s2 = manager.start_span("op2", parent=s1)
        spans = manager.get_trace(s1.trace_id)
        assert len(spans) == 2

    def test_get_nonexistent_trace(self) -> None:
        manager = TracingManager()
        assert manager.get_trace("nonexistent") == []


class TestTracingManagerGetTraces:
    """Tests for TracingManager.get_traces()."""

    def test_get_traces_empty(self) -> None:
        manager = TracingManager()
        assert manager.get_traces() == {}

    def test_get_traces_multiple(self) -> None:
        manager = TracingManager()
        s1 = manager.start_span("op1")
        s2 = manager.start_span("op2")
        traces = manager.get_traces()
        assert len(traces) == 2
        assert s1.trace_id in traces
        assert s2.trace_id in traces


class TestTracingManagerClearTraces:
    """Tests for TracingManager.clear_traces()."""

    def test_clear_traces(self) -> None:
        manager = TracingManager()
        manager.start_span("op")
        manager.clear_traces()
        assert manager.get_traces() == {}

    def test_clear_then_add(self) -> None:
        manager = TracingManager()
        manager.start_span("op1")
        manager.clear_traces()
        span = manager.start_span("op2")
        traces = manager.get_traces()
        assert len(traces) == 1
        assert span.trace_id in traces


class TestTracingManagerStats:
    """Tests for TracingManager.get_stats()."""

    def test_stats_empty(self) -> None:
        manager = TracingManager()
        stats = manager.get_stats()
        assert stats["total_traces"] == 0
        assert stats["total_spans"] == 0

    def test_stats_with_spans(self) -> None:
        manager = TracingManager()
        manager.start_span("op1")
        manager.start_span("op2")
        stats = manager.get_stats()
        assert stats["total_traces"] == 2
        assert stats["total_spans"] == 2

    def test_stats_with_finished_spans(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        manager.end_span(span)
        stats = manager.get_stats()
        assert stats["total_spans"] == 1
        assert stats["finished_spans"] == 1
        assert stats["unfinished_spans"] == 0

    def test_stats_with_unfinished_spans(self) -> None:
        manager = TracingManager()
        manager.start_span("op")
        stats = manager.get_stats()
        assert stats["unfinished_spans"] == 1
        assert stats["finished_spans"] == 0

    def test_stats_with_error_spans(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        manager.end_span(span, status=SpanStatus.ERROR)
        stats = manager.get_stats()
        assert stats["error_spans"] == 1

    def test_stats_with_tags(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        span.set_tag("key", "value")
        stats = manager.get_stats()
        assert stats["total_tags"] == 1

    def test_stats_with_logs(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        span.log_event("evt", {})
        stats = manager.get_stats()
        assert stats["total_logs"] == 1


# ── Integration-style tests ─────────────────────────────────────────────────


class TestTracingIntegration:
    """Integration tests for the tracing package."""

    def test_full_trace_lifecycle(self) -> None:
        manager = TracingManager()
        root = manager.start_span("root")
        child = manager.start_span("child", parent=root)
        child.set_tag("key", "value")
        child.log_event("event", {"data": 1})
        manager.end_span(child)
        manager.end_span(root)

        traces = manager.get_traces()
        assert len(traces) == 1
        spans = manager.get_trace(root.trace_id)
        assert len(spans) == 2

        stats = manager.get_stats()
        assert stats["total_traces"] == 1
        assert stats["total_spans"] == 2
        assert stats["finished_spans"] == 2

    def test_context_propagation(self) -> None:
        manager = TracingManager()
        span = manager.start_span("op")
        ctx = TraceContext(trace_id=span.trace_id, span_id=span.span_id, baggage={})
        carrier: dict[str, str] = {}
        TraceContext.inject(ctx, carrier)
        restored = TraceContext.extract(carrier)
        assert restored.trace_id == span.trace_id
        assert restored.span_id == span.span_id

    def test_multiple_managers_isolated(self) -> None:
        m1 = TracingManager()
        m2 = TracingManager()
        s1 = m1.start_span("op")
        s2 = m2.start_span("op")
        assert s1.trace_id != s2.trace_id
        assert len(m1.get_traces()) == 1
        assert len(m2.get_traces()) == 1
