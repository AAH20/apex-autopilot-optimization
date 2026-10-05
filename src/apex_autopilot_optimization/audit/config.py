"""Audit configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AuditConfig:
    """Configuration for audit logging.

    Attributes:
        enabled: Whether audit logging is active.
        persistent: Whether events are persisted to storage.
        storage_path: File path for persistent audit log storage.
        max_events: Maximum number of events to retain in memory.
        retention_days: Number of days to retain audit events.
        tamper_evident: Whether to use hash-chained tamper evidence.
    """

    enabled: bool = True
    persistent: bool = False
    storage_path: str = ""
    max_events: int = 10000
    retention_days: int = 90
    tamper_evident: bool = True
