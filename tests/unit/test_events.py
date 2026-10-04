"""Tests for the event bus system."""
from __future__ import annotations

import time

from apex_autopilot_optimization.events import (
    Event,
    EventBus,
    EventEnvelope,
    EventPriority,
    HandlerRegistry,
    LoggingMiddleware,
    MetricsMiddleware,
)


class TestEvent:
    """Tests for Event dataclass."""

    def test_creation(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            payload={"key": "value"},
            timestamp=1234567890.0,
            priority=EventPriority.NORMAL,
            metadata={"trace": "abc"},
        )
        assert event.type == "test.event"
        assert event.source == "test_source"
        assert event.payload == {"key": "value"}
        assert event.timestamp == 1234567890.0
        assert event.priority == EventPriority.NORMAL
        assert event.metadata == {"trace": "abc"}

    def test_default_priority_is_normal(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            payload=None,
            timestamp=1234567890.0,
        )
        assert event.priority == EventPriority.NORMAL

    def test_default_metadata_is_empty_dict(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            payload=None,
            timestamp=1234567890.0,
        )
        assert event.metadata == {}


class TestEventPriority:
    """Tests for EventPriority enum ordering."""

    def test_priority_ordering(self) -> None:
        assert EventPriority.CRITICAL < EventPriority.HIGH
        assert EventPriority.HIGH < EventPriority.NORMAL
        assert EventPriority.NORMAL < EventPriority.LOW

    def test_priority_values_are_distinct(self) -> None:
        priorities = list(EventPriority)
        assert len(priorities) == 4
        assert len(set(priorities)) == 4


class TestEventEnvelope:
    """Tests for EventEnvelope dataclass."""

    def test_creation(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            payload={"data": 42},
            timestamp=1234567890.0,
        )
        envelope = EventEnvelope(
            event=event,
            trace_id="trace-123",
            timestamp=1234567891.0,
        )
        assert envelope.event is event
        assert envelope.trace_id == "trace-123"
        assert envelope.timestamp == 1234567891.0


class TestEventBus:
    """Tests for EventBus subscribe/unsubscribe/publish."""

    def test_subscribe_and_get_subscribers(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test.event", handler)
        subscribers = bus.get_subscribers("test.event")
        assert handler in subscribers

    def test_unsubscribe_removes_handler(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        subscribers = bus.get_subscribers("test.event")
        assert handler not in subscribers

    def test_unsubscribe_nonexistent_handler_is_noop(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.unsubscribe("test.event", handler)
        assert bus.get_subscribers("test.event") == []

    def test_publish_dispatches_to_handler(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test.event", handler)
        event = Event(
            type="test.event",
            source="test",
            payload={"x": 1},
            timestamp=time.time(),
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0] is event

    def test_publish_dispatches_to_multiple_handlers(self) -> None:
        bus = EventBus()
        received_a: list[Event] = []
        received_b: list[Event] = []

        def handler_a(event: Event) -> None:
            received_a.append(event)

        def handler_b(event: Event) -> None:
            received_b.append(event)

        bus.subscribe("test.event", handler_a)
        bus.subscribe("test.event", handler_b)
        event = Event(
            type="test.event",
            source="test",
            payload=None,
            timestamp=time.time(),
        )
        bus.publish(event)
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_publish_only_dispatches_to_matching_type(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("other.event", handler)
        event = Event(
            type="test.event",
            source="test",
            payload=None,
            timestamp=time.time(),
        )
        bus.publish(event)
        assert len(received) == 0

    def test_publish_no_subscribers_is_noop(self) -> None:
        bus = EventBus()
        event = Event(
            type="test.event",
            source="test",
            payload=None,
            timestamp=time.time(),
        )
        bus.publish(event)  # Should not raise

    def test_clear_removes_all_subscribers(self) -> None:
        bus = EventBus()
        handler_a = lambda e: None  # noqa: E731
        handler_b = lambda e: None  # noqa: E731
        bus.subscribe("test.event", handler_a)
        bus.subscribe("other.event", handler_b)
        bus.clear()
        assert bus.get_subscribers("test.event") == []
        assert bus.get_subscribers("other.event") == []

    def test_get_subscribers_returns_copy(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test.event", handler)
        subscribers = bus.get_subscribers("test.event")
        subscribers.clear()
        assert handler in bus.get_subscribers("test.event")


class TestHandlerRegistry:
    """Tests for HandlerRegistry."""

    def test_register_and_get_handlers(self) -> None:
        registry = HandlerRegistry()
        handler = lambda e: None  # noqa: E731
        registry.register("test.event", handler)
        handlers = registry.get_handlers("test.event")
        assert handler in handlers

    def test_unregister_removes_handler(self) -> None:
        registry = HandlerRegistry()
        handler = lambda e: None  # noqa: E731
        registry.register("test.event", handler)
        registry.unregister("test.event", handler)
        assert handler not in registry.get_handlers("test.event")

    def test_get_handlers_unknown_type_returns_empty(self) -> None:
        registry = HandlerRegistry()
        assert registry.get_handlers("unknown") == []


class TestMiddleware:
    """Tests for middleware classes."""

    def test_logging_middleware_logs_event(self) -> None:
        calls: list[str] = []

        def logger(msg: str) -> None:
            calls.append(msg)

        middleware = LoggingMiddleware(logger=logger)
        event = Event(
            type="test.event",
            source="test",
            payload=None,
            timestamp=time.time(),
        )
        middleware.process(event)
        assert len(calls) == 1
        assert "test.event" in calls[0]

    def test_metrics_middleware_counts_events(self) -> None:
        middleware = MetricsMiddleware()
        event = Event(
            type="test.event",
            source="test",
            payload=None,
            timestamp=time.time(),
        )
        middleware.process(event)
        assert middleware.get_count("test.event") == 1

    def test_metrics_middleware_counts_multiple_events(self) -> None:
        middleware = MetricsMiddleware()
        for _ in range(3):
            event = Event(
                type="test.event",
                source="test",
                payload=None,
                timestamp=time.time(),
            )
            middleware.process(event)
        assert middleware.get_count("test.event") == 3

    def test_middleware_chain(self) -> None:
        bus = EventBus()
        metrics = MetricsMiddleware()
        bus.add_middleware(metrics)
        received: list[Event] = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test.event", handler)
        event = Event(
            type="test.event",
            source="test",
            payload=None,
            timestamp=time.time(),
        )
        bus.publish(event)
        assert len(received) == 1
        assert metrics.get_count("test.event") == 1
