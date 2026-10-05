"""Production-ready Server-Sent Events endpoint for real-time channel publishing."""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SSEMessage:
    """A single SSE message with optional event type, ID, and retry."""

    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def format_sse(self) -> str:
        """Format as an SSE wire-format string."""
        lines: list[str] = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.event is not None:
            lines.append(f"event: {self.event}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        # Multi-line data: each line becomes a separate data: field
        for line in self.data.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")  # blank line terminates the event
        return "\n".join(lines) + "\n"


@dataclass
class Subscriber:
    """An SSE subscriber with metadata and delivery tracking."""

    id: str
    channel: str
    handler: Callable[[str], None] | None = None
    connected_at: float = field(default_factory=time.time)
    message_count: int = 0
    last_message_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_delivery(self) -> None:
        """Record a successful message delivery."""
        self.message_count += 1
        self.last_message_at = time.time()


class SSEEndpoint:
    """Thread-safe SSE endpoint managing channel subscribers and message publishing.

    Supports subscribing/unsubscribing to channels, publishing messages to
    channel subscribers, and querying subscriber/connection counts.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, Subscriber] = {}
        self._lock = threading.RLock()

    def subscribe(
        self,
        channel: str,
        handler: Callable[[str], None] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Subscribe to a channel, returning a subscriber ID.

        Args:
            channel: The channel name to subscribe to.
            handler: Optional callback invoked with the message string on publish.
            metadata: Optional dict of subscriber metadata.

        Returns:
            A unique subscriber ID string.
        """
        sub_id = str(uuid.uuid4())
        sub = Subscriber(
            id=sub_id,
            channel=channel,
            handler=handler,
            metadata=metadata or {},
        )
        with self._lock:
            self._subscribers[sub_id] = sub
        return sub_id

    def unsubscribe(self, channel: str) -> int:
        """Remove all subscribers for a channel.

        Args:
            channel: The channel name to unsubscribe.

        Returns:
            The number of subscribers removed.
        """
        with self._lock:
            to_remove = [
                sid
                for sid, sub in self._subscribers.items()
                if sub.channel == channel
            ]
            for sid in to_remove:
                del self._subscribers[sid]
            return len(to_remove)

    def unsubscribe_by_id(self, sub_id: str) -> bool:
        """Remove a specific subscriber by ID.

        Args:
            sub_id: The subscriber ID to remove.

        Returns:
            True if the subscriber was found and removed, False otherwise.
        """
        with self._lock:
            if sub_id in self._subscribers:
                del self._subscribers[sub_id]
                return True
            return False

    def publish(self, channel: str, message: str) -> int:
        """Publish a message to all subscribers of a channel.

        Args:
            channel: The channel to publish to.
            message: The message string to deliver.

        Returns:
            The number of subscribers the message was delivered to.
        """
        delivered = 0
        with self._lock:
            targets = [
                sub
                for sub in self._subscribers.values()
                if sub.channel == channel and sub.handler is not None
            ]
        for sub in targets:
            try:
                if sub.handler is not None:
                    sub.handler(message)
                sub.record_delivery()
                delivered += 1
            except Exception:
                # Don't let one failing handler block others
                continue
        return delivered

    def publish_sse(
        self,
        channel: str,
        message: str,
        event: str | None = None,
        id: str | None = None,
        retry: int | None = None,
    ) -> int:
        """Publish a formatted SSE message to all subscribers of a channel.

        Args:
            channel: The channel to publish to.
            message: The message data.
            event: Optional SSE event type.
            id: Optional SSE event ID.
            retry: Optional retry interval in milliseconds.

        Returns:
            The number of subscribers the message was delivered to.
        """
        sse_msg = SSEMessage(data=message, event=event, id=id, retry=retry)
        return self.publish(channel, sse_msg.format_sse())

    def publish_json(self, channel: str, data: Any, event: str | None = None) -> int:
        """Publish a JSON-serialized message to all subscribers of a channel.

        Args:
            channel: The channel to publish to.
            data: Any JSON-serializable object.
            event: Optional SSE event type.

        Returns:
            The number of subscribers the message was delivered to.
        """
        return self.publish_sse(channel, json.dumps(data), event=event)

    def get_subscribers(self, channel: str) -> list[str]:
        """Return subscriber IDs for a channel.

        Args:
            channel: The channel name.

        Returns:
            List of subscriber IDs subscribed to the channel.
        """
        with self._lock:
            return [
                sid
                for sid, sub in self._subscribers.items()
                if sub.channel == channel
            ]

    def get_subscriber_info(self, sub_id: str) -> dict[str, Any] | None:
        """Return info about a specific subscriber.

        Args:
            sub_id: The subscriber ID.

        Returns:
            Dict with subscriber info, or None if not found.
        """
        with self._lock:
            sub = self._subscribers.get(sub_id)
            if sub is None:
                return None
            return {
                "id": sub.id,
                "channel": sub.channel,
                "connected_at": sub.connected_at,
                "message_count": sub.message_count,
                "last_message_at": sub.last_message_at,
                "metadata": dict(sub.metadata),
            }

    def get_connection_count(self) -> int:
        """Return the total number of subscribers."""
        with self._lock:
            return len(self._subscribers)

    def get_channel_count(self) -> int:
        """Return the number of distinct channels with subscribers."""
        with self._lock:
            return len({sub.channel for sub in self._subscribers.values()})

    def get_channels(self) -> list[str]:
        """Return a list of all channel names with subscribers."""
        with self._lock:
            return list({sub.channel for sub in self._subscribers.values()})

    def get_stats(self) -> dict[str, Any]:
        """Return endpoint statistics.

        Returns:
            Dict with connection_count, channel_count, channels, and
            per-channel subscriber counts.
        """
        with self._lock:
            channel_counts: dict[str, int] = {}
            for sub in self._subscribers.values():
                channel_counts[sub.channel] = channel_counts.get(sub.channel, 0) + 1
            return {
                "connection_count": len(self._subscribers),
                "channel_count": len(channel_counts),
                "channels": list(channel_counts.keys()),
                "channel_subscribers": channel_counts,
            }

    def clear(self) -> int:
        """Remove all subscribers.

        Returns:
            The number of subscribers removed.
        """
        with self._lock:
            count = len(self._subscribers)
            self._subscribers.clear()
            return count
