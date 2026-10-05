"""Tests for the event bus system."""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.events import (
    Event,
    EventBus,
    EventFilter,
    EventPriority,
    LoggingMiddleware,
    MetricsMiddleware,
    ValidationMiddleware,
    publish,
    subscribe,
)


class TestEvent:
    """Tests for Event dataclass."""

    def test_creation_with_all_fields(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            timestamp=1234567890.0,
            payload={"key": "value"},
            priority=EventPriority.HIGH,
        )
        assert event.type == "test.event"
        assert event.source == "test_source"
        assert event.timestamp == 1234567890.0
        assert event.payload == {"key": "value"}
        assert event.priority == EventPriority.HIGH

    def test_default_priority_is_normal(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            timestamp=1234567890.0,
        )
        assert event.priority == EventPriority.NORMAL

    def test_default_payload_is_none(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            timestamp=1234567890.0,
        )
        assert event.payload is None

    def test_id_is_auto_generated(self) -> None:
        event = Event(
            type="test.event",
            source="test_source",
            timestamp=1234567890.0,
        )
        assert event.id is not None
        assert len(event.id) > 0

    def test_ids_are_unique(self) -> None:
        e1 = Event(type="t", source="s", timestamp=1.0)
        e2 = Event(type="t", source="s", timestamp=1.0)
        assert e1.id != e2.id


class TestEventPriority:
    """Tests for EventPriority enum."""

    def test_priority_ordering(self) -> None:
        assert EventPriority.CRITICAL < EventPriority.HIGH
        assert EventPriority.HIGH < EventPriority.NORMAL
        assert EventPriority.NORMAL < EventPriority.LOW

    def test_priority_values_are_distinct(self) -> None:
        priorities = list(EventPriority)
        assert len(priorities) == 4
        assert len(set(priorities)) == 4

    def test_critical_is_highest_priority(self) -> None:
        assert EventPriority.CRITICAL == 0
        assert EventPriority.LOW == 3


class TestEventFilter:
    """Tests for EventFilter."""

    def test_matches_by_type(self) -> None:
        f = EventFilter(types={"test.event"})
        event = Event(type="test.event", source="s", timestamp=1.0)
        assert f.matches(event) is True

    def test_no_match_by_type(self) -> None:
        f = EventFilter(types={"other.event"})
        event = Event(type="test.event", source="s", timestamp=1.0)
        assert f.matches(event) is False

    def test_matches_by_source(self) -> None:
        f = EventFilter(sources={"src_a"})
        event = Event(type="t", source="src_a", timestamp=1.0)
        assert f.matches(event) is True

    def test_matches_by_min_priority(self) -> None:
        f = EventFilter(min_priority=EventPriority.HIGH)
        assert (
            f.matches(
                Event(
                    type="t",
                    source="s",
                    timestamp=1.0,
                    priority=EventPriority.CRITICAL,
                )
            )
            is True
        )
        assert (
            f.matches(
                Event(
                    type="t",
                    source="s",
                    timestamp=1.0,
                    priority=EventPriority.HIGH,
                )
            )
            is True
        )
        assert (
            f.matches(
                Event(
                    type="t",
                    source="s",
                    timestamp=1.0,
                    priority=EventPriority.NORMAL,
                )
            )
            is False
        )

    def test_empty_filter_matches_all(self) -> None:
        f = EventFilter()
        event = Event(type="anything", source="any", timestamp=1.0)
        assert f.matches(event) is True


