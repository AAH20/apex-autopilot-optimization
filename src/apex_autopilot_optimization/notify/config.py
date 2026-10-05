"""Notification system configuration.

Exposes :class:`NotificationConfig` as the single source of runtime settings
for the notification subsystem (delivery enablement, defaults, retry policy,
and rate limiting). Re-exported from :mod:`notify.models` so the dataclass
definition lives in exactly one place.
"""
from __future__ import annotations

from apex_autopilot_optimization.notify.models import NotificationConfig

__all__ = ["NotificationConfig"]
