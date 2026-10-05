"""Tests for the resource package: ResourceType, ResourceStatus,
ResourceAllocation, ResourceQuota, and ResourceManager."""

from __future__ import annotations

import math
import threading

import pytest

from apex_autopilot_optimization.resource import (
    QuotaExceededError,
    ResourceAllocation,
    ResourceError,
    ResourceManager,
    ResourceQuota,
    ResourceStatus,
    ResourceType,
)

# ---------------------------------------------------------------------------
# ResourceType / ResourceStatus
# ---------------------------------------------------------------------------


class TestEnums:
    def test_resource_type_values(self):
        assert ResourceType.CPU.value == "cpu"
        assert ResourceType.MEMORY.value == "memory"
        assert ResourceType.GPU.value == "gpu"
        assert ResourceType.NETWORK.value == "network"
        assert ResourceType.STORAGE.value == "storage"
        assert len(ResourceType) == 5

    def test_resource_status_values(self):
        assert ResourceStatus.ALLOCATED.value == "allocated"
        assert ResourceStatus.RESERVED.value == "reserved"
        assert ResourceStatus.RELEASED.value == "released"
        assert ResourceStatus.EXPIRED.value == "expired"
        assert len(ResourceStatus) == 4


# ---------------------------------------------------------------------------
# ResourceAllocation
# ---------------------------------------------------------------------------


class TestResourceAllocation:
    def test_valid_construction(self):
        alloc = ResourceAllocation(
            id="a1",
            resource_type=ResourceType.CPU,
            amount=2.5,
            owner="worker-1",
            status=ResourceStatus.ALLOCATED,
            created_at=100.0,
        )
        assert alloc.id == "a1"
        assert alloc.resource_type is ResourceType.CPU
        assert alloc.amount == 2.5
        assert alloc.owner == "worker-1"
        assert alloc.status is ResourceStatus.ALLOCATED
        assert alloc.created_at == 100.0
        assert alloc.expires_at is None

    def test_expires_at_before_created_at_raises(self):
        with pytest.raises(ValueError, match="expires_at"):
            ResourceAllocation(
                id="a1",
                resource_type=ResourceType.CPU,
                amount=1.0,
                owner="w",
                status=ResourceStatus.ALLOCATED,
                created_at=100.0,
                expires_at=50.0,
            )

    def test_empty_id_raises(self):
        with pytest.raises(ValueError, match="id"):
            ResourceAllocation(
                id="",
                resource_type=ResourceType.CPU,
                amount=1.0,
                owner="w",
                status=ResourceStatus.ALLOCATED,
                created_at=0.0,
            )

    def test_empty_owner_raises(self):
        with pytest.raises(ValueError, match="owner"):
            ResourceAllocation(
                id="a1",
                resource_type=ResourceType.CPU,
                amount=1.0,
                owner="",
                status=ResourceStatus.ALLOCATED,
                created_at=0.0,
            )

    def test_non_positive_amount_raises(self):
        with pytest.raises(ValueError, match="amount"):
            ResourceAllocation(
                id="a1",
                resource_type=ResourceType.CPU,
                amount=0.0,
                owner="w",
                status=ResourceStatus.ALLOCATED,
                created_at=0.0,
            )

    def test_non_finite_amount_raises(self):
        with pytest.raises(ValueError, match="finite"):
            ResourceAllocation(
                id="a1",
                resource_type=ResourceType.CPU,
                amount=math.inf,
                owner="w",
                status=ResourceStatus.ALLOCATED,
                created_at=0.0,
            )

    def test_wrong_resource_type_raises(self):
        with pytest.raises(TypeError, match="resource_type"):
            ResourceAllocation(
                id="a1",
                resource_type="cpu",  # type: ignore[arg-type]
                amount=1.0,
                owner="w",
                status=ResourceStatus.ALLOCATED,
                created_at=0.0,
            )

    def test_is_expired(self):
        alloc = ResourceAllocation(
            id="a1",
            resource_type=ResourceType.CPU,
            amount=1.0,
            owner="w",
            status=ResourceStatus.ALLOCATED,
            created_at=0.0,
            expires_at=100.0,
        )
        assert not alloc.is_expired(now=50.0)
        assert alloc.is_expired(now=100.0)
        assert alloc.is_expired(now=150.0)

    def test_is_expired_none_expires_at(self):
        alloc = ResourceAllocation(
            id="a1",
            resource_type=ResourceType.CPU,
            amount=1.0,
            owner="w",
            status=ResourceStatus.ALLOCATED,
            created_at=0.0,
        )
        assert not alloc.is_expired(now=1e12)

    def test_is_active(self):
        alloc = ResourceAllocation(
            id="a1",
            resource_type=ResourceType.CPU,
            amount=1.0,
            owner="w",
            status=ResourceStatus.ALLOCATED,
            created_at=0.0,
        )
        assert alloc.is_active
        alloc.status = ResourceStatus.RELEASED
        assert not alloc.is_active


