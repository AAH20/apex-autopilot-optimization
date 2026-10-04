"""Approval status enumeration for the HITL system."""

from __future__ import annotations

from enum import Enum


class ApprovalStatus(Enum):
    """Lifecycle states of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ESCALATED = "escalated"
