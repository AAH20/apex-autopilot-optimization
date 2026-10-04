"""Ethics, bias detection, and fairness auditing for apex-autopilot-optimization.

This package provides the ethical guardrails the autopilot stack was missing:
declarative ethics policies with machine-checkable constraints, group-level bias
detection, fairness metrics with a disparate-impact audit, and a human-in-the-loop
review workflow.
"""

from apex_autopilot_optimization.ethics.bias import BiasDetector, BiasMetric
from apex_autopilot_optimization.ethics.config import EthicsConfig
from apex_autopilot_optimization.ethics.fairness import FairnessMetric
from apex_autopilot_optimization.ethics.policy import (
    EthicsPolicy,
    EthicsPrinciple,
    evaluate_action,
    get_policy_summary,
    get_violations,
)
from apex_autopilot_optimization.ethics.review import EthicsReview

__all__ = [
    "EthicsPolicy",
    "EthicsPrinciple",
    "BiasDetector",
    "BiasMetric",
    "FairnessMetric",
    "EthicsReview",
    "EthicsConfig",
    "evaluate_action",
    "get_violations",
    "get_policy_summary",
]