# ---------------------------------------------------------------------------
# ResourceQuota
# ---------------------------------------------------------------------------


class TestResourceQuota:
    def test_valid_construction(self):
        quota = ResourceQuota(resource_type=ResourceType.MEMORY, owner="w1", limit=1024.0)
        assert quota.resource_type is ResourceType.MEMORY
        assert quota.owner == "w1"
        assert quota.limit == 1024.0
        assert quota.used == 0.0
        assert quota.reserved == 0.0

    def test_check_quota_within_limit(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=10.0, used=4.0)
        assert quota.check_quota(ResourceType.CPU, "w1", 6.0)
        assert not quota.check_quota(ResourceType.CPU, "w1", 6.1)

    def test_check_quota_accounts_for_reserved(self):
        quota = ResourceQuota(
            resource_type=ResourceType.CPU,
            owner="w1",
            limit=10.0,
            used=4.0,
            reserved=3.0,
        )
        assert quota.check_quota(ResourceType.CPU, "w1", 3.0)
        assert not quota.check_quota(ResourceType.CPU, "w1", 3.1)

    def test_check_quota_type_mismatch_raises(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=10.0)
        with pytest.raises(ValueError, match="resource type mismatch"):
            quota.check_quota(ResourceType.GPU, "w1", 1.0)

    def test_check_quota_owner_mismatch_raises(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=10.0)
        with pytest.raises(ValueError, match="owner mismatch"):
            quota.check_quota(ResourceType.CPU, "w2", 1.0)

    def test_reserve_success(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=10.0)
        assert quota.reserve(ResourceType.CPU, "w1", 4.0)
        assert quota.reserved == 4.0

    def test_reserve_exceeding_limit_fails(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=10.0)
        assert not quota.reserve(ResourceType.CPU, "w1", 11.0)
        assert quota.reserved == 0.0

    def test_release_reservation(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=10.0, reserved=5.0)
        remaining = quota.release_reservation(ResourceType.CPU, "w1", 2.0)
        assert remaining == 3.0
        assert quota.reserved == 3.0

    def test_release_reservation_too_much_raises(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=10.0, reserved=2.0)
        with pytest.raises(ValueError, match="cannot release"):
            quota.release_reservation(ResourceType.CPU, "w1", 3.0)

    def test_get_quota_status(self):
        quota = ResourceQuota(
            resource_type=ResourceType.CPU,
            owner="w1",
            limit=10.0,
            used=3.0,
            reserved=2.0,
        )
        status = quota.get_quota_status(ResourceType.CPU, "w1")
        assert status["resource_type"] == "cpu"
        assert status["owner"] == "w1"
        assert status["limit"] == 10.0
        assert status["used"] == 3.0
        assert status["reserved"] == 2.0
        assert status["available"] == 5.0
        assert status["utilization"] == pytest.approx(0.3)

    def test_get_quota_status_zero_limit(self):
        quota = ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=0.0)
        status = quota.get_quota_status(ResourceType.CPU, "w1")
        assert status["available"] == 0.0
        assert status["utilization"] == 0.0

    def test_negative_limit_raises(self):
        with pytest.raises(ValueError, match="limit"):
            ResourceQuota(resource_type=ResourceType.CPU, owner="w1", limit=-1.0)


# ---------------------------------------------------------------------------
# ResourceManager
# ---------------------------------------------------------------------------


