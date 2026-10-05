"""Tests for the messaging package (message queue, stream processing, event store)."""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.messaging import (
    EventStore,
    Message,
    MessageQueue,
    QueueConfig,
    StreamProcessor,
)


class TestMessage:
    """Tests for the Message dataclass."""

    def test_creation(self) -> None:
        msg = Message(
            id="msg-1",
            topic="orders",
            payload={"item": "widget", "qty": 3},
            timestamp="2026-10-04T10:00:00Z",
            priority=5,
            headers={"trace": "abc"},
        )
        assert msg.id == "msg-1"
        assert msg.topic == "orders"
        assert msg.payload == {"item": "widget", "qty": 3}
        assert msg.timestamp == "2026-10-04T10:00:00Z"
        assert msg.priority == 5
        assert msg.headers == {"trace": "abc"}

    def test_default_priority_is_zero(self) -> None:
        msg = Message(
            id="msg-2",
            topic="orders",
            payload={},
            timestamp="2026-10-04T10:00:01Z",
        )
        assert msg.priority == 0
        assert msg.headers == {}

    def test_messages_with_same_fields_are_equal(self) -> None:
        a = Message(id="m", topic="t", payload={"x": 1}, timestamp="ts", priority=1)
        b = Message(id="m", topic="t", payload={"x": 1}, timestamp="ts", priority=1)
        assert a == b

    def test_messages_with_different_fields_are_not_equal(self) -> None:
        a = Message(id="m1", topic="t", payload={}, timestamp="ts")
        b = Message(id="m2", topic="t", payload={}, timestamp="ts")
        assert a != b


class TestQueueConfig:
    """Tests for the QueueConfig dataclass."""

    def test_creation(self) -> None:
        cfg = QueueConfig(name="orders", max_size=100, durable=True, ttl_seconds=60)
        assert cfg.name == "orders"
        assert cfg.max_size == 100
        assert cfg.durable is True
        assert cfg.ttl_seconds == 60

    def test_defaults(self) -> None:
        cfg = QueueConfig(name="orders")
        assert cfg.max_size == 1000
        assert cfg.durable is False
        assert cfg.ttl_seconds == 3600


