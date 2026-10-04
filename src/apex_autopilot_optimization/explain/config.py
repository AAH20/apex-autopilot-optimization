"""Configuration for the explainability layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExplainConfig:
    """Controls how the :class:`Explainer` produces explanations.

    Attributes:
        enabled: When ``False``, :meth:`Explainer.explain` refuses to run.
        min_confidence: Confidence threshold used by callers deciding whether
            an explanation is trustworthy.
        max_factors: Maximum number of contributing factors to retain per
            explanation (the highest-magnitude factors survive).
        include_counterfactuals: When ``True``, append counterfactual factors
            describing what would have changed the decision.
        audit_all: When ``True``, the audit trail is expected to record every
            decision, not just low-confidence ones.
    """

    enabled: bool = True
    min_confidence: float = 0.5
    max_factors: int = 10
    include_counterfactuals: bool = False
    audit_all: bool = False
