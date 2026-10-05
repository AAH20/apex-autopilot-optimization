"""Configuration for key rotation policies."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeyRotationConfig:
    """Configuration for automatic key rotation."""

    rotation_interval_days: int = 30
    grace_period_days: int = 7
    max_active_keys: int = 5
    auto_rotate: bool = True


@dataclass
class SecretRotationPolicy:
    """Policy defining how secrets should be rotated."""

    name: str
    interval_days: int
    auto_rotate: bool
    notification_channels: list[str] = field(default_factory=list)
