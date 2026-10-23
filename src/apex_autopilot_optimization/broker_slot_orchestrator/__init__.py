"""Broker channel agent slot orchestrator.

Manages 330 agent slots across 12 squads for broker channel distribution
(MENA + emerging markets via broker OS + Facebook/WhatsApp).
"""

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

__all__ = [
    "SlotManager",
    "BrokerAllocation",
    "BrokerId",
    "OrchestratorConfig",
    "SlotId",
    "SlotRecord",
    "SlotRequirements",
    "SlotState",
    "SquadId",
    "SquadStatus",
]
