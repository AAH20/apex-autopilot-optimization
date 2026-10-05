"""Edge computing configuration objects."""

from __future__ import annotations

from dataclasses import dataclass

POWER_PROFILES = ("low_power", "balanced", "performance")


@dataclass
class EdgeConfig:
    """Configuration for an edge node.

    Attributes:
        node_id: Unique identifier for this edge node.
        cloud_url: Base URL of the cloud endpoint used for sync.
        sync_interval_seconds: Desired interval between cloud syncs (> 0).
        max_buffer_size: Maximum number of records held in the local
            store-and-forward buffer before the oldest are dropped (> 0).
        offline_mode: When True, the node never attempts cloud sync.
        power_profile: One of "low_power", "balanced", "performance".
    """

    node_id: str
    cloud_url: str = "https://cloud.example.com"
    sync_interval_seconds: float = 60.0
    max_buffer_size: int = 1000
    offline_mode: bool = False
    power_profile: str = "balanced"

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        if not isinstance(self.cloud_url, str) or not self.cloud_url.strip():
            raise ValueError("cloud_url must be a non-empty string")
        if self.sync_interval_seconds <= 0:
            raise ValueError("sync_interval_seconds must be positive")
        if self.max_buffer_size <= 0:
            raise ValueError("max_buffer_size must be positive")
        if self.power_profile not in POWER_PROFILES:
            raise ValueError(
                f"power_profile must be one of {POWER_PROFILES}, got {self.power_profile!r}"
            )
