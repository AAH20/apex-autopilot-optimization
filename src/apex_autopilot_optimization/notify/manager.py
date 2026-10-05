"""Notification manager: send, broadcast, query, and clear notifications."""

from __future__ import annotations

from apex_autopilot_optimization.notify.models import (
    Notification,
    NotificationChannel,
    NotificationPriority,
)


class NotificationManager:
    """Manages sending, storing, and querying notifications."""

    def __init__(self) -> None:
        self._notifications: list[Notification] = []

    def send(self, notification: Notification) -> None:
        """Store a single notification."""
        self._notifications.append(notification)

    def broadcast(
        self,
        notification: Notification,
        channels: list[NotificationChannel],
    ) -> None:
        """Send a notification to multiple channels, one per channel."""
        for channel in channels:
            variant = Notification(
                id=f"{notification.id}-{channel.value}",
                title=notification.title,
                message=notification.message,
                priority=notification.priority,
                channel=channel,
                recipient=notification.recipient,
                timestamp=notification.timestamp,
                metadata=dict(notification.metadata),
            )
            self._notifications.append(variant)

    def get_notifications(self, recipient: str) -> list[Notification]:
        """Return all notifications for a given recipient."""
        return [n for n in self._notifications if n.recipient == recipient]

    def get_notifications_by_priority(self, priority: NotificationPriority) -> list[Notification]:
        """Return all notifications with the given priority."""
        return [n for n in self._notifications if n.priority == priority]

    def get_notification_count(self) -> int:
        """Return the total number of stored notifications."""
        return len(self._notifications)

    def clear_notifications(self) -> None:
        """Remove all stored notifications."""
        self._notifications.clear()
