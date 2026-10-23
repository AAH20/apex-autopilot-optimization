"""Broker channel agent slot orchestrator.

Manages 330 agent slots across 12 squads for broker channel distribution
(MENA + emerging markets via broker OS + Facebook/WhatsApp).

Each vehicle slot owns a lifecycle: FREE -> ALLOCATED -> BUSY -> FAILED/DRAINING.
Thread-safe via threading.RLock.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

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


class SlotManager:
    """Allocates and tracks agent slots across squads for broker channel.

    Every slot belongs to exactly one squad. Squads partition the total
    slot pool evenly (330 slots / 12 squads = 27-28 per squad by default).
    """

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        self.config = config or OrchestratorConfig()
        self._slots: dict[SlotId, SlotRecord] = {}
        self._broker_slots: dict[BrokerId, set[SlotId]] = {}
        self._lock = threading.RLock()
        self._build_slots()

    def _build_slots(self) -> None:
        slot_id = 0
        for squad_idx, squad_count in enumerate(self.config.squad_slot_counts()):
            squad_id = SquadId(squad_idx)
            for _ in range(squad_count):
                self._slots[SlotId(slot_id)] = SlotRecord(
                    slot_id=SlotId(slot_id), squad_id=squad_id
                )
                slot_id += 1

    def _squad_range(self, squad_id: SquadId) -> tuple[int, int]:
        """Return (start, end) slot indices for a squad."""
        counts = self.config.squad_slot_counts()
        start = sum(counts[:squad_id])
        end = start + counts[squad_id]
        return start, end

    def _validate_squad(self, squad_id: SquadId) -> None:
        if not 0 <= squad_id < self.config.total_squads:
            raise ValueError(f"SquadId {squad_id} out of range [0, {self.config.total_squads})")

    def _validate_slot(self, slot_id: SlotId) -> None:
        if slot_id not in self._slots:
            raise ValueError(f"SlotId {slot_id} does not exist")

    def allocate(
        self,
        squad_id: SquadId,
        broker_id: BrokerId,
        requirements: SlotRequirements | None = None,
    ) -> SlotId | None:
        """Allocate a FREE slot in ``squad_id`` to ``broker_id``.

        Returns the allocated SlotId, or None if the squad is exhausted.
        Thread-safe: holds self._lock for the entire check-and-allocate.
        """
        requirements = requirements or SlotRequirements()
        with self._lock:
            self._validate_squad(squad_id)
            start, end = self._squad_range(squad_id)
            for slot_idx in range(start, end):
                slot_id = SlotId(slot_idx)
                rec = self._slots[slot_id]
                if rec.state == SlotState.FREE:
                    rec.mark_allocated(broker_id, requirements)
                    self._broker_slots.setdefault(broker_id, set()).add(slot_id)
                    return slot_id
            return None

    def deallocate(self, slot_id: SlotId) -> None:
        """Release a slot back to FREE state.

        Raises ValueError if the slot does not exist or is already FREE.
        """
        with self._lock:
            self._validate_slot(slot_id)
            rec = self._slots[slot_id]
            if rec.state == SlotState.FREE:
                raise ValueError(f"Slot {slot_id} is already FREE")
            broker_id = rec.broker_id
            rec.mark_free()
            if broker_id is not None:
                self._broker_slots.get(broker_id, set()).discard(slot_id)

    def heartbeat(self, slot_id: SlotId, when: datetime) -> None:
        """Record a heartbeat for ``slot_id``.

        If the slot is DRAINING and the heartbeat is older than the TTL,
        the slot is marked FAILED. Raises ValueError if the slot is FREE
        or does not exist.
        """
        with self._lock:
            self._validate_slot(slot_id)
            rec = self._slots[slot_id]
            if rec.state == SlotState.FREE:
                raise ValueError(f"Cannot heartbeat FREE slot {slot_id}")
            rec.heartbeat(when)
            if rec.state == SlotState.DRAINING and rec.last_heartbeat is not None:
                age = (datetime.now(UTC) - rec.last_heartbeat).total_seconds()
                if age > self.config.heartbeat_ttl_seconds:
                    rec.mark_failed()

    def drain_slot(self, slot_id: SlotId) -> None:
        """Mark a slot DRAINING (stop new assignments, finish in-flight).

        Raises ValueError if the slot is FREE, FAILED, or does not exist.
        """
        with self._lock:
            self._validate_slot(slot_id)
            rec = self._slots[slot_id]
            if rec.state in (SlotState.FREE, SlotState.FAILED):
                raise ValueError(f"Cannot drain slot {slot_id} in state {rec.state.value}")
            rec.mark_draining()

    def get_available_slots(self, squad_id: SquadId) -> int:
        """Count FREE slots in ``squad_id``."""
        with self._lock:
            self._validate_squad(squad_id)
            start, end = self._squad_range(squad_id)
            return sum(
                1
                for slot_idx in range(start, end)
                if self._slots[SlotId(slot_idx)].state == SlotState.FREE
            )

    def get_squad_status(self, squad_id: SquadId) -> SquadStatus:
        """Aggregate status for ``squad_id``."""
        with self._lock:
            self._validate_squad(squad_id)
            start, end = self._squad_range(squad_id)
            total = end - start
            free = allocated = busy = failed = draining = 0
            for slot_idx in range(start, end):
                state = self._slots[SlotId(slot_idx)].state
                if state == SlotState.FREE:
                    free += 1
                elif state == SlotState.ALLOCATED:
                    allocated += 1
                elif state == SlotState.BUSY:
                    busy += 1
                elif state == SlotState.FAILED:
                    failed += 1
                elif state == SlotState.DRAINING:
                    draining += 1
            utilization = (allocated + busy + failed + draining) / total * 100 if total else 0.0
            return SquadStatus(
                squad_id=squad_id,
                total=total,
                free=free,
                allocated=allocated,
                busy=busy,
                failed=failed,
                draining=draining,
                utilization_pct=utilization,
            )

    def get_broker_allocation(self, broker_id: BrokerId) -> BrokerAllocation:
        """Return all slots assigned to ``broker_id``."""
        with self._lock:
            slot_ids = sorted(self._broker_slots.get(broker_id, set()))
            squad_ids: set[SquadId] = set()
            for slot_id in slot_ids:
                squad_ids.add(self._slots[slot_id].squad_id)
            return BrokerAllocation(
                broker_id=broker_id,
                slot_ids=tuple(slot_ids),
                squad_ids=tuple(sorted(squad_ids)),
            )
