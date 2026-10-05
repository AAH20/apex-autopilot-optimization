"""Rotation policy evaluation functions."""

from __future__ import annotations

import time

from apex_autopilot_optimization.keymgmt.config import SecretRotationPolicy

DAY = 86400.0


def should_rotate(
    last_rotation: float | None,
    policy: SecretRotationPolicy,
    now: float | None = None,
) -> bool:
    """Determine if a secret should be rotated based on the policy.

    Args:
        last_rotation: Timestamp of the last rotation, or None if never rotated.
        policy: The rotation policy to evaluate against.
        now: Current timestamp (defaults to time.time()).

    Returns:
        True if rotation is needed, False otherwise.
    """
    if not policy.auto_rotate:
        return False
    if last_rotation is None:
        return True
    if now is None:
        now = time.time()
    return (now - last_rotation) >= policy.interval_days * DAY


def get_next_rotation_date(
    last_rotation: float | None,
    policy: SecretRotationPolicy,
) -> float | None:
    """Calculate the next rotation date based on the last rotation.

    Args:
        last_rotation: Timestamp of the last rotation, or None if never rotated.
        policy: The rotation policy to use.

    Returns:
        The next rotation timestamp, or None if last_rotation is None.
    """
    if last_rotation is None:
        return None
    return last_rotation + policy.interval_days * DAY
