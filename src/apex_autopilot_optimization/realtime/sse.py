"""Server-Sent Events endpoint for real-time channel publishing."""
from __future__ import annotations

import uuid
from typing import Any, Callable


class SSEEndpoint:
    """An SSE endpoint managing channel subscribers and message publishing."""

    def __init__(self) -> None:
        self._subscribers: dict[str, dict[str, Any]] = {}

    def subscribe(
        self,
        channel: str,
        handler: Callable[[str], None] | None = None,
    ) -> str:
        """Subscribe to a channel, returning a subscriber ID."""
        sub_id = str(uuid.uuid4())
        self._subscribers[sub_id] = {"channel": channel, "handler": handler}
        return sub_id

    def unsubscribe(self, channel: str) -> None:
        """Remove all subscribers for a channel."""
        to_remove = [
            sid
            for sid, sub in self._subscribers.items()
            if sub["channel"] == channel
        ]
        for sid in to_remove:
            del self._subscribers[sid]

    def publish(self, channel: str, message: str) -> None:
        """Publish a message to all subscribers of a channel."""
        for sub in self._subscribers.values():
            if sub["channel"] == channel and sub["handler"] is not None:
                sub["handler"](message)

    def get_subscribers(self, channel: str) -> list[str]:
        """Return subscriber IDs for a channel."""
        return [
            sid
            for sid, sub in self._subscribers.items()
            if sub["channel"] == channel
        ]

    def get_connection_count(self) -> int:
        """Return the total number of subscribers."""
        return len(self._subscribers)
