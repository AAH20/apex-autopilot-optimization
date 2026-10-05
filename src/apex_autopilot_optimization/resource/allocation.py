"""Resource allocation types: ResourceType, ResourceStatus, ResourceAllocation.

This module also hosts the small shared validation helpers used by the
quota and manager modules.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum

__all__ = ["ResourceAllocation", "ResourceStatus", "ResourceType"]


class ResourceType(str, Enum):
    """Types of managed resources."""

    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    NETWORK = "network"
    STORAGE = "storage"


class ResourceStatus(str, Enum):
    """Lifecycle status of a resource allocation."""

    ALLOCATED = "allocated"
    RESERVED = "reserved"
    RELEASED = "released"
    EXPIRED = "expired"


@dataclass
class ResourceAllocation:
    """A single assignment of a resource amount to an owner.

    ``expires_at`` is an optional absolute timestamp (seconds since the
    epoch). ``None`` means the allocation never expires. Expired
    allocations are treated as inactive by queries and are swept lazily.
    """

    id: str
    resource_type: ResourceType
    amount: float
    owner: str
    status: ResourceStatus
    created_at: float
    expires_at: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("id must be a non-empty string")
        if not isinstance(self.resource_type, ResourceType):
            raise TypeError(
                f"resource_type must be a ResourceType, got {type(self.resource_type).__name__}"
            )
        if not isinstance(self.owner, str) or not self.owner:
            raise ValueError("owner must be a non-empty string")
        if not isinstance(self.status, ResourceStatus):
            raise TypeError(
                f"status must be a ResourceStatus, got {type(self.status).__name__}"
            )
        _validate_amount(self.amount)
        _validate_timestamp(self.created_at, "created_at")
        if self.expires_at is not None:
            _validate_timestamp(self.expires_at, "expires_at")
            if self.expires_at < self.created_at:
                raise ValueError("expires_at must not be before created_at")

    def is_expired(self, now: float | None = None) -> bool:
        """Return True if the allocation has passed its expiry timestamp."""
        if self.expires_at is None:
            return False
        return (time.time() if now is None else now) >= self.expires_at

    @property
    def is_active(self) -> bool:
        """True while the allocation is ALLOCATED and not expired."""
        return self.status is ResourceStatus.ALLOCATED and not self.is_expired()


# ---------------------------------------------------------------------------
# Shared validation helpers (package-internal)
# ---------------------------------------------------------------------------


def _validate_amount(amount: float) -> float:
    """Validate that ``amount`` is a positive, finite number; return it as float."""
    if isinstance(amount, bool) or not isinstance(amount, int | float):
        raise TypeError(f"amount must be a number, got {type(amount).__name__}")
    value = float(amount)
    if not math.isfinite(value):
        raise ValueError("amount must be a finite number")
    if value <= 0:
        raise ValueError(f"amount must be positive, got {value}")
    return value


def _validate_owner(owner: str) -> str:
    """Validate that ``owner`` is a non-empty string."""
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner must be a non-empty string")
    return owner


def _coerce_resource_type(resource_type: ResourceType | str) -> ResourceType:
    """Coerce a ResourceType or its string value into a ResourceType."""
    if isinstance(resource_type, ResourceType):
        return resource_type
    if isinstance(resource_type, str):
        try:
            return ResourceType(resource_type.strip().lower())
        except ValueError:
            valid = ", ".join(t.value for t in ResourceType)
            raise ValueError(
                f"unknown resource type {resource_type!r}; valid types: {valid}"
            ) from None
    raise TypeError(
        f"resource_type must be a ResourceType or str, got {type(resource_type).__name__}"
    )


def _validate_timestamp(value: float, name: str) -> float:
    """Validate that ``value`` is a non-negative, finite timestamp."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a non-negative finite number, got {result}")
    return result
