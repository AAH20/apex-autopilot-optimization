"""Bias detection and scoring for apex-autopilot-optimization.

Implements group-level fairness metrics over labelled decision data. The
:class:`BiasDetector` consumes a list of records (dicts containing a
``selected`` boolean, one or more protected attribute keys, and optionally a
``label`` ground-truth key) and produces per-group selection rates plus
demographic-parity, equal-opportunity and equalized-odds style metrics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

DEFAULT_BIAS_THRESHOLD = 0.1


class BiasMetric(Enum):
    """Bias metrics computed by :class:`BiasDetector`."""

    DEMOGRAPHIC_PARITY = "demographic_parity"
    EQUAL_OPPORTUNITY = "equal_opportunity"
    EQUALIZED_ODDS = "equalized_odds"


def _selection_rate(records: list[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get("selected")) / len(records)


def _true_positive_rate(records: list[dict]) -> float | None:
    positives = [r for r in records if r.get("label") is True]
    if not positives:
        return None
    return sum(1 for r in positives if r.get("selected")) / len(positives)


def _false_positive_rate(records: list[dict]) -> float | None:
    negatives = [r for r in records if r.get("label") is False]
    if not negatives:
        return None
    return sum(1 for r in negatives if r.get("selected")) / len(negatives)


def _spread(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(values) - min(values)


class BiasDetector:
    """Detects group bias in decision data across protected attributes."""

    def __init__(self, threshold: float = DEFAULT_BIAS_THRESHOLD) -> None:
        self.threshold = threshold
        self._report: dict[str, Any] | None = None

    def detect_bias(self, data: list[dict], protected_attrs: list[str]) -> dict:
        """Analyse ``data`` for bias across ``protected_attrs``.

        Returns the generated report (also retrievable via
        :meth:`get_bias_report`).
        """
        groups: dict[str, dict[str, dict[str, Any]]] = {}
        parity_values: list[float] = []
        equal_opportunity_values: list[float] = []
        equalized_odds_values: list[float] = []

        for attr in protected_attrs:
            attr_groups: dict[str, dict[str, Any]] = {}
            rates: list[float] = []
            tprs: list[float] = []
            fprs: list[float] = []

            for record in data:
                if attr not in record:
                    continue
                group = str(record[attr])
                attr_groups.setdefault(group, {"records": []})["records"].append(record)

            for group, payload in attr_groups.items():
                records = payload["records"]
                rate = _selection_rate(records)
                tpr = _true_positive_rate(records)
                fpr = _false_positive_rate(records)
                rates.append(rate)
                if tpr is not None:
                    tprs.append(tpr)
                if fpr is not None:
                    fprs.append(fpr)
                attr_groups[group] = {
                    "count": len(records),
                    "selection_rate": rate,
                    "true_positive_rate": tpr,
                    "false_positive_rate": fpr,
                }

            groups[attr] = attr_groups
            parity_values.append(_spread(rates))
            if len(tprs) >= 2:
                equal_opportunity_values.append(_spread(tprs))
            if len(tprs) >= 2 and len(fprs) >= 2:
                equalized_odds_values.append(max(_spread(tprs), _spread(fprs)))

        demographic_parity = max(parity_values) if parity_values else 0.0
        equal_opportunity = (
            max(equal_opportunity_values) if equal_opportunity_values else None
        )
        equalized_odds = max(equalized_odds_values) if equalized_odds_values else None

        max_disparity = max(
            [demographic_parity]
            + [v for v in (equal_opportunity, equalized_odds) if v is not None]
        )
        bias_detected = max_disparity > self.threshold

        self._report = {
            "protected_attrs": list(protected_attrs),
            "groups": groups,
            "metrics": {
                BiasMetric.DEMOGRAPHIC_PARITY.value: demographic_parity,
                BiasMetric.EQUAL_OPPORTUNITY.value: equal_opportunity,
                BiasMetric.EQUALIZED_ODDS.value: equalized_odds,
            },
            "max_disparity": max_disparity,
            "bias_detected": bias_detected,
            "threshold": self.threshold,
        }
        return self._report

    def get_bias_report(self) -> dict:
        """Return the most recent bias report, or an empty report."""
        if self._report is None:
            return {
                "protected_attrs": [],
                "groups": {},
                "metrics": {
                    BiasMetric.DEMOGRAPHIC_PARITY.value: 0.0,
                    BiasMetric.EQUAL_OPPORTUNITY.value: None,
                    BiasMetric.EQUALIZED_ODDS.value: None,
                },
                "max_disparity": 0.0,
                "bias_detected": False,
                "threshold": self.threshold,
            }
        return self._report

    def get_bias_score(self) -> float:
        """Return a 0..1 fairness score (1.0 = no detected disparity)."""
        if self._report is None:
            return 1.0
        score = 1.0 - float(self._report["max_disparity"])
        return max(0.0, min(1.0, score))

    def clear_bias_data(self) -> None:
        """Discard all accumulated detection state."""
        self._report = None
