"""Tests for the notification system."""
from __future__ import annotations

import time

from apex_autopilot_optimization.notify import (
    Notification,
    NotificationChannel,
    NotificationConfig,
    NotificationManager,
    NotificationPriority,
)


def make_notification(
    nid: str = "n1",
    recipient: str = "user@example.com",
    priority: NotificationPriority = NotificationPriority.NORMAL,
    channel: NotificationChannel = NotificationChannel.EMAIL,
) -> Notification:
    """Helper to build a notification with sensible defaults."""
    return Notification(
        id=nid,
        title="Test Title",
        message="Test message body",
        priority=priority,
        channel=channel,
        recipient=recipient,
        timestamp=1234567890.0,
    )


class TestNotificationPriority:
    """Tests for NotificationPriority enumeration."""

    def test_all_priorities_exist(self) -> None:
        assert NotificationPriority.CRITICAL is not None
        assert NotificationPriority.HIGH is not None
        assert NotificationPriority.NORMAL is not None
        assert NotificationPriority.LOW is not None

    def test_priority_ordering(self) -> None:
        assert NotificationPriority.CRITICAL < NotificationPriority.HIGH
        assert NotificationPriority.HIGH < NotificationPriority.NORMAL
        assert NotificationPriority.NORMAL < NotificationPriority.LOW

    def test_priorities_are_distinct(self) -> None:
        priorities = list(NotificationPriority)
        assert len(priorities) == 4
        assert len(set(priorities)) == 4


class TestNotificationChannel:
    """Tests for NotificationChannel enumeration."""

    def test_all_channels_exist(self) -> None:
        assert NotificationChannel.EMAIL is not None
        assert NotificationChannel.SMS is not None
        assert NotificationChannel.WEBHOOK is not None
        assert NotificationChannel.SLACK is not None
        assert NotificationChannel.PUSH is not None

    def test_channels_are_distinct(self) -> None:
        channels = list(NotificationChannel)
        assert len(channels) == 5
        assert len(set(channels)) == 5


class TestNotification:
    """Tests for Notification dataclass creation."""

    def test_creation_with_all_fields(self) -> None:
        notification = Notification(
            id="n1",
            title="Alert",
            message="Something happened",
            priority=NotificationPriority.HIGH,
            channel=NotificationChannel.SLACK,
            recipient="ops@example.com",
            timestamp=1234567890.0,
            metadata={"source": "monitor"},
        )
        assert notification.id == "n1"
        assert notification.title == "Alert"
        assert notification.message == "Something happened"
        assert notification.priority == NotificationPriority.HIGH
        assert notification.channel == NotificationChannel.SLACK
        assert notification.recipient == "ops@example.com"
        assert notification.timestamp == 1234567890.0
        assert notification.metadata == {"source": "monitor"}

    def test_default_metadata_is_empty_dict(self) -> None:
        notification = make_notification()
        assert notification.metadata == {}

    def test_equal_field_values_produce_equal_notifications(self) -> None:
        n1 = make_notification(nid="same")
        n2 = make_notification(nid="same")
        assert n1 == n2

    def test_different_ids_produce_unequal_notifications(self) -> None:
        n1 = make_notification(nid="a")
        n2 = make_notification(nid="b")
        assert n1 != n2


class TestNotificationManagerSend:
    """Tests for NotificationManager.send and broadcast."""

    def test_send_stores_notification(self) -> None:
        manager = NotificationManager()
        manager.send(make_notification(nid="s1"))
        assert manager.get_notification_count() == 1

    def test_send_multiple_notifications(self) -> None:
        manager = NotificationManager()
        for i in range(3):
            manager.send(make_notification(nid=f"s{i}"))
        assert manager.get_notification_count() == 3

    def test_broadcast_stores_one_per_channel(self) -> None:
        manager = NotificationManager()
        manager.broadcast(
            make_notification(nid="b1"),
            [NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.SLACK],
        )
        assert manager.get_notification_count() == 3

    def test_broadcast_assigns_each_channel(self) -> None:
        manager = NotificationManager()
        manager.broadcast(
            make_notification(nid="b2"),
            [NotificationChannel.EMAIL, NotificationChannel.SMS],
        )
        channels = {n.channel for n in manager.get_notifications("user@example.com")}
        assert channels == {NotificationChannel.EMAIL, NotificationChannel.SMS}

    def test_broadcast_produces_distinct_ids(self) -> None:
        manager = NotificationManager()
        manager.broadcast(
            make_notification(nid="b3"),
            [NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.PUSH],
        )
        ids = [n.id for n in manager.get_notifications("user@example.com")]
        assert len(ids) == len(set(ids))


class TestNotificationManagerQuery:
    """Tests for querying notifications by recipient and priority."""

    def test_get_notifications_by_recipient(self) -> None:
        manager = NotificationManager()
        manager.send(make_notification(nid="r1", recipient="a@b.com"))
        manager.send(make_notification(nid="r2", recipient="c@d.com"))
        manager.send(make_notification(nid="r3", recipient="a@b.com"))
        result = manager.get_notifications("a@b.com")
        assert len(result) == 2
        assert all(n.recipient == "a@b.com" for n in result)

    def test_get_notifications_unknown_recipient_returns_empty(self) -> None:
        manager = NotificationManager()
        manager.send(make_notification(nid="r4", recipient="a@b.com"))
        assert manager.get_notifications("nobody@nowhere.com") == []

    def test_get_notifications_by_priority(self) -> None:
        manager = NotificationManager()
        manager.send(make_notification(nid="p1", priority=NotificationPriority.CRITICAL))
        manager.send(make_notification(nid="p2", priority=NotificationPriority.NORMAL))
        manager.send(
            make_notification(
                nid="p3",
                recipient="other@example.com",
                priority=NotificationPriority.CRITICAL,
            )
        )
        result = manager.get_notifications_by_priority(NotificationPriority.CRITICAL)
        assert len(result) == 2
        assert all(n.priority == NotificationPriority.CRITICAL for n in result)

    def test_get_notifications_by_priority_empty_when_no_match(self) -> None:
        manager = NotificationManager()
        manager.send(make_notification(nid="p4", priority=NotificationPriority.LOW))
        assert manager.get_notifications_by_priority(NotificationPriority.CRITICAL) == []


class TestNotificationManagerCountClear:
    """Tests for count and clear operations."""

    def test_count_is_zero_when_empty(self) -> None:
        manager = NotificationManager()
        assert manager.get_notification_count() == 0

    def test_clear_removes_all_notifications(self) -> None:
        manager = NotificationManager()
        manager.send(make_notification(nid="c1"))
        manager.send(make_notification(nid="c2"))
        manager.clear_notifications()
        assert manager.get_notification_count() == 0
        assert manager.get_notifications("user@example.com") == []


class TestNotificationConfig:
    """Tests for NotificationConfig dataclass."""

    def test_creation_with_explicit_values(self) -> None:
        config = NotificationConfig(
            enabled=False,
            default_channel=NotificationChannel.SLACK,
            retry_count=5,
            retry_delay_seconds=2.5,
            rate_limit_per_minute=120,
        )
        assert config.enabled is False
        assert config.default_channel == NotificationChannel.SLACK
        assert config.retry_count == 5
        assert config.retry_delay_seconds == 2.5
        assert config.rate_limit_per_minute == 120

    def test_creation_with_defaults(self) -> None:
        config = NotificationConfig()
        assert config.enabled is True
        assert isinstance(config.default_channel, NotificationChannel)
        assert config.retry_count >= 0
        assert config.retry_delay_seconds >= 0.0
        assert config.rate_limit_per_minute > 0
