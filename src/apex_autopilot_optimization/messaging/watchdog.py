"""Offboard setpoint-loss watchdog.

Tracks when the last valid offboard setpoint was received and reports loss
once the silence exceeds ``timeout_sec`` (contract: 500 ms). On loss the
bridge exits OFFBOARD -> HOLD/LOITER.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class SetpointWatchdog:
    """Watchdog for the 10 Hz offboard setpoint heartbeat.

    Args:
        timeout_sec: Silence duration after which the setpoint is considered
            lost (default 0.5 s per the setpoint contract).
        clock: Callable returning the current time (defaults to
            ``time.time``). Injected for deterministic tests.
    """

    def __init__(
        self,
        timeout_sec: float = 0.5,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.timeout_sec = float(timeout_sec)
        self._clock = clock
        self._last_setpoint_ts: float | None = None
        self.loss_count = 0

    def record_setpoint(self, timestamp: float | None = None) -> None:
        """Mark that a valid setpoint was (re)ceived at ``timestamp``."""
        self._last_setpoint_ts = float(timestamp) if timestamp is not None else float(self._clock())

    def is_lost(self, now: float | None = None) -> bool:
        """Return True if no setpoint has arrived within ``timeout_sec``.

        Returns False when no setpoint has ever been recorded (avoids
        declaring loss on a cold bridge before streaming begins).
        """
        if self._last_setpoint_ts is None:
            return False
        now = self._clock() if now is None else float(now)
        return (now - self._last_setpoint_ts) > self.timeout_sec

    def time_since_setpoint(self, now: float | None = None) -> float | None:
        """Seconds since the last setpoint, or None if never recorded."""
        if self._last_setpoint_ts is None:
            return None
        now = self._clock() if now is None else float(now)
        return now - self._last_setpoint_ts

    def check(self, now: float | None = None) -> bool:
        """Return True if setpoint loss is detected (and count it)."""
        if self.is_lost(now):
            self.loss_count += 1
            return True
        return False

    @property
    def last_setpoint_ts(self) -> float | None:
        return self._last_setpoint_ts
