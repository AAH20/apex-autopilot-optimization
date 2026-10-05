"""Notification data models: priority, channel, notification, and config."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class NotificationPriority(IntEnum):
    """Priority levels for notifications (lower value = higher urgency)."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class NotificationChannel(Enum):
    """Delivery channels for notifications."""

    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    SLACK = "slack"
    PUSH = "push"


@dataclass
class Notification:
    """A single notification to be delivered."""

    id: str
    title: str
    message: str
    priority: NotificationPriority
    channel: NotificationChannel
    recipient: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationConfig:
    """Configuration for the notification system."""

    enabled: bool = True
    default_channel: NotificationChannel = NotificationChannel.EMAIL
    retry_count: int = 3
    retry_delay_seconds: float = 1.0
    rate_limit_per_minute: int = 60
