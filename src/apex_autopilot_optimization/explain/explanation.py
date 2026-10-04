"""The :class:`Explanation` value object.

An explanation records why a decision was made: the decision label, the
context it was made in, the contributing factors (with normalized weights), a
confidence score, and the model that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Explanation:
    """A single, auditable explanation of a decision.

    Attributes:
        id: Unique identifier for this explanation.
        decision: The decision label being explained.
        context: The inputs the decision was made from.
        factors: Contributing factors, each a dict with at least ``name`` and
            ``weight`` keys.
        confidence: Model confidence in the decision, in ``[0, 1]``.
        timestamp: Unix timestamp of when the explanation was created.
        model: Identifier of the model that produced the decision.
    """

    id: str
    decision: str
    context: dict[str, Any]
    factors: list[dict[str, Any]]
    confidence: float
    timestamp: float
    model: str

    def get_top_factors(self, n: int | None = None) -> list[dict[str, Any]]:
        """Return factors sorted by descending weight.

        Args:
            n: If given, return only the ``n`` highest-weighted factors.
        """
        ordered = sorted(self.factors, key=lambda f: f.get("weight", 0.0), reverse=True)
        return ordered if n is None else ordered[:n]

    def get_factor_by_name(self, name: str) -> dict[str, Any] | None:
        """Return the factor with the given name, or ``None`` if absent."""
        for factor in self.factors:
            if factor.get("name") == name:
                return factor
        return None

    def is_confident(self, threshold: float) -> bool:
        """Return whether the confidence meets ``threshold``."""
        return self.confidence >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Serialize the explanation to a plain, JSON-friendly dict."""
        return {
            "id": self.id,
            "decision": self.decision,
            "context": dict(self.context),
            "factors": [dict(f) for f in self.factors],
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "model": self.model,
        }
