"""Edge-to-cloud synchronization with conflict resolution."""
from __future__ import annotations

import threading
import time
from typing import Any, Protocol

from apex_autopilot_optimization.edge.config import EdgeConfig


class CloudClient(Protocol):
    """Minimal cloud backend interface used by EdgeCloudSync."""

    def upload(self, key: str, data: Any) -> bool: ...

    def download(self, key: str) -> Any: ...


class InMemoryCloudClient:
    """Dependency-free cloud client used as the default backend.

    Stores payloads in a dict so the sync layer can be exercised without
    network access. Suitable for testing and fully offline deployments.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def upload(self, key: str, data: Any) -> bool:
        self._store[key] = data
        return True

    def download(self, key: str) -> Any:
        return self._store.get(key)


class EdgeCloudSync:
    """Synchronizes edge data with a cloud backend.

    Supports bidirectional sync, sync-status tracking, and deterministic
    conflict resolution between local and remote payloads.
    """

    CONFLICT_STRATEGIES = ("local", "remote", "timestamp", "merge")

    def __init__(
        self,
        config: EdgeConfig,
        client: CloudClient | None = None,
    ) -> None:
        self.config = config
        self._client = client if client is not None else InMemoryCloudClient()
        self._last_sync_time: float | None = None
        self._last_status: str = "never"
        self._sync_count = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Sync operations
    # ------------------------------------------------------------------
    def sync_to_cloud(self, data: Any) -> str:
        """Upload ``data`` to the cloud.

        Returns the resulting status string: "skipped" in offline mode,
        "success" on a successful upload, "failed" otherwise.
        """
        if self.config.offline_mode:
            with self._lock:
                self._last_status = "skipped"
            return "skipped"
        key = f"edge/{self.config.node_id}/data"
        ok = self._client.upload(key, data)
        with self._lock:
            self._sync_count += 1
            if ok:
                self._last_status = "success"
                self._last_sync_time = time.time()
            else:
                self._last_status = "failed"
        return self._last_status

    def sync_from_cloud(self) -> Any:
        """Download the latest payload published for this node."""
        key = f"edge/{self.config.node_id}/commands"
        return self._client.download(key)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def get_sync_status(self) -> dict[str, Any]:
        """Return the current synchronization status."""
        with self._lock:
            return {
                "node_id": self.config.node_id,
                "last_sync_time": self._last_sync_time,
                "last_status": self._last_status,
                "sync_count": self._sync_count,
                "offline_mode": self.config.offline_mode,
            }

    def get_last_sync_time(self) -> float | None:
        """Return the timestamp of the last successful sync, or None."""
        with self._lock:
            return self._last_sync_time

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------
    def resolve_conflicts(
        self,
        local: Any,
        remote: Any,
        strategy: str = "timestamp",
    ) -> Any:
        """Resolve a conflict between ``local`` and ``remote`` payloads.

        Strategies:
            "local":    always keep the local payload.
            "remote":   always keep the remote payload.
            "timestamp": keep the payload with the larger "timestamp" key
                        (ties go to local).
            "merge":    shallow-merge mappings (local wins on key
                        conflicts); falls back to "timestamp" for
                        non-mapping payloads.

        Raises ValueError for an unknown strategy.
        """
        if strategy not in self.CONFLICT_STRATEGIES:
            raise ValueError(
                f"unknown conflict strategy {strategy!r}; "
                f"expected one of {self.CONFLICT_STRATEGIES}"
            )
        if strategy == "local":
            return local
        if strategy == "remote":
            return remote
        if strategy == "timestamp":
            local_ts = local.get("timestamp", 0) if isinstance(local, dict) else 0
            remote_ts = remote.get("timestamp", 0) if isinstance(remote, dict) else 0
            return remote if remote_ts > local_ts else local
        # merge
        if isinstance(local, dict) and isinstance(remote, dict):
            merged = dict(remote)
            merged.update(local)
            return merged
        return self.resolve_conflicts(local, remote, strategy="timestamp")
