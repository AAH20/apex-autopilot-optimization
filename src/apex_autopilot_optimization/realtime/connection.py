"""Connection manager for tracking real-time client connections."""
from __future__ import annotations

import uuid
from typing import Any


class ConnectionManager:
    """Manage real-time client connections with metadata and broadcast."""

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, Any]] = {}

    def add_connection(self, conn_id: str, metadata: dict[str, Any]) -> None:
        """Add or update a connection with the given ID and metadata."""
        self._connections[conn_id] = {"metadata": metadata, "inbox": []}

    def remove_connection(self, conn_id: str) -> None:
        """Remove a connection by ID."""
        del self._connections[conn_id]

    def get_connection(self, conn_id: str) -> dict[str, Any]:
        """Return the connection record for the given ID."""
        return self._connections[conn_id]

    def get_all_connections(self) -> dict[str, dict[str, Any]]:
        """Return all connection records."""
        return dict(self._connections)

    def get_connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)

    def broadcast(self, message: str) -> None:
        """Broadcast a message to all connected clients."""
        for conn in self._connections.values():
            conn["inbox"].append(message)

    def get_health(self) -> dict[str, Any]:
        """Return health status based on connection count."""
        count = self.get_connection_count()
        return {
            "status": "healthy" if count > 0 else "degraded",
            "connection_count": count,
        }
