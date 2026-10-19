"""Latching safety/governance veto manager.

Implements the veto latch from the setpoint contract (§8):

* Veto types: CLEAR(0), SOFT_HOLD(1), HARD_EMERGENCY(2).
* Latching: re-published at 1 Hz while active (TRANSIENT_LOCAL semantics).
* Fleet-wide: ``drone_id == 0`` applies to every vehicle.
* Authority chain: ``apex/governance`` > ``apex/safety`` > ``apex/planner`` >
  ``operator``. A veto can only be cleared by the same or a higher authority.
* Expiry: ``valid_until`` (0 = indefinite); auto-expires unless
  ``require_clear_ack`` is set.
* Precedence: HARD_EMERGENCY overrides SOFT_HOLD overrides normal operation.
"""

from __future__ import annotations

import time
from collections.abc import Callable

# Veto type codes (mirror apex_control_msgs/Veto)
VETO_CLEAR = 0
VETO_SOFT_HOLD = 1
VETO_HARD_EMERGENCY = 2

# Authority rank (higher = more authoritative)
AUTHORITY_RANK: dict[str, int] = {
    "apex/governance": 4,
    "apex/safety": 3,
    "apex/planner": 2,
    "operator": 1,
}

# Republish interval for an active veto (1 Hz, per contract).
VETO_REPUBLISH_INTERVAL_SEC = 1.0


class Veto:
    """A veto record mirroring apex_control_msgs/Veto."""

    def __init__(
        self,
        *,
        drone_id: int = 0,
        veto_type: int = VETO_CLEAR,
        severity: int = 1,
        reason: str = "",
        authority: str = "operator",
        valid_until: float = 0.0,
        require_clear_ack: bool = False,
        header: object = None,
        stamp: float | None = None,
    ) -> None:
        self.drone_id = int(drone_id)  # 0 = fleet-wide
        self.veto_type = int(veto_type)
        self.severity = int(severity)
        self.reason = reason
        self.authority = authority
        self.valid_until = float(valid_until)  # 0 = indefinite
        self.require_clear_ack = bool(require_clear_ack)
        self.header = header
        self.stamp = float(stamp if stamp is not None else time.time())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Veto(drone_id={self.drone_id}, type={self.veto_type}, "
            f"authority={self.authority!r}, valid_until={self.valid_until})"
        )


class VetoManager:
    """Manages the current latched veto for a vehicle (or fleet)."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._current: Veto | None = None
        self._last_republish: float = 0.0

    # -- issue / clear -----------------------------------------------------

    def issue(self, veto: Veto, now: float | None = None) -> Veto | None:
        """Record a new veto, applying precedence rules.

        A CLEAR veto attempts to release the latch. Any other type is merged
        by precedence (HARD > SOFT > normal); for equal type the higher-or
        equal authority wins. Returns the active veto after the merge, or
        None if cleared.
        """
        now = self._clock() if now is None else float(now)
        veto.stamp = now

        if veto.veto_type == VETO_CLEAR:
            self._current = None
            self._last_republish = 0.0
            return None

        current = self._current
        if current is None:
            self._current = veto
            return veto

        if self._outranks(veto, current):
            self._current = veto
            return veto
        return current

    def clear(self, authority: str, now: float | None = None) -> bool:
        """Attempt to clear the active veto by ``authority``.

        Returns True if cleared. Requires the clearing authority to be the
        same or higher than the veto's issuing authority (governance clears
        anything).
        """
        now = self._clock() if now is None else float(now)
        current = self._current
        if current is None:
            return False

        rank = AUTHORITY_RANK.get(authority, 0)
        issuing_rank = AUTHORITY_RANK.get(current.authority, 0)
        if authority == "apex/governance" or rank >= issuing_rank:
            self._current = None
            self._last_republish = 0.0
            return True
        return False

    # -- query -------------------------------------------------------------

    def active(self, now: float | None = None) -> Veto | None:
        """Return the currently active veto, or None.

        A veto is considered inactive once ``valid_until`` passes, unless
        ``require_clear_ack`` is set (then it stays latched until an explicit
        CLEAR).
        """
        now = self._clock() if now is None else float(now)
        current = self._current
        if current is None:
            return None
        if (
            current.valid_until > 0.0
            and now > current.valid_until
            and not current.require_clear_ack
        ):
            self._current = None
            self._last_republish = 0.0
            return None
        return current

    def is_active(self, now: float | None = None) -> bool:
        return self.active(now) is not None

    def veto_type(self, now: float | None = None) -> int:
        active = self.active(now)
        return active.veto_type if active is not None else VETO_CLEAR

    def should_republish(self, now: float | None = None) -> bool:
        """True if an active veto is due for its 1 Hz republish."""
        now = self._clock() if now is None else float(now)
        if self._current is None:
            return False
        if self._last_republish <= 0.0:
            return True
        return (now - self._last_republish) >= VETO_REPUBLISH_INTERVAL_SEC

    def mark_republished(self, now: float | None = None) -> None:
        now = self._clock() if now is None else float(now)
        self._last_republish = now

    # -- helpers -----------------------------------------------------------

    def _outranks(self, candidate: Veto, current: Veto) -> bool:
        """True if ``candidate`` should displace ``current``."""
        # Higher veto type always wins.
        if candidate.veto_type != current.veto_type:
            return candidate.veto_type > current.veto_type
        # Same type: higher-or-equal authority wins.
        cand_rank = AUTHORITY_RANK.get(candidate.authority, 0)
        cur_rank = AUTHORITY_RANK.get(current.authority, 0)
        return cand_rank >= cur_rank
