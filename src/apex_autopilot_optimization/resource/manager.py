"""Thread-safe resource manager: allocation, deallocation, quotas, and
utilization tracking for finite resource pools."""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from apex_autopilot_optimization.resource.allocation import (
    ResourceAllocation,
    ResourceStatus,
    ResourceType,
    _coerce_resource_type,
    _validate_amount,
    _validate_owner,
)
from apex_autopilot_optimization.resource.quota import ResourceQuota

__all__ = ["QuotaExceededError", "ResourceError", "ResourceManager"]


class ResourceError(Exception):
    """Base class for resource management errors."""


class QuotaExceededError(ResourceError):
    """Raised when an allocation would exceed the owner's resource quota."""


class ResourceManager:
    """Manages a finite pool of resources across multiple owners.

    Args:
        capacities: Total capacity per ResourceType. Types absent from this
            mapping (and from ``default_capacity``) are treated as
            unbounded: ``get_available`` returns ``math.inf`` and
            ``get_utilization`` returns ``0.0``.
        default_capacity: Fallback capacity for resource types not present
            in ``capacities``.
        quotas: Optional per-owner limits as
            ``{(resource_type, owner): limit}``.
        clock: Timestamp source (defaults to ``time.time``); injectable for
            deterministic testing.

    All mutating operations are serialized with a reentrant lock, so a
    single manager instance is safe to share across threads.
    """

    def __init__(
        self,
        capacities: dict[ResourceType, float] | None = None,
        default_capacity: float | None = None,
        quotas: dict[tuple[ResourceType, str], float] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._capacities: dict[ResourceType, float] = dict(capacities or {})
        self._default_capacity = default_capacity
        self._quotas: dict[tuple[ResourceType, str], ResourceQuota] = {}
        self._allocations: dict[str, ResourceAllocation] = {}
        self._lock = threading.RLock()
        self._clock = clock
        for (resource_type, owner), limit in (quotas or {}).items():
            self.set_quota(resource_type, owner, limit)

    # ------------------------------------------------------------------
    # Quota management
    # ------------------------------------------------------------------

    def set_quota(
        self, resource_type: ResourceType | str, owner: str, limit: float
    ) -> ResourceQuota:
        """Create or update the quota for one (resource_type, owner) pair."""
        rt = _coerce_resource_type(resource_type)
        own = _validate_owner(owner)
        if isinstance(limit, bool) or not isinstance(limit, int | float):
            raise TypeError(f"limit must be a number, got {type(limit).__name__}")
        limit_f = float(limit)
        if not math.isfinite(limit_f) or limit_f < 0:
            raise ValueError(f"limit must be a non-negative finite number, got {limit_f}")
        with self._lock:
            quota = self._quotas.get((rt, own))
            if quota is None:
                quota = ResourceQuota(resource_type=rt, owner=own, limit=limit_f)
                self._quotas[(rt, own)] = quota
            else:
                quota.limit = limit_f
            return quota

    def get_quota(self, resource_type: ResourceType | str, owner: str) -> ResourceQuota | None:
        """Return the quota record for (resource_type, owner), or None."""
        rt = _coerce_resource_type(resource_type)
        own = _validate_owner(owner)
        with self._lock:
            return self._quotas.get((rt, own))

    def get_quota_status(
        self, resource_type: ResourceType | str, owner: str
    ) -> dict[str, Any] | None:
        """Return a JSON-serializable quota snapshot, or None if no quota
        is defined for (resource_type, owner)."""
        rt = _coerce_resource_type(resource_type)
        own = _validate_owner(owner)
        with self._lock:
            quota = self._quotas.get((rt, own))
            return quota.get_quota_status(rt, own) if quota is not None else None

    # ------------------------------------------------------------------
    # Allocation / deallocation
    # ------------------------------------------------------------------

    def allocate(
        self,
        resource_type: ResourceType | str,
        amount: float,
        owner: str,
        ttl: float | None = None,
    ) -> ResourceAllocation:
        """Allocate ``amount`` of ``resource_type`` to ``owner``.

        Args:
            resource_type: The resource type to allocate.
            amount: Positive, finite amount to allocate.
            owner: Non-empty owner identifier.
            ttl: Optional time-to-live in seconds; the allocation expires
                ``ttl`` seconds after creation.

        Returns:
            The created ResourceAllocation.

        Raises:
            ValueError: On invalid input (amount, owner, ttl, type).
            TypeError: On invalid input types.
            QuotaExceededError: If a quota exists for (resource_type, owner)
                and the allocation would exceed it.
        """
        rt = _coerce_resource_type(resource_type)
        amt = _validate_amount(amount)
        own = _validate_owner(owner)
        if ttl is not None:
            if isinstance(ttl, bool) or not isinstance(ttl, int | float):
                raise TypeError(f"ttl must be a number, got {type(ttl).__name__}")
            if not math.isfinite(float(ttl)) or ttl <= 0:
                raise ValueError(f"ttl must be a positive finite number, got {ttl}")
        with self._lock:
            self._sweep_expired_locked()
            quota = self._quotas.get((rt, own))
            if quota is not None and not quota.check_quota(rt, own, amt):
                raise QuotaExceededError(
                    f"allocation of {amt} {rt.value} for {own!r} would exceed quota "
                    f"(used={quota.used}, reserved={quota.reserved}, limit={quota.limit})"
                )
            now = self._clock()
            alloc = ResourceAllocation(
                id=uuid.uuid4().hex,
                resource_type=rt,
                amount=amt,
                owner=own,
                status=ResourceStatus.ALLOCATED,
                created_at=now,
                expires_at=now + float(ttl) if ttl is not None else None,
            )
            self._allocations[alloc.id] = alloc
            if quota is not None:
                quota.used += amt
            return alloc

    def deallocate(self, resource_type: ResourceType | str, amount: float, owner: str) -> bool:
        """Release ``amount`` of ``resource_type`` from ``owner``.

        Releases are applied FIFO across the owner's active allocations.
        A partial release of an allocation marks the original RELEASED and
        creates a new allocation for the remainder.

        Returns:
            True if the full amount was released; False if the owner has
            less than ``amount`` currently allocated.
        """
        rt = _coerce_resource_type(resource_type)
        amt = _validate_amount(amount)
        own = _validate_owner(owner)
        with self._lock:
            self._sweep_expired_locked()
            candidates = sorted(
                (
                    a
                    for a in self._allocations.values()
                    if a.resource_type is rt
                    and a.owner == own
                    and a.status is ResourceStatus.ALLOCATED
                ),
                key=lambda a: a.created_at,
            )
            if amt > sum(a.amount for a in candidates):
                return False
            quota = self._quotas.get((rt, own))
            remaining = amt
            for alloc in candidates:
                if remaining <= 0:
                    break
                take = min(remaining, alloc.amount)
                alloc.status = ResourceStatus.RELEASED
                if take < alloc.amount:
                    remainder = ResourceAllocation(
                        id=uuid.uuid4().hex,
                        resource_type=rt,
                        amount=alloc.amount - take,
                        owner=own,
                        status=ResourceStatus.ALLOCATED,
                        created_at=self._clock(),
                        expires_at=alloc.expires_at,
                    )
                    self._allocations[remainder.id] = remainder
                if quota is not None:
                    quota.used = max(0.0, quota.used - take)
                remaining -= take
            return True

    def sweep_expired(self) -> list[ResourceAllocation]:
        """Mark all expired allocations as EXPIRED and free their quota
        usage. Returns the allocations that were expired by this call."""
        with self._lock:
            return self._sweep_expired_locked()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_available(self, resource_type: ResourceType | str) -> float:
        """Return the unallocated capacity for a resource type, or
        ``math.inf`` if the type is unbounded."""
        rt = _coerce_resource_type(resource_type)
        with self._lock:
            self._sweep_expired_locked()
            capacity = self._capacity_for(rt)
            if capacity is None:
                return math.inf
            return max(0.0, capacity - self._allocated_locked(rt))

    def get_allocated(self, resource_type: ResourceType | str) -> float:
        """Return the total active (non-expired, non-released) allocation
        for a resource type across all owners."""
        rt = _coerce_resource_type(resource_type)
        with self._lock:
            self._sweep_expired_locked()
            return self._allocated_locked(rt)

    def get_reserved(self, resource_type: ResourceType | str) -> float:
        """Return the total reserved (not yet allocated) amount for a
        resource type across all owner quotas."""
        rt = _coerce_resource_type(resource_type)
        with self._lock:
            return sum(
                quota.reserved for (quota_rt, _), quota in self._quotas.items() if quota_rt is rt
            )

    def get_utilization(self, resource_type: ResourceType | str) -> float:
        """Return the fraction of capacity currently allocated, in
        [0.0, 1.0]. Returns 0.0 for unbounded or zero-capacity types."""
        rt = _coerce_resource_type(resource_type)
        with self._lock:
            self._sweep_expired_locked()
            capacity = self._capacity_for(rt)
            if capacity is None or capacity <= 0:
                return 0.0
            return min(1.0, self._allocated_locked(rt) / capacity)

    def get_all_allocations(self) -> list[ResourceAllocation]:
        """Return all allocations (any status), oldest first."""
        with self._lock:
            return sorted(self._allocations.values(), key=lambda a: a.created_at)

    def get_owner_allocations(self, owner: str) -> list[ResourceAllocation]:
        """Return all allocations for ``owner``, oldest first."""
        own = _validate_owner(owner)
        with self._lock:
            return sorted(
                (a for a in self._allocations.values() if a.owner == own),
                key=lambda a: a.created_at,
            )

    def get_allocation(self, allocation_id: str) -> ResourceAllocation | None:
        """Return a single allocation by ID, or None."""
        with self._lock:
            return self._allocations.get(allocation_id)

    def get_stats(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of manager state."""
        with self._lock:
            self._sweep_expired_locked()
            utilization = {}
            for rt in ResourceType:
                capacity = self._capacity_for(rt)
                if capacity is None or capacity <= 0:
                    utilization[rt.value] = 0.0
                else:
                    utilization[rt.value] = min(1.0, self._allocated_locked(rt) / capacity)
            return {
                "total_allocations": len(self._allocations),
                "active_allocations": sum(
                    1 for a in self._allocations.values() if a.status is ResourceStatus.ALLOCATED
                ),
                "utilization": utilization,
            }

    # ------------------------------------------------------------------
    # Internal helpers (call with self._lock held)
    # ------------------------------------------------------------------

    def _capacity_for(self, resource_type: ResourceType) -> float | None:
        if resource_type in self._capacities:
            return self._capacities[resource_type]
        return self._default_capacity

    def _allocated_locked(self, resource_type: ResourceType) -> float:
        return sum(
            a.amount
            for a in self._allocations.values()
            if a.resource_type is resource_type and a.status is ResourceStatus.ALLOCATED
        )

    def _sweep_expired_locked(self) -> list[ResourceAllocation]:
        now = self._clock()
        expired: list[ResourceAllocation] = []
        for alloc in list(self._allocations.values()):
            if (
                alloc.status is ResourceStatus.ALLOCATED
                and alloc.expires_at is not None
                and now >= alloc.expires_at
            ):
                alloc.status = ResourceStatus.EXPIRED
                quota = self._quotas.get((alloc.resource_type, alloc.owner))
                if quota is not None:
                    quota.used = max(0.0, quota.used - alloc.amount)
                expired.append(alloc)
        return expired
