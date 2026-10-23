"""Tests for the broker slot orchestrator SlotManager.

TDD: every behavior has a failing test before implementation.
Covers: squad distribution, allocation/deallocation, heartbeat/TTL,
draining, broker lookups, validation errors, and thread safety.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from apex_autopilot_optimization.broker_slot_orchestrator.slot_manager import (
    SlotManager,
)
from apex_autopilot_optimization.broker_slot_orchestrator.types import (
    BrokerAllocation,
    BrokerId,
    OrchestratorConfig,
    SlotId,
    SlotRecord,
    SlotRequirements,
    SlotState,
    SquadId,
    SquadStatus,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _fresh_heartbeat() -> datetime:
    return datetime.now(UTC)


def _old_heartbeat() -> datetime:
    return datetime.now(UTC) - timedelta(seconds=600)


# --------------------------------------------------------------------------- #
# Construction & squad distribution
# --------------------------------------------------------------------------- #


def test_default_config_has_330_slots_12_squads() -> None:
    cfg = OrchestratorConfig()
    assert cfg.total_slots == 330
    assert cfg.total_squads == 12
    counts = cfg.squad_slot_counts()
    assert len(counts) == 12
    assert sum(counts) == 330
    # 330 / 12 = 27 remainder 6 → squads 0-5 get 28, squads 6-11 get 27
    assert counts == (28,) * 6 + (27,) * 6


def test_custom_config_valid_distribution() -> None:
    cfg = OrchestratorConfig(total_slots=100, total_squads=4, slots_per_squad=(25, 25, 25, 25))
    counts = cfg.squad_slot_counts()
    assert counts == (25, 25, 25, 25)


def test_config_rejects_mismatched_squad_count() -> None:
    with pytest.raises(ValueError):
        OrchestratorConfig(total_slots=100, total_squads=4, slots_per_squad=(25, 25, 25))


def test_config_rejects_wrong_total() -> None:
    with pytest.raises(ValueError):
        OrchestratorConfig(
            total_slots=100, total_squads=4, slots_per_squad=(24, 25, 25, 25)
        )  # sums to 99 != 100


def test_slot_manager_initializes_all_slots_free() -> None:
    mgr = SlotManager(OrchestratorConfig(total_slots=10, total_squads=2, slots_per_squad=(5, 5)))
    for sid in range(10):
        rec = mgr._slots[SlotId(sid)]
        assert rec.state == SlotState.FREE
        assert rec.broker_id is None


def test_slot_manager_distributes_slots_across_squads() -> None:
    mgr = SlotManager(OrchestratorConfig(total_slots=10, total_squads=2, slots_per_squad=(5, 5)))
    assert mgr.get_available_slots(SquadId(0)) == 5
    assert mgr.get_available_slots(SquadId(1)) == 5


def test_slot_manager_rejects_invalid_squad() -> None:
    mgr = SlotManager()
    with pytest.raises(ValueError):
        mgr.get_available_slots(SquadId(99))


# --------------------------------------------------------------------------- #
# Allocation
# --------------------------------------------------------------------------- #


def test_allocate_returns_free_slot_and_marks_allocated() -> None:
    mgr = SlotManager()
    slot = mgr.allocate(SquadId(0), BrokerId("broker-alpha"))
    assert isinstance(slot, SlotId)
    assert 0 <= slot < 330
    rec = mgr._slots[slot]
    assert rec.state == SlotState.ALLOCATED
    assert rec.broker_id == BrokerId("broker-alpha")
    assert rec.squad_id == SquadId(0)
    assert rec.allocated_at is not None
    assert rec.last_heartbeat is not None


def test_allocate_respects_slot_requirements() -> None:
    mgr = SlotManager()
    req = SlotRequirements(min_slots=1, preferred_region="MENA")
    slot = mgr.allocate(SquadId(0), BrokerId("broker-beta"), req)
    rec = mgr._slots[slot]
    assert rec.requirements == req


def test_allocate_returns_none_when_squad_exhausted() -> None:
    # Squad with 1 slot
    mgr = SlotManager(OrchestratorConfig(total_slots=2, total_squads=2, slots_per_squad=(1, 1)))
    assert mgr.allocate(SquadId(0), BrokerId("b1")) is not None
    assert mgr.allocate(SquadId(0), BrokerId("b2")) is None
    # Squad 1 still has capacity
    assert mgr.allocate(SquadId(1), BrokerId("b3")) is not None


def test_allocate_same_broker_gets_multiple_slots() -> None:
    mgr = SlotManager()
    s1 = mgr.allocate(SquadId(0), BrokerId("broker-shared"))
    s2 = mgr.allocate(SquadId(0), BrokerId("broker-shared"))
    assert s1 != s2
    assert mgr._slots[s1].broker_id == BrokerId("broker-shared")
    assert mgr._slots[s2].broker_id == BrokerId("broker-shared")


def test_allocate_prefers_free_over_draining() -> None:
    mgr = SlotManager(OrchestratorConfig(total_slots=2, total_squads=1, slots_per_squad=(2,)))
    mgr.allocate(SquadId(0), BrokerId("b1"))
    mgr.allocate(SquadId(0), BrokerId("b2"))
    mgr.drain_slot(SlotId(0))
    # s1 is DRAINING, s2 is ALLOCATED — no FREE left, should return None
    assert mgr.allocate(SquadId(0), BrokerId("b3")) is None


# --------------------------------------------------------------------------- #
# Deallocation
# --------------------------------------------------------------------------- #


def test_deallocate_marks_slot_free_and_clears_broker() -> None:
    mgr = SlotManager()
    slot = mgr.allocate(SquadId(0), BrokerId("broker-x"))
    mgr.deallocate(slot)
    rec = mgr._slots[slot]
    assert rec.state == SlotState.FREE
    assert rec.broker_id is None
    assert rec.allocated_at is None
    assert rec.last_heartbeat is None


def test_deallocate_invalid_slot_raises() -> None:
    mgr = SlotManager()
    with pytest.raises(ValueError):
        mgr.deallocate(SlotId(999))


def test_deallocate_already_free_slot_raises() -> None:
    mgr = SlotManager()
    with pytest.raises(ValueError):
        mgr.deallocate(SlotId(0))  # slot 0 starts FREE


# --------------------------------------------------------------------------- #
# Heartbeat
# --------------------------------------------------------------------------- #


def test_heartbeat_keeps_slot_alive() -> None:
    mgr = SlotManager(OrchestratorConfig(heartbeat_ttl_seconds=60.0))
    slot = mgr.allocate(SquadId(0), BrokerId("b1"))
    assert slot is not None
    when = _fresh_heartbeat()
    mgr.heartbeat(slot, when)
    rec = mgr._slots[slot]
    assert rec.state == SlotState.ALLOCATED
    assert rec.last_heartbeat is not None
    assert abs((rec.last_heartbeat - when).total_seconds()) < 1.0


def test_heartbeat_on_free_slot_raises() -> None:
    mgr = SlotManager()
    with pytest.raises(ValueError):
        mgr.heartbeat(SlotId(0), _fresh_heartbeat())


def test_heartbeat_expires_draining_slot() -> None:
    mgr = SlotManager(OrchestratorConfig(heartbeat_ttl_seconds=60.0))
    slot = mgr.allocate(SquadId(0), BrokerId("b1"))
    mgr.drain_slot(slot)
    assert mgr._slots[slot].state == SlotState.DRAINING
    # Heartbeat older than TTL → mark FAILED
    mgr.heartbeat(slot, _old_heartbeat())
    assert mgr._slots[slot].state == SlotState.FAILED


def test_heartbeat_fresh_draining_slot_stays_draining() -> None:
    mgr = SlotManager(OrchestratorConfig(heartbeat_ttl_seconds=60.0))
    slot = mgr.allocate(SquadId(0), BrokerId("b1"))
    mgr.drain_slot(slot)
    mgr.heartbeat(slot, _fresh_heartbeat())
    assert mgr._slots[slot].state == SlotState.DRAINING


# --------------------------------------------------------------------------- #
# Draining
# --------------------------------------------------------------------------- #


def test_drain_slot_marks_draining() -> None:
    mgr = SlotManager()
    slot = mgr.allocate(SquadId(0), BrokerId("b1"))
    mgr.drain_slot(slot)
    assert mgr._slots[slot].state == SlotState.DRAINING


def test_drain_free_slot_raises() -> None:
    mgr = SlotManager()
    with pytest.raises(ValueError):
        mgr.drain_slot(SlotId(0))  # FREE


def test_drain_already_failed_slot_raises() -> None:
    mgr = SlotManager()
    slot = mgr.allocate(SquadId(0), BrokerId("b1"))
    mgr._slots[slot].mark_failed()
    with pytest.raises(ValueError):
        mgr.drain_slot(slot)


# --------------------------------------------------------------------------- #
# Squad status
# --------------------------------------------------------------------------- #


def test_get_squad_status_returns_counts() -> None:
    mgr = SlotManager()
    mgr.allocate(SquadId(0), BrokerId("b1"))
    mgr.allocate(SquadId(0), BrokerId("b2"))
    status = mgr.get_squad_status(SquadId(0))
    assert isinstance(status, SquadStatus)
    assert status.squad_id == SquadId(0)
    assert status.total == 28  # squad 0 gets 28 in default config
    assert status.allocated == 2
    assert status.free == status.total - 2
    assert status.utilization_pct == pytest.approx(2 / 28 * 100, abs=0.01)


def test_get_squad_status_utilization_zero_when_empty() -> None:
    mgr = SlotManager()
    status = mgr.get_squad_status(SquadId(0))
    assert status.utilization_pct == 0.0
    assert status.free == status.total


# --------------------------------------------------------------------------- #
# Broker allocation
# --------------------------------------------------------------------------- #


def test_get_broker_allocation_returns_slots() -> None:
    mgr = SlotManager()
    s1 = mgr.allocate(SquadId(0), BrokerId("broker-a"))
    s2 = mgr.allocate(SquadId(1), BrokerId("broker-a"))
    alloc = mgr.get_broker_allocation(BrokerId("broker-a"))
    assert isinstance(alloc, BrokerAllocation)
    assert alloc.broker_id == BrokerId("broker-a")
    assert set(alloc.slot_ids) == {s1, s2}


def test_get_broker_allocation_unknown_broker_returns_empty() -> None:
    mgr = SlotManager()
    alloc = mgr.get_broker_allocation(BrokerId("no-such-broker"))
    assert alloc.slot_ids == ()


def test_get_available_slots_counts_free() -> None:
    mgr = SlotManager()
    mgr.allocate(SquadId(0), BrokerId("b1"))
    mgr.allocate(SquadId(0), BrokerId("b2"))
    # squad 0 has 28 slots, 2 allocated → 26 free
    assert mgr.get_available_slots(SquadId(0)) == 26


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def test_invalid_squad_id_raises() -> None:
    mgr = SlotManager()
    with pytest.raises(ValueError):
        mgr.allocate(SquadId(99), BrokerId("b1"))


def test_empty_broker_id_raises() -> None:
    mgr = SlotManager()
    with pytest.raises(ValueError):
        mgr.allocate(SquadId(0), BrokerId(""))


def test_whitespace_broker_id_is_stripped() -> None:
    mgr = SlotManager()
    slot = mgr.allocate(SquadId(0), BrokerId("  broker-trim  "))
    assert mgr._slots[slot].broker_id == BrokerId("broker-trim")


# --------------------------------------------------------------------------- #
# Thread safety
# --------------------------------------------------------------------------- #


def test_concurrent_allocations_do_not_duplicate_slots() -> None:
    mgr = SlotManager()
    broker = BrokerId("concurrent-broker")
    allocated: list[SlotId] = []
    lock = threading.Lock()
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(5):
                slot = mgr.allocate(SquadId(0), broker)
                if slot is not None:
                    with lock:
                        allocated.append(slot)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors during concurrent allocation: {errors}"
    assert len(allocated) == len(set(allocated)), "duplicate slots allocated"
    # No two threads got the same slot
    for slot in allocated:
        assert mgr._slots[slot].broker_id == broker


def test_concurrent_allocations_respect_squad_capacity() -> None:
    mgr = SlotManager(OrchestratorConfig(total_slots=20, total_squads=2, slots_per_squad=(10, 10)))
    broker = BrokerId("cap-broker")
    allocated: list[SlotId] = []
    lock = threading.Lock()

    def worker(squad: SquadId) -> None:
        for _ in range(20):  # more than squad capacity
            slot = mgr.allocate(squad, broker)
            if slot is not None:
                with lock:
                    allocated.append(slot)

    threads = [
        threading.Thread(target=worker, args=(SquadId(0),)),
        threading.Thread(target=worker, args=(SquadId(1),)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Total allocated across both squads cannot exceed 20
    assert len(allocated) <= 20
    # Each squad's allocated count cannot exceed its capacity (10)
    squad0 = sum(1 for s in allocated if mgr._slots[s].squad_id == SquadId(0))
    squad1 = sum(1 for s in allocated if mgr._slots[s].squad_id == SquadId(1))
    assert squad0 <= 10
    assert squad1 <= 10


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_requirements_default_empty() -> None:
    mgr = SlotManager()
    slot = mgr.allocate(SquadId(0), BrokerId("b1"))
    rec = mgr._slots[slot]
    assert rec.requirements == SlotRequirements()


def test_slot_record_mark_allocated_sets_timestamps() -> None:
    rec = SlotRecord(slot_id=SlotId(0), squad_id=SquadId(0))
    when = datetime.now(UTC)
    rec.mark_allocated(BrokerId("b1"), SlotRequirements())
    assert rec.state == SlotState.ALLOCATED
    assert rec.broker_id == BrokerId("b1")
    assert rec.allocated_at is not None
    assert rec.last_heartbeat is not None
    assert rec.allocated_at <= when + timedelta(seconds=1)
    assert rec.last_heartbeat <= when + timedelta(seconds=1)


def test_slot_record_mark_free_clears_all() -> None:
    rec = SlotRecord(
        slot_id=SlotId(0),
        squad_id=SquadId(0),
        state=SlotState.ALLOCATED,
        broker_id=BrokerId("b1"),
        allocated_at=datetime.now(UTC),
        last_heartbeat=datetime.now(UTC),
        requirements=SlotRequirements(),
    )
    rec.mark_free()
    assert rec.state == SlotState.FREE
    assert rec.broker_id is None
    assert rec.allocated_at is None
    assert rec.last_heartbeat is None
    assert rec.requirements is None


def test_slot_record_failure_count_increments() -> None:
    rec = SlotRecord(slot_id=SlotId(0), squad_id=SquadId(0))
    assert rec.failure_count == 0
    rec.mark_failed()
    assert rec.failure_count == 1
    rec.mark_failed()
    assert rec.failure_count == 2
