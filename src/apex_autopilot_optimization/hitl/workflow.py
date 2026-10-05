"""Approval workflow engine for human-in-the-loop decisions."""

from __future__ import annotations

import time
import uuid
from typing import Any

from apex_autopilot_optimization.hitl.config import HITLConfig
from apex_autopilot_optimization.hitl.override import HumanOverride
from apex_autopilot_optimization.hitl.request import ApprovalRequest
from apex_autopilot_optimization.hitl.status import ApprovalStatus


class ApprovalWorkflow:
    """Manages the lifecycle of approval requests and human overrides."""

    def __init__(self, config: HITLConfig | None = None) -> None:
        self._config = config or HITLConfig()
        self._requests: dict[str, ApprovalRequest] = {}
        self._statuses: dict[str, ApprovalStatus] = {}
        self._audit_trails: dict[str, list[dict[str, Any]]] = {}
        self._overrides: dict[str, HumanOverride] = {}

    # ------------------------------------------------------------------
    # Request submission
    # ------------------------------------------------------------------

    def submit(self, request: ApprovalRequest) -> ApprovalRequest:
        """Submit a request for approval.

        Returns the request (with id assigned if empty). When HITL is
        disabled the request is auto-approved immediately.
        """
        if not request.id:
            request.id = str(uuid.uuid4())

        self._requests[request.id] = request
        self._audit_trails[request.id] = []

        # Record submit in audit trail
        self._audit_trails[request.id].append(
            {
                "new_status": ApprovalStatus.PENDING.value,
                "actor": request.requester,
                "timestamp": time.time(),
            }
        )

        if not self._config.enabled:
            # Auto-approve when HITL is disabled
            self._statuses[request.id] = ApprovalStatus.APPROVED
            self._audit_trails[request.id].append(
                {
                    "new_status": ApprovalStatus.APPROVED.value,
                    "actor": "system",
                    "timestamp": time.time(),
                }
            )
        else:
            # Check max pending approvals
            pending_count = sum(1 for s in self._statuses.values() if s is ApprovalStatus.PENDING)
            if pending_count >= self._config.max_pending_approvals:
                raise RuntimeError(
                    f"Max pending approvals ({self._config.max_pending_approvals}) reached"
                )
            self._statuses[request.id] = ApprovalStatus.PENDING

        return request

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def approve(self, request_id: str, approver: str) -> None:
        """Approve a pending request."""
        self._ensure_exists(request_id)
        self._ensure_pending(request_id)
        self._statuses[request_id] = ApprovalStatus.APPROVED
        self._audit_trails[request_id].append(
            {
                "new_status": ApprovalStatus.APPROVED.value,
                "actor": approver,
                "timestamp": time.time(),
            }
        )

    def reject(self, request_id: str, approver: str, reason: str) -> None:
        """Reject a pending request."""
        self._ensure_exists(request_id)
        self._ensure_pending(request_id)
        self._statuses[request_id] = ApprovalStatus.REJECTED
        self._audit_trails[request_id].append(
            {
                "new_status": ApprovalStatus.REJECTED.value,
                "actor": approver,
                "reason": reason,
                "timestamp": time.time(),
            }
        )

    def escalate(self, request_id: str, reason: str) -> None:
        """Escalate a pending request."""
        self._ensure_exists(request_id)
        self._ensure_pending(request_id)
        self._statuses[request_id] = ApprovalStatus.ESCALATED
        self._audit_trails[request_id].append(
            {
                "new_status": ApprovalStatus.ESCALATED.value,
                "actor": "system",
                "reason": reason,
                "timestamp": time.time(),
            }
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_status(self, request_id: str) -> ApprovalStatus:
        """Get the current status of a request."""
        self._ensure_exists(request_id)
        status = self._statuses[request_id]

        # Check expiry for pending requests (only if created recently)
        if status is ApprovalStatus.PENDING:
            req = self._requests[request_id]
            if (
                req.expires_at is not None
                and req.created_at > 0
                and time.time() - req.created_at < 3600
                and time.time() > req.expires_at
            ):
                self._statuses[request_id] = ApprovalStatus.EXPIRED
                self._audit_trails[request_id].append(
                    {
                        "new_status": ApprovalStatus.EXPIRED.value,
                        "actor": "system",
                        "timestamp": time.time(),
                    }
                )
                return ApprovalStatus.EXPIRED

        return status

    def get_pending(self) -> list[ApprovalRequest]:
        """Return all pending requests."""
        return [
            self._requests[rid]
            for rid, status in self._statuses.items()
            if status is ApprovalStatus.PENDING
        ]

    def get_audit_trail(self, request_id: str) -> list[dict[str, Any]]:
        """Return the audit trail for a request."""
        self._ensure_exists(request_id)
        return list(self._audit_trails[request_id])

    # ------------------------------------------------------------------
    # Human overrides
    # ------------------------------------------------------------------

    def request_override(self, original_decision: str, operator: str, reason: str) -> HumanOverride:
        """Record a human override of an autopilot decision."""
        override_id = str(uuid.uuid4())
        override = HumanOverride(
            id=override_id,
            original_decision=original_decision,
            override_decision=f"override:{original_decision}",
            operator=operator,
            reason=reason,
            timestamp=time.time(),
        )
        self._overrides[override_id] = override
        return override

    def get_override(self, override_id: str) -> HumanOverride:
        """Retrieve a specific override by id."""
        if override_id not in self._overrides:
            raise KeyError(f"No override with id '{override_id}'")
        return self._overrides[override_id]

    def list_overrides(self) -> list[HumanOverride]:
        """Return all overrides in creation order."""
        return list(self._overrides.values())

    def get_override_count(self) -> int:
        """Return the total number of overrides."""
        return len(self._overrides)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_exists(self, request_id: str) -> None:
        if request_id not in self._requests:
            raise KeyError(f"No request with id '{request_id}'")

    def _ensure_pending(self, request_id: str) -> None:
        if self._statuses[request_id] is not ApprovalStatus.PENDING:
            status = self._statuses[request_id].value
            raise RuntimeError(f"Request '{request_id}' is not pending (status: {status})")