class TestResourceManager:
    def test_allocate_and_get_allocated(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        alloc = mgr.allocate(ResourceType.CPU, 4.0, "worker-1")
        assert alloc.resource_type is ResourceType.CPU
        assert alloc.amount == 4.0
        assert alloc.owner == "worker-1"
        assert alloc.status is ResourceStatus.ALLOCATED
        assert mgr.get_allocated(ResourceType.CPU) == 4.0

    def test_allocate_with_string_type(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        alloc = mgr.allocate("cpu", 2.0, "w1")
        assert alloc.resource_type is ResourceType.CPU

    def test_allocate_invalid_amount_raises(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        with pytest.raises(ValueError, match="amount"):
            mgr.allocate(ResourceType.CPU, 0.0, "w1")
        with pytest.raises(ValueError, match="amount"):
            mgr.allocate(ResourceType.CPU, -1.0, "w1")

    def test_allocate_invalid_owner_raises(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        with pytest.raises(ValueError, match="owner"):
            mgr.allocate(ResourceType.CPU, 1.0, "")

    def test_allocate_unknown_type_raises(self):
        mgr = ResourceManager()
        with pytest.raises(ValueError, match="unknown resource type"):
            mgr.allocate("quantum", 1.0, "w1")

    def test_allocate_invalid_ttl_raises(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        with pytest.raises(ValueError, match="ttl"):
            mgr.allocate(ResourceType.CPU, 1.0, "w1", ttl=0.0)
        with pytest.raises(ValueError, match="ttl"):
            mgr.allocate(ResourceType.CPU, 1.0, "w1", ttl=-5.0)

    def test_get_available(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        assert mgr.get_available(ResourceType.CPU) == 10.0
        mgr.allocate(ResourceType.CPU, 4.0, "w1")
        assert mgr.get_available(ResourceType.CPU) == 6.0

    def test_get_available_unbounded(self):
        mgr = ResourceManager()
        assert mgr.get_available(ResourceType.CPU) == math.inf

    def test_get_utilization(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        assert mgr.get_utilization(ResourceType.CPU) == 0.0
        mgr.allocate(ResourceType.CPU, 5.0, "w1")
        assert mgr.get_utilization(ResourceType.CPU) == pytest.approx(0.5)

    def test_get_utilization_unbounded(self):
        mgr = ResourceManager()
        assert mgr.get_utilization(ResourceType.CPU) == 0.0

    def test_deallocate_full(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        mgr.allocate(ResourceType.CPU, 4.0, "w1")
        assert mgr.deallocate(ResourceType.CPU, 4.0, "w1")
        assert mgr.get_allocated(ResourceType.CPU) == 0.0

    def test_deallocate_partial(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        mgr.allocate(ResourceType.CPU, 4.0, "w1")
        assert mgr.deallocate(ResourceType.CPU, 1.5, "w1")
        assert mgr.get_allocated(ResourceType.CPU) == pytest.approx(2.5)

    def test_deallocate_more_than_allocated_returns_false(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        mgr.allocate(ResourceType.CPU, 2.0, "w1")
        assert not mgr.deallocate(ResourceType.CPU, 3.0, "w1")
        assert mgr.get_allocated(ResourceType.CPU) == 2.0

    def test_deallocate_wrong_owner_returns_false(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        mgr.allocate(ResourceType.CPU, 2.0, "w1")
        assert not mgr.deallocate(ResourceType.CPU, 1.0, "w2")

    def test_get_all_allocations(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        a1 = mgr.allocate(ResourceType.CPU, 1.0, "w1")
        a2 = mgr.allocate(ResourceType.CPU, 2.0, "w2")
        allocs = mgr.get_all_allocations()
        assert len(allocs) == 2
        assert {a.id for a in allocs} == {a1.id, a2.id}

    def test_get_owner_allocations(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        a1 = mgr.allocate(ResourceType.CPU, 1.0, "w1")
        mgr.allocate(ResourceType.CPU, 2.0, "w2")
        a3 = mgr.allocate(ResourceType.CPU, 3.0, "w1")
        allocs = mgr.get_owner_allocations("w1")
        assert len(allocs) == 2
        assert {a.id for a in allocs} == {a1.id, a3.id}

    def test_get_allocation_by_id(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        alloc = mgr.allocate(ResourceType.CPU, 1.0, "w1")
        assert mgr.get_allocation(alloc.id) is alloc
        assert mgr.get_allocation("nonexistent") is None

    def test_quota_enforced_on_allocate(self):
        mgr = ResourceManager(
            capacities={ResourceType.CPU: 100.0},
            quotas={(ResourceType.CPU, "w1"): 10.0},
        )
        mgr.allocate(ResourceType.CPU, 8.0, "w1")
        with pytest.raises(QuotaExceededError):
            mgr.allocate(ResourceType.CPU, 3.0, "w1")

    def test_quota_not_enforced_for_other_owner(self):
        mgr = ResourceManager(
            capacities={ResourceType.CPU: 100.0},
            quotas={(ResourceType.CPU, "w1"): 10.0},
        )
        alloc = mgr.allocate(ResourceType.CPU, 50.0, "w2")
        assert alloc.amount == 50.0

    def test_set_quota_and_get_quota_status(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 100.0})
        mgr.set_quota(ResourceType.CPU, "w1", 20.0)
        status = mgr.get_quota_status(ResourceType.CPU, "w1")
        assert status is not None
        assert status["limit"] == 20.0
        assert status["used"] == 0.0
        mgr.allocate(ResourceType.CPU, 5.0, "w1")
        status = mgr.get_quota_status(ResourceType.CPU, "w1")
        assert status is not None
        assert status["used"] == 5.0
        assert status["available"] == 15.0

    def test_get_quota_status_no_quota(self):
        mgr = ResourceManager()
        assert mgr.get_quota_status(ResourceType.CPU, "w1") is None

    def test_set_quota_invalid_limit_raises(self):
        mgr = ResourceManager()
        with pytest.raises(ValueError, match="limit"):
            mgr.set_quota(ResourceType.CPU, "w1", -1.0)

    def test_ttl_expiry_frees_resources(self):
        clock = [1000.0]
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0}, clock=lambda: clock[0])
        mgr.allocate(ResourceType.CPU, 6.0, "w1", ttl=10.0)
        assert mgr.get_allocated(ResourceType.CPU) == 6.0
        clock[0] = 1011.0
        expired = mgr.sweep_expired()
        assert len(expired) == 1
        assert expired[0].status is ResourceStatus.EXPIRED
        assert mgr.get_allocated(ResourceType.CPU) == 0.0
        assert mgr.get_available(ResourceType.CPU) == 10.0

    def test_ttl_expiry_frees_quota(self):
        clock = [1000.0]
        mgr = ResourceManager(
            capacities={ResourceType.CPU: 100.0},
            quotas={(ResourceType.CPU, "w1"): 10.0},
            clock=lambda: clock[0],
        )
        mgr.allocate(ResourceType.CPU, 8.0, "w1", ttl=10.0)
        with pytest.raises(QuotaExceededError):
            mgr.allocate(ResourceType.CPU, 3.0, "w1")
        clock[0] = 1011.0
        mgr.sweep_expired()
        # Quota should now be free
        alloc = mgr.allocate(ResourceType.CPU, 3.0, "w1")
        assert alloc.amount == 3.0

    def test_get_stats(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 10.0})
        mgr.allocate(ResourceType.CPU, 5.0, "w1")
        stats = mgr.get_stats()
        assert stats["total_allocations"] == 1
        assert stats["active_allocations"] == 1
        assert stats["utilization"]["cpu"] == pytest.approx(0.5)

    def test_thread_safety(self):
        mgr = ResourceManager(capacities={ResourceType.CPU: 1000.0})
        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for _ in range(50):
                    mgr.allocate(ResourceType.CPU, 1.0, f"w{n}")
                    mgr.deallocate(ResourceType.CPU, 1.0, f"w{n}")
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert mgr.get_allocated(ResourceType.CPU) == 0.0

    def test_multiple_resource_types_independent(self):
        mgr = ResourceManager(
            capacities={
                ResourceType.CPU: 10.0,
                ResourceType.MEMORY: 100.0,
                ResourceType.GPU: 2.0,
            }
        )
        mgr.allocate(ResourceType.CPU, 4.0, "w1")
        mgr.allocate(ResourceType.MEMORY, 50.0, "w1")
        mgr.allocate(ResourceType.GPU, 1.0, "w1")
        assert mgr.get_allocated(ResourceType.CPU) == 4.0
        assert mgr.get_allocated(ResourceType.MEMORY) == 50.0
        assert mgr.get_allocated(ResourceType.GPU) == 1.0
        assert mgr.get_available(ResourceType.CPU) == 6.0
        assert mgr.get_available(ResourceType.MEMORY) == 50.0
        assert mgr.get_available(ResourceType.GPU) == 1.0

    def test_default_capacity(self):
        mgr = ResourceManager(default_capacity=50.0)
        assert mgr.get_available(ResourceType.CPU) == 50.0
        assert mgr.get_available(ResourceType.GPU) == 50.0
        mgr.allocate(ResourceType.CPU, 10.0, "w1")
        assert mgr.get_available(ResourceType.CPU) == 40.0

    def test_resource_error_hierarchy(self):
        assert issubclass(QuotaExceededError, ResourceError)

    def test_get_reserved(self):
        mgr = ResourceManager(
            capacities={ResourceType.CPU: 100.0},
            quotas={(ResourceType.CPU, "w1"): 50.0},
        )
        quota = mgr.get_quota(ResourceType.CPU, "w1")
        assert quota is not None
        quota.reserve(ResourceType.CPU, "w1", 10.0)
        assert mgr.get_reserved(ResourceType.CPU) == 10.0