class TestEventBus:
    """Tests for EventBus subscribe/unsubscribe/publish."""

    def test_subscribe_and_get_handlers(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test.event", handler)
        handlers = bus.get_handlers("test.event")
        assert handler in handlers

    def test_unsubscribe_removes_handler(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        assert handler not in bus.get_handlers("test.event")

    def test_unsubscribe_nonexistent_is_noop(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.unsubscribe("test.event", handler)
        assert bus.get_handlers("test.event") == []

    def test_publish_dispatches_to_handler(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test.event", handler)
        event = Event(type="test.event", source="test", timestamp=time.time())
        bus.publish(event)
        assert len(received) == 1
        assert received[0] is event

    def test_publish_dispatches_to_multiple_handlers(self) -> None:
        bus = EventBus()
        received_a: list[Event] = []
        received_b: list[Event] = []

        bus.subscribe("test.event", lambda e: received_a.append(e))
        bus.subscribe("test.event", lambda e: received_b.append(e))
        event = Event(type="test.event", source="test", timestamp=time.time())
        bus.publish(event)
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_publish_only_dispatches_to_matching_type(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe("other.event", lambda e: received.append(e))
        event = Event(type="test.event", source="test", timestamp=time.time())
        bus.publish(event)
        assert len(received) == 0

    def test_publish_no_subscribers_is_noop(self) -> None:
        bus = EventBus()
        event = Event(type="test.event", source="test", timestamp=time.time())
        bus.publish(event)  # Should not raise

    def test_clear_handlers_removes_all(self) -> None:
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.clear_handlers()
        assert bus.get_handlers("a") == []
        assert bus.get_handlers("b") == []

    def test_get_handlers_returns_copy(self) -> None:
        bus = EventBus()
        handler = lambda e: None  # noqa: E731
        bus.subscribe("test.event", handler)
        handlers = bus.get_handlers("test.event")
        handlers.clear()
        assert handler in bus.get_handlers("test.event")

    def test_get_event_count(self) -> None:
        bus = EventBus()
        bus.subscribe("test.event", lambda e: None)
        assert bus.get_event_count() == 0
        bus.publish(Event(type="test.event", source="s", timestamp=1.0))
        bus.publish(Event(type="test.event", source="s", timestamp=2.0))
        assert bus.get_event_count() == 2

    def test_get_event_history(self) -> None:
        bus = EventBus()
        bus.subscribe("test.event", lambda e: None)
        for i in range(5):
            bus.publish(Event(type="test.event", source="s", timestamp=float(i)))
        history = bus.get_event_history()
        assert len(history) == 5

    def test_get_event_history_with_limit(self) -> None:
        bus = EventBus()
        bus.subscribe("test.event", lambda e: None)
        for i in range(10):
            bus.publish(Event(type="test.event", source="s", timestamp=float(i)))
        history = bus.get_event_history(limit=3)
        assert len(history) == 3
        assert history[0].timestamp == 7.0

    def test_get_filtered_history(self) -> None:
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.publish(Event(type="a", source="s", timestamp=1.0))
        bus.publish(Event(type="b", source="s", timestamp=2.0))
        bus.publish(Event(type="a", source="s", timestamp=3.0))
        f = EventFilter(types={"a"})
        filtered = bus.get_filtered_history(f)
        assert len(filtered) == 2
        assert all(e.type == "a" for e in filtered)

    def test_clear_history(self) -> None:
        bus = EventBus()
        bus.subscribe("test.event", lambda e: None)
        bus.publish(Event(type="test.event", source="s", timestamp=1.0))
        bus.clear_history()
        assert bus.get_event_history() == []


class TestMiddleware:
    """Tests for middleware classes."""

    def test_logging_middleware_logs_event(self) -> None:
        calls: list[str] = []
        middleware = LoggingMiddleware(logger=calls.append)
        event = Event(type="test.event", source="test", timestamp=time.time())
        result = middleware.process(event)
        assert len(calls) == 1
        assert "test.event" in calls[0]
        assert result is event

    def test_metrics_middleware_counts_events(self) -> None:
        middleware = MetricsMiddleware()
        event = Event(type="test.event", source="test", timestamp=time.time())
        middleware.process(event)
        assert middleware.get_count("test.event") == 1

    def test_metrics_middleware_counts_multiple(self) -> None:
        middleware = MetricsMiddleware()
        for _ in range(3):
            middleware.process(Event(type="test.event", source="s", timestamp=1.0))
        assert middleware.get_count("test.event") == 3

    def test_metrics_middleware_get_all_counts(self) -> None:
        middleware = MetricsMiddleware()
        middleware.process(Event(type="a", source="s", timestamp=1.0))
        middleware.process(Event(type="b", source="s", timestamp=1.0))
        middleware.process(Event(type="a", source="s", timestamp=1.0))
        counts = middleware.get_all_counts()
        assert counts == {"a": 2, "b": 1}

    def test_validation_middleware_passes_valid_event(self) -> None:
        middleware = ValidationMiddleware()
        event = Event(type="test.event", source="test", timestamp=1.0)
        result = middleware.process(event)
        assert result is event

    def test_validation_middleware_rejects_empty_type(self) -> None:
        middleware = ValidationMiddleware()
        event = Event(type="", source="test", timestamp=1.0)
        with pytest.raises(ValueError, match="type"):
            middleware.process(event)

    def test_validation_middleware_rejects_empty_source(self) -> None:
        middleware = ValidationMiddleware()
        event = Event(type="test", source="", timestamp=1.0)
        with pytest.raises(ValueError, match="source"):
            middleware.process(event)

    def test_validation_middleware_rejects_zero_timestamp(self) -> None:
        middleware = ValidationMiddleware()
        event = Event(type="test", source="s", timestamp=0.0)
        with pytest.raises(ValueError, match="timestamp"):
            middleware.process(event)

    def test_middleware_chain_in_bus(self) -> None:
        bus = EventBus()
        metrics = MetricsMiddleware()
        bus.add_middleware(metrics)
        received: list[Event] = []
        bus.subscribe("test.event", lambda e: received.append(e))
        event = Event(type="test.event", source="test", timestamp=time.time())
        bus.publish(event)
        assert len(received) == 1
        assert metrics.get_count("test.event") == 1

    def test_remove_middleware(self) -> None:
        bus = EventBus()
        metrics = MetricsMiddleware()
        bus.add_middleware(metrics)
        bus.remove_middleware(metrics)
        assert metrics not in bus.get_middleware()

    def test_middleware_order_preserved(self) -> None:
        bus = EventBus()
        m1 = MetricsMiddleware()
        m2 = MetricsMiddleware()
        bus.add_middleware(m1)
        bus.add_middleware(m2)
        mws = bus.get_middleware()
        assert mws[0] is m1
        assert mws[1] is m2


class TestConvenienceFunctions:
    """Tests for module-level subscribe/publish functions."""

    def test_subscribe_function(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        subscribe(bus, "test.event", lambda e: received.append(e))
        event = Event(type="test.event", source="s", timestamp=1.0)
        bus.publish(event)
        assert len(received) == 1

    def test_publish_function(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe("test.event", lambda e: received.append(e))
        event = Event(type="test.event", source="s", timestamp=1.0)
        publish(bus, event)
        assert len(received) == 1
