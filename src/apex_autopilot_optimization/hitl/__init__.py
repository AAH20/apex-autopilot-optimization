"""Human-in-the-loop (HITL) approval and override system.

This package provides the approval workflow for autopilot actions:
status enumeration, request lifecycle management, audit trails, and
human override tracking.
"""

from apex_autopilot_optimization.hitl.config import HITLConfig
from apex_autopilot_optimization.hitl.override import HumanOverride
from apex_autopilot_optimization.hitl.request import ApprovalRequest
from apex_autopilot_optimization.hitl.status import ApprovalStatus
from apex_autopilot_optimization.hitl.workflow import ApprovalWorkflow

__all__ = [
    "ApprovalRequest",
    "ApprovalStatus",
    "ApprovalWorkflow",
    "HITLConfig",
    "HumanOverride",
]
