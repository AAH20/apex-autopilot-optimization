"""Tests for the real-time communication package."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from apex_autopilot_optimization.realtime import (
    ConnectionManager,
    SSEEndpoint,
    WebhookEvent,
    WebhookManager,
    WebSocketServer,
)


def _make_signature(payload: dict, secret: str) -> str:
    """Compute the expected HMAC-SHA256 signature for a payload."""
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestWebhookEvent:
    """Tests for the WebhookEvent dataclass."""

    def test_creation(self) -> None:
        event = WebhookEvent(
            event_type="test.event",
            payload={"key": "value"},
            timestamp=1234567890.0,
            signature="abc123",
        )
        assert event.event_type == "test.event"
        assert event.payload == {"key": "value"}
        assert event.timestamp == 1234567890.0
        assert event.signature == "abc123"

    def test_create_generates_timestamp_and_signature(self) -> None:
        secret = "top-secret"
        payload = {"drone": "alpha", "status": "ok"}
        event = WebhookEvent.create("telemetry", payload, secret=secret)
        assert event.event_type == "telemetry"
        assert event.payload == payload
        assert event.timestamp > 0
        assert event.signature == _make_signature(payload, secret)

    def test_create_without_secret_produces_empty_signature(self) -> None:
        event = WebhookEvent.create("telemetry", {"a": 1})
        assert event.signature == ""


class TestWebhookManager:
    """Tests for WebhookManager registration and unregistration."""

    def test_register_returns_subscription_id(self) -> None:
        mgr = WebhookManager()
        sub_id = mgr.register("https://example.com/hook", ["telemetry"])
        assert isinstance(sub_id, str)
        assert sub_id

    def test_register_stores_subscription(self) -> None:
        mgr = WebhookManager()
        sub_id = mgr.register("https://example.com/hook", ["telemetry"])
        subs = mgr.get_subscriptions()
        assert sub_id in subs
        assert subs[sub_id]["url"] == "https://example.com/hook"
        assert subs[sub_id]["events"] == ["telemetry"]

    def test_register_multiple_subscriptions_get_unique_ids(self) -> None:
        mgr = WebhookManager()
        id1 = mgr.register("https://a.com/hook", ["telemetry"])
        id2 = mgr.register("https://b.com/hook", ["alert"])
        assert id1 != id2
        assert len(mgr.get_subscriptions()) == 2

    def test_unregister_removes_subscription(self) -> None:
        mgr = WebhookManager()
        sub_id = mgr.register("https://example.com/hook", ["telemetry"])
        mgr.unregister(sub_id)
        assert sub_id not in mgr.get_subscriptions()

    def test_unregister_unknown_id_raises(self) -> None:
        mgr = WebhookManager()
        with pytest.raises(KeyError):
            mgr.unregister("does-not-exist")

    def test_unregister_only_removes_target(self) -> None:
        mgr = WebhookManager()
        id1 = mgr.register("https://a.com/hook", ["telemetry"])
        id2 = mgr.register("https://b.com/hook", ["alert"])
        mgr.unregister(id1)
        subs = mgr.get_subscriptions()
        assert id1 not in subs
        assert id2 in subs


class TestWebhookDispatch:
    """Tests for WebhookManager dispatch and delivery stats."""

    def test_dispatch_delivers_to_matching_subscription(self) -> None:
        mgr = WebhookManager()
        received: list[WebhookEvent] = []
        sub_id = mgr.register("https://example.com/hook", ["telemetry"])
        mgr.set_delivery_handler(lambda sub, event: received.append(event))
        mgr.dispatch("telemetry", {"drone": "alpha"})
        assert len(received) == 1
        assert received[0].event_type == "telemetry"
        assert received[0].payload == {"drone": "alpha"}

    def test_dispatch_skips_non_matching_event_type(self) -> None:
        mgr = WebhookManager()
        received: list[WebhookEvent] = []
        mgr.register("https://example.com/hook", ["telemetry"])
        mgr.set_delivery_handler(lambda sub, event: received.append(event))
        mgr.dispatch("alert", {"drone": "alpha"})
        assert received == []

    def test_dispatch_to_multiple_matching_subscriptions(self) -> None:
        mgr = WebhookManager()
        received: list[WebhookEvent] = []
        mgr.register("https://a.com/hook", ["telemetry"])
        mgr.register("https://b.com/hook", ["telemetry", "alert"])
        mgr.set_delivery_handler(lambda sub, event: received.append(event))
        mgr.dispatch("telemetry", {"x": 1})
        assert len(received) == 2

    def test_dispatch_wildcard_event_type_matches_all(self) -> None:
        mgr = WebhookManager()
        received: list[WebhookEvent] = []
        mgr.register("https://a.com/hook", ["*"])
        mgr.set_delivery_handler(lambda sub, event: received.append(event))
        mgr.dispatch("anything", {"x": 1})
        assert len(received) == 1

    def test_dispatch_creates_signed_event(self) -> None:
        mgr = WebhookManager(secret="s3cret")
        received: list[WebhookEvent] = []
        mgr.register("https://a.com/hook", ["telemetry"])
        mgr.set_delivery_handler(lambda sub, event: received.append(event))
        mgr.dispatch("telemetry", {"drone": "alpha"})
        assert received[0].signature == _make_signature({"drone": "alpha"}, "s3cret")

    def test_get_delivery_stats_counts_deliveries(self) -> None:
        mgr = WebhookManager()
        mgr.register("https://a.com/hook", ["telemetry"])
        mgr.set_delivery_handler(lambda sub, event: None)
        mgr.dispatch("telemetry", {"x": 1})
        mgr.dispatch("telemetry", {"x": 2})
        stats = mgr.get_delivery_stats()
        assert stats["total_deliveries"] == 2

    def test_get_delivery_stats_tracks_failures(self) -> None:
        mgr = WebhookManager()
        mgr.register("https://a.com/hook", ["telemetry"])

        def failing_handler(sub: dict, event: WebhookEvent) -> None:
            raise RuntimeError("delivery failed")

        mgr.set_delivery_handler(failing_handler)
        mgr.dispatch("telemetry", {"x": 1})
        stats = mgr.get_delivery_stats()
        assert stats["total_deliveries"] == 1
        assert stats["failed_deliveries"] == 1

    def test_get_delivery_stats_per_subscription(self) -> None:
        mgr = WebhookManager()
        sub_id = mgr.register("https://a.com/hook", ["telemetry"])
        mgr.set_delivery_handler(lambda sub, event: None)
        mgr.dispatch("telemetry", {"x": 1})
        stats = mgr.get_delivery_stats()
        assert stats["per_subscription"][sub_id] == 1


class TestWebhookSignatureVerification:
    """Tests for WebhookManager.verify_signature."""

    def test_verify_signature_valid(self) -> None:
        mgr = WebhookManager()
        payload = {"drone": "alpha", "status": "ok"}
        sig = _make_signature(payload, "secret")
        assert mgr.verify_signature(payload, sig, "secret") is True

    def test_verify_signature_invalid_secret(self) -> None:
        mgr = WebhookManager()
        payload = {"drone": "alpha"}
        sig = _make_signature(payload, "secret")
        assert mgr.verify_signature(payload, sig, "wrong") is False

    def test_verify_signature_tampered_payload(self) -> None:
        mgr = WebhookManager()
        payload = {"drone": "alpha"}
        sig = _make_signature(payload, "secret")
        tampered = {"drone": "beta"}
        assert mgr.verify_signature(tampered, sig, "secret") is False

    def test_verify_signature_empty_signature(self) -> None:
        mgr = WebhookManager()
        assert mgr.verify_signature({"a": 1}, "", "secret") is False


class TestWebSocketServer:
    """Tests for WebSocketServer start/stop and lifecycle."""

    def test_start_marks_server_running(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        assert server.is_running() is True
        server.stop()

    def test_stop_marks_server_not_running(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        server.stop()
        assert server.is_running() is False

    def test_start_stores_host_and_port(self) -> None:
        server = WebSocketServer()
        server.start("0.0.0.0", 9000)
        assert server.host == "0.0.0.0"
        assert server.port == 9000
        server.stop()

    def test_broadcast_before_start_does_not_raise(self) -> None:
        server = WebSocketServer()
        server.broadcast("chan", "msg")
        assert server.get_connection_count() == 0


class TestWebSocketSubscribe:
    """Tests for WebSocketServer subscribe/unsubscribe/broadcast."""

    def test_subscribe_adds_connection(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        server.subscribe("telemetry", lambda msg: None)
        assert server.get_connection_count() == 1
        server.stop()

    def test_subscribe_multiple_channels(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        server.subscribe("telemetry", lambda msg: None)
        server.subscribe("alert", lambda msg: None)
        assert server.get_connection_count() == 2
        server.stop()

    def test_unsubscribe_removes_connection(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        handler = lambda msg: None  # noqa: E731
        server.subscribe("telemetry", handler)
        server.unsubscribe("telemetry", handler)
        assert server.get_connection_count() == 0
        server.stop()

    def test_broadcast_delivers_to_channel_handlers(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        received: list[str] = []
        server.subscribe("telemetry", received.append)
        server.broadcast("telemetry", "hello")
        assert received == ["hello"]
        server.stop()

    def test_broadcast_only_delivers_to_matching_channel(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        telemetry: list[str] = []
        alerts: list[str] = []
        server.subscribe("telemetry", telemetry.append)
        server.subscribe("alert", alerts.append)
        server.broadcast("telemetry", "data")
        assert telemetry == ["data"]
        assert alerts == []
        server.stop()

    def test_broadcast_multiple_handlers_same_channel(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        first: list[str] = []
        second: list[str] = []
        server.subscribe("telemetry", first.append)
        server.subscribe("telemetry", second.append)
        server.broadcast("telemetry", "msg")
        assert first == ["msg"]
        assert second == ["msg"]
        server.stop()

    def test_get_connections_returns_connection_records(self) -> None:
        server = WebSocketServer()
        server.start("127.0.0.1", 8765)
        server.subscribe("telemetry", lambda msg: None)
        conns = server.get_connections()
        assert len(conns) == 1
        assert conns[0]["channel"] == "telemetry"
        server.stop()


class TestSSEEndpoint:
    """Tests for SSEEndpoint subscribe/unsubscribe/publish."""

    def test_subscribe_adds_subscriber(self) -> None:
        sse = SSEEndpoint()
        sse.subscribe("telemetry")
        assert sse.get_connection_count() == 1

    def test_subscribe_multiple_channels(self) -> None:
        sse = SSEEndpoint()
        sse.subscribe("telemetry")
        sse.subscribe("alert")
        assert sse.get_connection_count() == 2

    def test_unsubscribe_removes_subscribers_for_channel(self) -> None:
        sse = SSEEndpoint()
        sse.subscribe("telemetry")
        sse.subscribe("telemetry")
        sse.unsubscribe("telemetry")
        assert sse.get_subscribers("telemetry") == []
        assert sse.get_connection_count() == 0

    def test_unsubscribe_only_target_channel(self) -> None:
        sse = SSEEndpoint()
        sse.subscribe("telemetry")
        sse.subscribe("alert")
        sse.unsubscribe("telemetry")
        assert sse.get_subscribers("telemetry") == []
        assert len(sse.get_subscribers("alert")) == 1

    def test_publish_delivers_to_channel_subscribers(self) -> None:
        sse = SSEEndpoint()
        received: list[str] = []
        sse.subscribe("telemetry", received.append)
        sse.publish("telemetry", "data")
        assert received == ["data"]

    def test_publish_only_delivers_to_matching_channel(self) -> None:
        sse = SSEEndpoint()
        telemetry: list[str] = []
        alerts: list[str] = []
        sse.subscribe("telemetry", telemetry.append)
        sse.subscribe("alert", alerts.append)
        sse.publish("telemetry", "data")
        assert telemetry == ["data"]
        assert alerts == []

    def test_get_subscribers_returns_ids(self) -> None:
        sse = SSEEndpoint()
        sub_id = sse.subscribe("telemetry")
        assert sub_id in sse.get_subscribers("telemetry")

    def test_get_subscribers_unknown_channel_returns_empty(self) -> None:
        sse = SSEEndpoint()
        assert sse.get_subscribers("nope") == []


class TestConnectionManager:
    """Tests for ConnectionManager add/remove/get/broadcast/health."""

    def test_add_connection(self) -> None:
        mgr = ConnectionManager()
        mgr.add_connection("c1", {"client": "alpha"})
        assert mgr.get_connection_count() == 1

    def test_add_connection_stores_metadata(self) -> None:
        mgr = ConnectionManager()
        mgr.add_connection("c1", {"client": "alpha"})
        assert mgr.get_connection("c1")["metadata"] == {"client": "alpha"}

    def test_add_duplicate_connection_overwrites(self) -> None:
        mgr = ConnectionManager()
        mgr.add_connection("c1", {"client": "alpha"})
        mgr.add_connection("c1", {"client": "beta"})
        assert mgr.get_connection_count() == 1
        assert mgr.get_connection("c1")["metadata"] == {"client": "beta"}

    def test_remove_connection(self) -> None:
        mgr = ConnectionManager()
        mgr.add_connection("c1", {"client": "alpha"})
        mgr.remove_connection("c1")
        assert mgr.get_connection_count() == 0

    def test_remove_unknown_connection_raises(self) -> None:
        mgr = ConnectionManager()
        with pytest.raises(KeyError):
            mgr.remove_connection("nope")

    def test_get_connection_unknown_raises(self) -> None:
        mgr = ConnectionManager()
        with pytest.raises(KeyError):
            mgr.get_connection("nope")

    def test_get_all_connections(self) -> None:
        mgr = ConnectionManager()
        mgr.add_connection("c1", {"client": "alpha"})
        mgr.add_connection("c2", {"client": "beta"})
        all_conns = mgr.get_all_connections()
        assert set(all_conns.keys()) == {"c1", "c2"}

    def test_broadcast_delivers_to_all_connections(self) -> None:
        mgr = ConnectionManager()
        mgr.add_connection("c1", {"client": "alpha"})
        mgr.add_connection("c2", {"client": "beta"})
        mgr.broadcast("hello")
        assert mgr.get_connection("c1")["inbox"] == ["hello"]
        assert mgr.get_connection("c2")["inbox"] == ["hello"]

    def test_broadcast_no_connections_does_not_raise(self) -> None:
        mgr = ConnectionManager()
        mgr.broadcast("hello")
        assert mgr.get_connection_count() == 0

    def test_get_health_reports_status(self) -> None:
        mgr = ConnectionManager()
        mgr.add_connection("c1", {"client": "alpha"})
        health = mgr.get_health()
        assert health["status"] == "healthy"
        assert health["connection_count"] == 1

    def test_get_health_reports_degraded_when_empty(self) -> None:
        mgr = ConnectionManager()
        health = mgr.get_health()
        assert health["status"] == "degraded"
        assert health["connection_count"] == 0
