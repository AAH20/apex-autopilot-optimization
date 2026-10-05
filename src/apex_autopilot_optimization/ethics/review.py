"""Human-in-the-loop ethics review workflow.

Actions that require ethical sign-off are submitted as review requests. Each
request moves through a small state machine: ``pending`` -> ``approved`` or
``rejected``. :class:`EthicsReview` owns the request store and exposes lookup,
decision and listing helpers.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class EthicsReview:
    """Manages ethics review requests and their decisions."""

    def __init__(self) -> None:
        self._reviews: dict[str, dict[str, Any]] = {}

    def submit_for_review(self, action: dict[str, Any], context: dict[str, Any]) -> str:
        """Submit ``action`` for ethics review and return a review id."""
        review_id = uuid.uuid4().hex
        self._reviews[review_id] = {
            "review_id": review_id,
            "action": action,
            "context": context,
            "status": STATUS_PENDING,
            "reviewer": None,
            "reason": None,
            "submitted_at": time.time(),
            "decided_at": None,
        }
        return review_id

    def get_review_status(self, review_id: str) -> str | None:
        """Return the status of a review, or None if unknown."""
        review = self._reviews.get(review_id)
        return review["status"] if review else None

    def get_review_decision(self, review_id: str) -> dict[str, Any] | None:
        """Return the decision record for a review, or None if unknown."""
        review = self._reviews.get(review_id)
        if review is None:
            return None
        return {
            "review_id": review_id,
            "status": review["status"],
            "reviewer": review["reviewer"],
            "reason": review["reason"],
            "decided_at": review["decided_at"],
        }

    def approve_review(self, review_id: str, reviewer: str) -> bool:
        """Approve a pending review. Returns False if not pending/unknown."""
        review = self._reviews.get(review_id)
        if review is None or review["status"] != STATUS_PENDING:
            return False
        review["status"] = STATUS_APPROVED
        review["reviewer"] = reviewer
        review["decided_at"] = time.time()
        return True

    def reject_review(self, review_id: str, reviewer: str, reason: str) -> bool:
        """Reject a pending review. Returns False if not pending/unknown."""
        review = self._reviews.get(review_id)
        if review is None or review["status"] != STATUS_PENDING:
            return False
        review["status"] = STATUS_REJECTED
        review["reviewer"] = reviewer
        review["reason"] = reason
        review["decided_at"] = time.time()
        return True

    def get_pending_reviews(self) -> list[dict[str, Any]]:
        """Return all reviews still awaiting a decision."""
        return [
            {
                "review_id": r["review_id"],
                "action": r["action"],
                "context": r["context"],
                "status": r["status"],
                "submitted_at": r["submitted_at"],
            }
            for r in self._reviews.values()
            if r["status"] == STATUS_PENDING
        ]
