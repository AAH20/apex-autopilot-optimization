"""Session configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Configuration for session management.

    Attributes:
        default_ttl_seconds: Default time-to-live for sessions in seconds.
        max_sessions_per_user: Maximum number of active sessions per user.
        cleanup_interval_seconds: Interval between cleanup runs in seconds.
        persistent: Whether sessions should persist across restarts.
    """

    default_ttl_seconds: int = 3600
    max_sessions_per_user: int = 5
    cleanup_interval_seconds: int = 300
    persistent: bool = False
