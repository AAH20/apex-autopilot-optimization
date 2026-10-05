"""Per-owner resource quota tracking."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from apex_autopilot_optimization.resource.allocation import (
    ResourceType,
    _validate_amount,
)

__all__ = ["ResourceQuota"]


@dataclass
class ResourceQuota:
    """Quota record for one (resource_type, owner) pair.

    ``used`` is the amount currently allocated; ``reserved`` is the amount
    held by in-flight reservations that have not yet been allocated or
    released. Both count against ``limit``. Instances are mutated by
    ResourceManager, which serializes access; callers must not mutate a
    quota concurrently from multiple threads.
    """

    resource_type: ResourceType
    owner: str
    limit: float
    used: float = 0.0
    reserved: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, ResourceType):
            raise TypeError(
                "resource_type must be a ResourceType, got "
                f"{type(self.resource_type).__name__}"
            )
        if not isinstance(self.owner, str) or not self.owner:
            raise ValueError("owner must be a non-empty string")
        for name in ("limit", "used", "reserved"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError(f"{name} must be a number, got {type(value).__name__}")
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a non-negative finite number, got {value}")
            setattr(self, name, value)

    def _check_match(self, resource_type: ResourceType, owner: str) -> None:
        if resource_type != self.resource_type:
            raise ValueError(
                f"resource type mismatch: {resource_type!r} does not match {self.resource_type!r}"
            )
        if owner != self.owner:
            raise ValueError(f"owner mismatch: {owner!r} does not match {self.owner!r}")

    def check_quota(self, resource_type: ResourceType, owner: str, amount: float) -> bool:
        """Return True if ``amount`` fits within the limit, accounting for
        both ``used`` and ``reserved``."""
        self._check_match(resource_type, owner)
        _validate_amount(amount)
        return self.used + self.reserved + amount <= self.limit

    def reserve(self, resource_type: ResourceType, owner: str, amount: float) -> bool:
        """Reserve ``amount`` against the quota. Returns True on success,
        False if the reservation would exceed the limit."""
        self._check_match(resource_type, owner)
        _validate_amount(amount)
        if not self.check_quota(resource_type, owner, amount):
            return False
        self.reserved += amount
        return True

    def release_reservation(self, resource_type: ResourceType, owner: str, amount: float) -> float:
        """Release a previous reservation of ``amount``. Returns the
        remaining reserved amount. Raises ValueError if ``amount`` exceeds
        the currently reserved amount."""
        self._check_match(resource_type, owner)
        _validate_amount(amount)
        if amount > self.reserved:
            raise ValueError(
                f"cannot release {amount}: only {self.reserved} is reserved"
            )
        self.reserved -= amount
        return self.reserved

    def get_quota_status(self, resource_type: ResourceType, owner: str) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the quota state."""
        self._check_match(resource_type, owner)
        available = max(0.0, self.limit - self.used - self.reserved)
        utilization = (self.used / self.limit) if self.limit > 0 else 0.0
        return {
            "resource_type": self.resource_type.value,
            "owner": self.owner,
            "limit": self.limit,
            "used": self.used,
            "reserved": self.reserved,
            "available": available,
            "utilization": utilization,
        }
