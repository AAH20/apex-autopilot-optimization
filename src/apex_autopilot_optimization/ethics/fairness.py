"""Fairness metrics and auditing for apex-autopilot-optimization.

Computes per-group fairness metrics from model predictions, ground-truth
labels and protected attribute assignments, and exposes both an object-oriented
:class:`FairnessAuditor` API and module-level convenience functions backed by a
shared auditor instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_FAIRNESS_THRESHOLD = 0.8
DISPARATE_IMPACT_THRESHOLD = 0.8


@dataclass
class FairnessMetric:
    """A single fairness metric with its value, threshold and verdict."""

    name: str
    value: float
    threshold: str
    passed: bool


def _selection_rate(predictions: list[bool], protected: list[str]) -> float:
    if not protected:
        return 0.0
    return sum(1 for p in predictions if p) / len(protected)


def _true_positive_rate(predictions: list[bool], labels: list[bool]) -> float | None:
    positives = [(p, y) for p, y in zip(predictions, labels, strict=False) if y]
    if not positives:
        return None
    return sum(1 for p, _ in positives if p) / len(positives)


def _false_positive_rate(predictions: list[bool], labels: list[bool]) -> float | None:
    negatives = [(p, y) for p, y in zip(predictions, labels, strict=False) if not y]
    if not negatives:
        return None
    return sum(1 for p, _ in negatives if p) / len(negatives)


def _grouped(values: list[Any], protected: list[str]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for value, group in zip(values, protected, strict=False):
        grouped.setdefault(str(group), []).append(value)
    return grouped


class FairnessAuditor:
    """Computes and stores fairness metrics for a set of predictions."""

    def __init__(self, fairness_threshold: float = DEFAULT_FAIRNESS_THRESHOLD) -> None:
        self.fairness_threshold = fairness_threshold
        self._metrics: list[FairnessMetric] = []

    def calculate_fairness(
        self, predictions: list[bool], labels: list[bool], protected_attrs: list[str]
    ) -> list[FairnessMetric]:
        """Compute fairness metrics for ``predictions`` against ``labels``.

        ``protected_attrs`` holds the group assignment for each sample.
        Returns the list of :class:`FairnessMetric` objects and stores them for
        later retrieval via :meth:`get_fairness_report`.
        """
        pred_groups = _grouped(predictions, protected_attrs)
        label_groups = _grouped(labels, protected_attrs)

        rates = [_selection_rate(pred_groups[g], pred_groups[g]) for g in pred_groups]
        max_rate = max(rates) if rates else 0.0
        min_rate = min(rates) if rates else 0.0

        # Disparate impact ratio: min group rate / max group rate (the "80% rule").
        if max_rate == 0.0:
            disparate_impact = 1.0 if min_rate == 0.0 else 0.0
        else:
            disparate_impact = min_rate / max_rate
        di_passed = disparate_impact >= DISPARATE_IMPACT_THRESHOLD

        # Equal opportunity: max difference in true-positive rates across groups.
        tprs = [_true_positive_rate(pred_groups[g], label_groups.get(g, [])) for g in pred_groups]
        tprs = [t for t in tprs if t is not None]
        equal_opportunity = max(tprs) - min(tprs) if len(tprs) >= 2 else 0.0  # type: ignore[type-var,operator]
        eo_passed = equal_opportunity <= (1.0 - self.fairness_threshold)

        # Equalized odds: worst of TPR/FPR spreads.
        fprs = [_false_positive_rate(pred_groups[g], label_groups.get(g, [])) for g in pred_groups]
        fprs = [f for f in fprs if f is not None]
        if len(tprs) >= 2 and len(fprs) >= 2:
            equalized_odds = max(max(tprs) - min(tprs), max(fprs) - min(fprs))  # type: ignore[type-var,operator]
        else:
            equalized_odds = 0.0
        eo_odds_passed = equalized_odds <= (1.0 - self.fairness_threshold)

        # Demographic parity: max difference in selection rates.
        demographic_parity = max_rate - min_rate
        dp_passed = demographic_parity <= (1.0 - self.fairness_threshold)

        self._metrics = [
            FairnessMetric(
                name="disparate_impact",
                value=disparate_impact,
                threshold=f">= {DISPARATE_IMPACT_THRESHOLD}",
                passed=di_passed,
            ),
            FairnessMetric(
                name="demographic_parity",
                value=demographic_parity,
                threshold=f"<= {1.0 - self.fairness_threshold}",
                passed=dp_passed,
            ),
            FairnessMetric(
                name="equal_opportunity",
                value=equal_opportunity,
                threshold=f"<= {1.0 - self.fairness_threshold}",
                passed=eo_passed,
            ),
            FairnessMetric(
                name="equalized_odds",
                value=equalized_odds,
                threshold=f"<= {1.0 - self.fairness_threshold}",
                passed=eo_odds_passed,
            ),
        ]
        return list(self._metrics)

    def get_fairness_report(self) -> dict[str, Any]:
        """Return a structured fairness report."""
        return {
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "threshold": m.threshold,
                    "passed": m.passed,
                }
                for m in self._metrics
            ],
            "score": self.get_fairness_score(),
            "disparate_impact": self.get_disparate_impact(),
            "fair": all(m.passed for m in self._metrics) if self._metrics else True,
        }

    def get_disparate_impact(self) -> float:
        """Return the most recently computed disparate-impact ratio."""
        for metric in self._metrics:
            if metric.name == "disparate_impact":
                return metric.value
        return 1.0

    def get_fairness_score(self) -> float:
        """Return the fraction of fairness metrics that passed (0..1)."""
        if not self._metrics:
            return 1.0
        return sum(1 for m in self._metrics if m.passed) / len(self._metrics)


# ---------------------------------------------------------------------------
# Module-level convenience API backed by a shared auditor.
# ---------------------------------------------------------------------------

_default_auditor = FairnessAuditor()


def calculate_fairness(
    predictions: list[bool], labels: list[bool], protected_attrs: list[str]
) -> list[FairnessMetric]:
    """Compute fairness metrics using the shared auditor."""
    return _default_auditor.calculate_fairness(predictions, labels, protected_attrs)


def get_fairness_report() -> dict[str, Any]:
    """Return the shared auditor's fairness report."""
    return _default_auditor.get_fairness_report()


def get_disparate_impact() -> float:
    """Return the shared auditor's disparate-impact ratio."""
    return _default_auditor.get_disparate_impact()


def get_fairness_score() -> float:
    """Return the shared auditor's fairness score."""
    return _default_auditor.get_fairness_score()
