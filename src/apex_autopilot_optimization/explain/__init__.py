"""Explainability and interpretability for apex-autopilot-optimization.

AI/ML decisions must be explainable. This package provides:

* :class:`Explainer` — produce :class:`Explanation` objects from decisions.
* :class:`Explanation` — an auditable record of a decision and its factors.
* :class:`FeatureImportance` — per-feature importance and direction.
* :class:`DecisionAudit` — an append-only decision audit trail.
* :class:`ExplainConfig` — behavioural configuration.
"""

from apex_autopilot_optimization.explain.audit import DecisionAudit
from apex_autopilot_optimization.explain.config import ExplainConfig
from apex_autopilot_optimization.explain.explainer import Explainer
from apex_autopilot_optimization.explain.explanation import Explanation
from apex_autopilot_optimization.explain.importance import (
    FeatureImportance,
    calculate_importance,
    get_importance_distribution,
    get_top_features,
)

__all__ = [
    "DecisionAudit",
    "ExplainConfig",
    "Explanation",
    "Explainer",
    "FeatureImportance",
    "calculate_importance",
    "get_importance_distribution",
    "get_top_features",
]
