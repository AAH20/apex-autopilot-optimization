"""Core types for the broker slot orchestrator.

Defines slot states, squad/slot/broker identifiers, and the data model
for tracking 330 agent slots across 12 squads in the broker channel GTM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class SlotState(StrEnum):
    """Lifecycle state of a single agent slot."""

    FREE = "FREE"
    ALLOCATED = "ALLOCATED"
    BUSY = "BUSY"
    FAILED = "FAILED"
    DRAINING = "DRAINING"


class SquadId(int):
    """Squad identifier: integer in [0, 11]."""

    def __new__(cls, value: int) -> SquadId:
        if not isinstance(value, int) or not 0 <= value <= 11:
            raise ValueError(f"SquadId must be an integer in [0, 11], got {value!r}")
        return super().__new__(cls, value)


class SlotId(int):
    """Slot identifier: integer in [0, 329]."""

    def __new__(cls, value: int) -> SlotId:
        if not isinstance(value, int) or not 0 <= value <= 329:
            raise ValueError(f"SlotId must be an integer in [0, 329], got {value!r}")
        return super().__new__(cls, value)


class BrokerId(str):
    """Broker identifier: non-empty string."""

    def __new__(cls, value: str) -> BrokerId:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"BrokerId must be a non-empty string, got {value!r}")
        return super().__new__(cls, value.strip())


@dataclass(frozen=True, slots=True)
class SlotRequirements:
    """Requirements a broker places on an allocated slot."""

    min_slots: int = 1
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    max_latency_ms: float | None = None
    preferred_region: str | None = None


@dataclass(slots=True)
class SlotRecord:
    """Mutable record tracking one slot's allocation state."""

    slot_id: SlotId
    squad_id: SquadId
    state: SlotState = SlotState.FREE
    broker_id: BrokerId | None = None
    allocated_at: datetime | None = None
    last_heartbeat: datetime | None = None
    requirements: SlotRequirements | None = None
    failure_count: int = 0

    def mark_allocated(self, broker_id: BrokerId, requirements: SlotRequirements) -> None:
        self.state = SlotState.ALLOCATED
        self.broker_id = broker_id
        self.allocated_at = datetime.now(UTC)
        self.last_heartbeat = self.allocated_at
        self.requirements = requirements

    def mark_busy(self) -> None:
        if self.state != SlotState.FAILED:
            self.state = SlotState.BUSY

    def mark_free(self) -> None:
        self.state = SlotState.FREE
        self.broker_id = None
        self.allocated_at = None
        self.last_heartbeat = None
        self.requirements = None
        self.failure_count = 0

    def mark_failed(self) -> None:
        self.state = SlotState.FAILED
        self.failure_count += 1

    def mark_draining(self) -> None:
        self.state = SlotState.DRAINING

    def heartbeat(self, when: datetime) -> None:
        self.last_heartbeat = when


@dataclass(frozen=True, slots=True)
class SquadStatus:
    """Aggregated status for a single squad."""

    squad_id: SquadId
    total: int
    free: int
    allocated: int
    busy: int
    failed: int
    draining: int
    utilization_pct: float

    @property
    def available(self) -> int:
        """Slots available for new allocation (FREE)."""
        return self.free


@dataclass(frozen=True, slots=True)
class OrchestratorConfig:
    """Configuration for SlotManager."""

    total_slots: int = 330
    total_squads: int = 12
    heartbeat_ttl_seconds: float = 300.0
    slots_per_squad: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.total_slots <= 0:
            raise ValueError("total_slots must be positive")
        if self.total_squads <= 0:
            raise ValueError("total_squads must be positive")
        if self.slots_per_squad is not None:
            if len(self.slots_per_squad) != self.total_squads:
                raise ValueError("slots_per_squad length must equal total_squads")
            if sum(self.slots_per_squad) != self.total_slots:
                raise ValueError("slots_per_squad sum must equal total_slots")
            if any(s <= 0 for s in self.slots_per_squad):
                raise ValueError("each squad must have at least one slot")

    @property
    def default_slots_per_squad(self) -> tuple[int, ...]:
        """Evenly distribute total_slots across total_squads."""
        base = self.total_slots // self.total_squads
        remainder = self.total_slots % self.total_squads
        return tuple(base + (1 if i < remainder else 0) for i in range(self.total_squads))

    def squad_slot_counts(self) -> tuple[int, ...]:
        return (
            self.slots_per_squad
            if self.slots_per_squad is not None
            else self.default_slots_per_squad
        )


@dataclass(frozen=True, slots=True)
class BrokerAllocation:
    """All slots assigned to a single broker."""

    broker_id: BrokerId
    slot_ids: tuple[SlotId, ...]
    squad_ids: tuple[SquadId, ...]
