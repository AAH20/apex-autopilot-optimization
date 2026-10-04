"""WebSocket server for real-time channel-based messaging."""
from __future__ import annotations

import uuid
from typing import Any, Callable


class WebSocketServer:
    """A WebSocket server managing channel subscriptions and broadcasts."""

    def __init__(self) -> None:
        self._running = False
        self.host = ""
        self.port = 0
        self._connections: dict[str, dict[str, Any]] = {}

    def start(self, host: str, port: int) -> None:
        """Start the server on the given host and port."""
        self.host = host
        self.port = port
        self._running = True

    def stop(self) -> None:
        """Stop the server."""
        self._running = False

    def subscribe(self, channel: str, handler: Callable[[str], None]) -> str:
        """Subscribe a handler to a channel, returning a connection ID."""
        conn_id = str(uuid.uuid4())
        self._connections[conn_id] = {"channel": channel, "handler": handler}
        return conn_id

    def unsubscribe(self, channel: str, handler: Callable[[str], None]) -> None:
        """Remove a handler from a channel."""
        to_remove = [
            cid
            for cid, conn in self._connections.items()
            if conn["channel"] == channel and conn["handler"] is handler
        ]
        for cid in to_remove:
            del self._connections[cid]

    def broadcast(self, channel: str, message: str) -> None:
        """Broadcast a message to all handlers subscribed to a channel."""
        for conn in self._connections.values():
            if conn["channel"] == channel:
                conn["handler"](message)

    def get_connections(self) -> list[dict[str, Any]]:
        """Return all active connection records."""
        return [
            {"id": cid, "channel": conn["channel"]}
            for cid, conn in self._connections.items()
        ]

    def get_connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)

    def is_running(self) -> bool:
        """Return whether the server is running."""
        return self._running