class TestMessageQueuePublishSubscribe:
    """Tests for MessageQueue publish/subscribe/unsubscribe."""

    def test_publish_delivers_to_subscriber(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        received: list[Message] = []
        q.subscribe("orders", received.append)
        msg = Message(id="m1", topic="orders", payload={"x": 1}, timestamp="ts")
        q.publish(msg)
        assert received == [msg]

    def test_publish_delivers_to_multiple_subscribers(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        a: list[Message] = []
        b: list[Message] = []
        q.subscribe("orders", a.append)
        q.subscribe("orders", b.append)
        msg = Message(id="m1", topic="orders", payload={}, timestamp="ts")
        q.publish(msg)
        assert a == [msg]
        assert b == [msg]

    def test_subscriber_only_receives_its_topic(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        received: list[Message] = []
        q.subscribe("orders", received.append)
        q.publish(Message(id="m1", topic="other", payload={}, timestamp="ts"))
        assert received == []

    def test_unsubscribe_stops_delivery(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        received: list[Message] = []
        handler = received.append
        q.subscribe("orders", handler)
        q.unsubscribe("orders", handler)
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        assert received == []

    def test_unsubscribe_unknown_handler_is_noop(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.unsubscribe("orders", lambda m: None)  # must not raise

    def test_publish_increments_stats(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.subscribe("orders", lambda m: None)
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        q.publish(Message(id="m2", topic="orders", payload={}, timestamp="ts"))
        stats = q.get_queue_stats()
        assert stats["published"] == 2
        assert stats["delivered"] == 2


class TestMessageQueueSizeAndStats:
    """Tests for MessageQueue size and stats."""

    def test_get_queue_size_counts_undelivered(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        q.publish(Message(id="m2", topic="orders", payload={}, timestamp="ts"))
        assert q.get_queue_size("orders") == 2

    def test_get_queue_size_unknown_topic_is_zero(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        assert q.get_queue_size("nope") == 0

    def test_get_queue_size_per_topic(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        q.publish(Message(id="m2", topic="billing", payload={}, timestamp="ts"))
        assert q.get_queue_size("orders") == 1
        assert q.get_queue_size("billing") == 1

    def test_get_queue_stats_reports_topics(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        stats = q.get_queue_stats()
        assert stats["topics"] == {"orders": 1}

    def test_get_queue_stats_tracks_subscribers(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.subscribe("orders", lambda m: None)
        q.subscribe("orders", lambda m: None)
        stats = q.get_queue_stats()
        assert stats["subscribers"] == {"orders": 2}


class TestMessageQueuePurgeClear:
    """Tests for MessageQueue purge and clear."""

    def test_purge_removes_messages_for_topic(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        q.publish(Message(id="m2", topic="billing", payload={}, timestamp="ts"))
        q.purge("orders")
        assert q.get_queue_size("orders") == 0
        assert q.get_queue_size("billing") == 1

    def test_purge_unknown_topic_is_noop(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.purge("nope")  # must not raise

    def test_clear_removes_all_messages(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        q.publish(Message(id="m2", topic="billing", payload={}, timestamp="ts"))
        q.clear()
        assert q.get_queue_size("orders") == 0
        assert q.get_queue_size("billing") == 0

    def test_clear_resets_stats(self) -> None:
        q = MessageQueue(QueueConfig(name="orders"))
        q.subscribe("orders", lambda m: None)
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        q.clear()
        stats = q.get_queue_stats()
        assert stats["published"] == 0
        assert stats["delivered"] == 0


class TestMessageQueueMaxSize:
    """Tests for MessageQueue max_size enforcement."""

    def test_publish_beyond_max_size_raises(self) -> None:
        q = MessageQueue(QueueConfig(name="orders", max_size=1))
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        with pytest.raises(RuntimeError):
            q.publish(Message(id="m2", topic="orders", payload={}, timestamp="ts"))

    def test_max_size_does_not_block_when_within_limit(self) -> None:
        q = MessageQueue(QueueConfig(name="orders", max_size=2))
        q.publish(Message(id="m1", topic="orders", payload={}, timestamp="ts"))
        q.publish(Message(id="m2", topic="orders", payload={}, timestamp="ts"))
        assert q.get_queue_size("orders") == 2


class TestStreamProcessor:
    """Tests for StreamProcessor process/window/aggregate/filter."""

    def test_process_stream_applies_to_each_item(self) -> None:
        sp = StreamProcessor()
        result = sp.process_stream([1, 2, 3], lambda x: x * 2)
        assert result == [2, 4, 6]

    def test_process_stream_empty(self) -> None:
        sp = StreamProcessor()
        assert sp.process_stream([], lambda x: x) == []

    def test_process_stream_tracks_stats(self) -> None:
        sp = StreamProcessor()
        sp.process_stream([1, 2, 3], lambda x: x)
        stats = sp.get_stream_stats()
        assert stats["processed"] == 3

    def test_window_by_count_groups_items(self) -> None:
        sp = StreamProcessor()
        windows = sp.window_by_count([1, 2, 3, 4, 5], 2)
        assert windows == [[1, 2], [3, 4], [5]]

    def test_window_by_count_exact_multiple(self) -> None:
        sp = StreamProcessor()
        windows = sp.window_by_count([1, 2, 3, 4], 2)
        assert windows == [[1, 2], [3, 4]]

    def test_window_by_time_groups_by_timestamp(self) -> None:
        sp = StreamProcessor()
        events = [
            {"value": 1, "timestamp": 0.0},
            {"value": 2, "timestamp": 1.0},
            {"value": 3, "timestamp": 5.0},
        ]
        windows = sp.window_by_time(events, 2.0)
        assert len(windows) == 2
        assert windows[0] == [{"value": 1, "timestamp": 0.0}, {"value": 2, "timestamp": 1.0}]
        assert windows[1] == [{"value": 3, "timestamp": 5.0}]

    def test_aggregate_sums_values(self) -> None:
        sp = StreamProcessor()
        result = sp.aggregate([1, 2, 3, 4], lambda vals: sum(vals))
        assert result == 10

    def test_aggregate_on_empty_stream(self) -> None:
        sp = StreamProcessor()
        assert sp.aggregate([], lambda vals: sum(vals)) == 0

    def test_filter_stream_keeps_matching(self) -> None:
        sp = StreamProcessor()
        result = sp.filter_stream([1, 2, 3, 4, 5], lambda x: x % 2 == 0)
        assert result == [2, 4]

    def test_filter_stream_no_matches(self) -> None:
        sp = StreamProcessor()
        assert sp.filter_stream([1, 3, 5], lambda x: x % 2 == 0) == []

    def test_get_stream_stats_tracks_windows(self) -> None:
        sp = StreamProcessor()
        sp.window_by_count([1, 2, 3, 4], 2)
        stats = sp.get_stream_stats()
        assert stats["windows"] == 2


class TestEventStore:
    """Tests for EventStore append/get/replay."""

    def test_append_and_get_events(self) -> None:
        store = EventStore()
        store.append({"id": "e1", "aggregate_id": "a1", "type": "created", "position": 1})
        store.append({"id": "e2", "aggregate_id": "a1", "type": "updated", "position": 2})
        events = store.get_events("a1")
        assert len(events) == 2
        assert events[0]["id"] == "e1"
        assert events[1]["id"] == "e2"

    def test_get_events_unknown_aggregate_is_empty(self) -> None:
        store = EventStore()
        assert store.get_events("nope") == []

    def test_get_events_by_type(self) -> None:
        store = EventStore()
        store.append({"id": "e1", "aggregate_id": "a1", "type": "created", "position": 1})
        store.append({"id": "e2", "aggregate_id": "a2", "type": "created", "position": 2})
        store.append({"id": "e3", "aggregate_id": "a1", "type": "updated", "position": 3})
        created = store.get_events_by_type("created")
        assert len(created) == 2
        assert all(e["type"] == "created" for e in created)

    def test_get_events_by_type_unknown_type_is_empty(self) -> None:
        store = EventStore()
        assert store.get_events_by_type("nope") == []

    def test_get_all_events_returns_everything(self) -> None:
        store = EventStore()
        store.append({"id": "e1", "aggregate_id": "a1", "type": "created", "position": 1})
        store.append({"id": "e2", "aggregate_id": "a2", "type": "created", "position": 2})
        all_events = store.get_all_events()
        assert len(all_events) == 2
        assert all_events[0]["id"] == "e1"
        assert all_events[1]["id"] == "e2"

    def test_replay_events_from_position(self) -> None:
        store = EventStore()
        for i in range(5):
            store.append({"id": f"e{i}", "aggregate_id": "a1", "type": "t", "position": i + 1})
        replayed = store.replay_events(3)
        assert len(replayed) == 3
        assert replayed[0]["id"] == "e2"
        assert replayed[-1]["id"] == "e4"

    def test_replay_events_from_zero(self) -> None:
        store = EventStore()
        store.append({"id": "e1", "aggregate_id": "a1", "type": "t", "position": 1})
        replayed = store.replay_events(0)
        assert len(replayed) == 1

    def test_replay_events_beyond_end_is_empty(self) -> None:
        store = EventStore()
        store.append({"id": "e1", "aggregate_id": "a1", "type": "t", "position": 1})
        assert store.replay_events(99) == []

    def test_get_event_count(self) -> None:
        store = EventStore()
        assert store.get_event_count() == 0
        store.append({"id": "e1", "aggregate_id": "a1", "type": "t", "position": 1})
        store.append({"id": "e2", "aggregate_id": "a2", "type": "t", "position": 2})
        assert store.get_event_count() == 2

    def test_append_assigns_monotonic_positions(self) -> None:
        store = EventStore()
        e1 = store.append({"id": "e1", "aggregate_id": "a1", "type": "t"})
        e2 = store.append({"id": "e2", "aggregate_id": "a1", "type": "t"})
        assert e2["position"] == e1["position"] + 1
