"""Human-in-the-loop adapter for MAVLink vehicle control.

Extends MAVLinkBridge to add human approval requirements for critical
vehicle actions. Integrates with the HITL approval workflow to ensure
operator authorization before arming, mode changes, and high-risk
control inputs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apex_autopilot_optimization.core.types import ControlInput
from apex_autopilot_optimization.hitl.config import HITLConfig
from apex_autopilot_optimization.hitl.request import ApprovalRequest
from apex_autopilot_optimization.hitl.status import ApprovalStatus
from apex_autopilot_optimization.hitl.workflow import ApprovalWorkflow
from apex_autopilot_optimization.integration.mavlink import MAVLinkBridge

logger = logging.getLogger(__name__)

# Risk levels for different vehicle actions
ACTION_RISK_LEVELS: dict[str, str] = {
    "arm": "high",
    "disarm": "medium",
    "set_mode": "medium",
    "send_control": "low",
    "takeoff": "high",
    "land": "medium",
    "rtl": "medium",
    "emergency_stop": "critical",
}

# Actions that always require approval regardless of risk level
MUST_APPROVE_ACTIONS: set[str] = {"arm", "takeoff", "emergency_stop"}


class HITLAdapter(MAVLinkBridge):
    """MAVLink bridge with human-in-the-loop approval requirements.

    Wraps a MAVLinkBridge instance and intercepts critical actions to
    require human approval before execution. Non-critical actions and
    state queries pass through directly to the underlying bridge.

    Attributes:
        workflow: The HITL approval workflow instance.
        auto_approve_low_risk: Whether low-risk actions skip approval.
    """

    def __init__(
        self,
        connection_string: str = "",
        simulation: bool = True,
        system_id: int = 1,
        component_id: int = 1,
        hitl_config: HITLConfig | None = None,
    ) -> None:
        """Initialize the HITL adapter.

        Args:
            connection_string: MAVLink connection URI.
            simulation: Force simulation mode.
            system_id: MAVLink system ID.
            component_id: MAVLink component ID.
            hitl_config: HITL configuration (uses defaults if None).
        """
        super().__init__(
            connection_string=connection_string,
            simulation=simulation,
            system_id=system_id,
            component_id=component_id,
        )
        self._hitl_config = hitl_config or HITLConfig()
        self._workflow = ApprovalWorkflow(config=self._hitl_config)
        self._pending_actions: dict[str, dict[str, Any]] = {}

    @property
    def workflow(self) -> ApprovalWorkflow:
        """Return the HITL approval workflow."""
        return self._workflow

    @property
    def hitl_config(self) -> HITLConfig:
        """Return the HITL configuration."""
        return self._hitl_config

    def arm(self) -> bool:
        """Arm the vehicle with human approval.

        Submits an approval request and only arms if approved.

        Returns:
            True if arming was approved and successful.
        """
        if not self._requires_approval("arm"):
            return super().arm()

        request = self._create_approval_request("arm", {"system_id": self._system_id})
        self._workflow.submit(request)

        if self._hitl_config.enabled:
            logger.info("Arm request %s pending approval", request.id)
            return False

        # HITL disabled: auto-approve
        return super().arm()

    def set_mode(self, mode: str) -> bool:
        """Set vehicle mode with human approval.

        Submits an approval request and only changes mode if approved.

        Args:
            mode: The desired flight mode.

        Returns:
            True if mode change was approved and successful.
        """
        if not self._requires_approval("set_mode"):
            return super().set_mode(mode)

        request = self._create_approval_request("set_mode", {"mode": mode})
        self._workflow.submit(request)

        if self._hitl_config.enabled:
            logger.info("Mode change request %s pending approval", request.id)
            return False

        return super().set_mode(mode)

    def send_control(self, control: ControlInput) -> bool:
        """Send control input with optional human approval.

        Low-risk control inputs pass through directly. High-risk inputs
        (e.g., high throttle) require approval.

        Args:
            control: Control input to send.

        Returns:
            True if control was sent successfully.
        """
        # Check if this control input is high-risk
        if abs(control.throttle) > 0.8 or abs(control.yaw_rate) > 1.0:
            if not self._requires_approval("send_control"):
                return super().send_control(control)

            request = self._create_approval_request(
                "send_control",
                {
                    "throttle": control.throttle,
                    "yaw_rate": control.yaw_rate,
                },
            )
            self._workflow.submit(request)

            if self._hitl_config.enabled:
                logger.info("Control request %s pending approval", request.id)
                return False

        return super().send_control(control)

    def approve_action(self, request_id: str, approver: str) -> bool:
        """Approve a pending action request.

        Args:
            request_id: The approval request ID.
            approver: Who is approving the action.

        Returns:
            True if approval was successful.
        """
        try:
            self._workflow.approve(request_id, approver=approver)
            return True
        except (KeyError, RuntimeError) as exc:
            logger.error("Failed to approve action %s: %s", request_id, exc)
            return False

    def reject_action(self, request_id: str, approver: str, reason: str) -> bool:
        """Reject a pending action request.

        Args:
            request_id: The approval request ID.
            approver: Who is rejecting the action.
            reason: Why the action is being rejected.

        Returns:
            True if rejection was successful.
        """
        try:
            self._workflow.reject(request_id, approver=approver, reason=reason)
            return True
        except (KeyError, RuntimeError) as exc:
            logger.error("Failed to reject action %s: %s", request_id, exc)
            return False

    def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get all pending approval requests.

        Returns:
            List of pending approval requests.
        """
        return self._workflow.get_pending()

    def get_approval_status(self, request_id: str) -> ApprovalStatus:
        """Get the status of an approval request.

        Args:
            request_id: The approval request ID.

        Returns:
            The current approval status.
        """
        return self._workflow.get_status(request_id)

    def _requires_approval(self, action: str) -> bool:
        """Check if an action requires human approval.

        Args:
            action: The action to check.

        Returns:
            True if the action requires approval.
        """
        if not self._hitl_config.enabled:
            return False

        if action in MUST_APPROVE_ACTIONS:
            return True

        risk = ACTION_RISK_LEVELS.get(action, "low")
        return not (risk == "low" and self._hitl_config.auto_approve_low_risk)

    def _create_approval_request(
        self, action: str, context: dict[str, Any]
    ) -> ApprovalRequest:
        """Create an approval request for an action.

        Args:
            action: The action being requested.
            context: Context data for the approver.

        Returns:
            The created approval request.
        """
        risk = ACTION_RISK_LEVELS.get(action, "low")
        priority = "high" if risk in ("high", "critical") else "medium"

        return ApprovalRequest(
            id="",
            action=action,
            requester="autopilot",
            context=context,
            priority=priority,
            created_at=time.time(),
            expires_at=time.time() + self._hitl_config.approval_timeout_seconds,
        )
