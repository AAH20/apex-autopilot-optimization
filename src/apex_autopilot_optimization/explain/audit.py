"""Append-only decision audit trail.

:class:`DecisionAudit` records every decision together with the context it was
made in and the explanation (if any) that accompanied it, then exposes
trail/stats queries and JSON/CSV export for compliance and post-hoc review.
"""

from __future__ import annotations

import csv
import io
import json
import time
import uuid
from typing import Any

from apex_autopilot_optimization.explain.explanation import Explanation


class DecisionAudit:
    """Record decisions and their explanations for later inspection."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    # ── recording ────────────────────────────────────────────────────────────

    def log_decision(
        self,
        decision: str,
        context: dict[str, Any],
        explanation: Explanation | dict[str, Any] | None,
    ) -> str:
        """Append a decision to the audit trail.

        Args:
            decision: The decision label.
            context: The inputs the decision was made from.
            explanation: The explanation object (or its dict form), or ``None``.

        Returns:
            The id of the created audit entry.
        """
        entry_id = uuid.uuid4().hex
        self._entries.append(
            {
                "id": entry_id,
                "decision": decision,
                "context": dict(context),
                "explanation": self._serialize_explanation(explanation),
                "timestamp": time.time(),
            }
        )
        return entry_id

    def get_audit_trail(self, decision_id: str) -> list[dict[str, Any]]:
        """Return every entry whose decision matches ``decision_id``."""
        return [e for e in self._entries if e["decision"] == decision_id]

    def get_audit_stats(self) -> dict[str, Any]:
        """Summarize the audit trail."""
        by_decision: dict[str, int] = {}
        for entry in self._entries:
            by_decision[entry["decision"]] = by_decision.get(entry["decision"], 0) + 1
        return {
            "total_entries": len(self._entries),
            "unique_decisions": len(by_decision),
            "by_decision": by_decision,
            "explanations_logged": sum(
                1 for e in self._entries if e["explanation"] is not None
            ),
        }

    def export_audit(self, format: str = "json") -> str:
        """Export the audit trail as ``"json"`` or ``"csv"``.

        Raises:
            ValueError: If ``format`` is neither ``"json"`` nor ``"csv"``.
        """
        if format == "json":
            return json.dumps(self._entries, indent=2, default=str)
        if format == "csv":
            return self._export_csv()
        raise ValueError(f"unsupported audit export format: {format!r}")

    def clear_audit(self) -> None:
        """Remove every audit entry."""
        self._entries.clear()

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_explanation(
        explanation: Explanation | dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if explanation is None:
            return None
        if isinstance(explanation, Explanation):
            return explanation.to_dict()
        return dict(explanation)

    def _export_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "decision", "context", "has_explanation", "timestamp"])
        for entry in self._entries:
            writer.writerow(
                [
                    entry["id"],
                    entry["decision"],
                    json.dumps(entry["context"], default=str),
                    entry["explanation"] is not None,
                    entry["timestamp"],
                ]
            )
        return buffer.getvalue()
