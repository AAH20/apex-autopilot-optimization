"""Configuration for the human-in-the-loop approval system."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HITLConfig:
    """Settings controlling HITL approval workflow behavior.

    Attributes:
        enabled: Master switch. When False, requests are auto-approved.
        auto_approve_low_risk: Whether low-risk actions skip approval.
        require_dual_approval: Whether two approvers are required.
        approval_timeout_seconds: Time before a pending request expires.
        max_pending_approvals: Maximum number of simultaneously pending
            requests.
    """

    enabled: bool = True
    auto_approve_low_risk: bool = False
    require_dual_approval: bool = False
    approval_timeout_seconds: float = 60.0
    max_pending_approvals: int = 10
