"""Feature importance via single-feature perturbation.

Importance is measured by changing one feature at a time and observing how far
the model's output moves. A relative perturbation (the feature's own magnitude,
falling back to ``1.0`` for zero-valued features) keeps the measurement
scale-free, so features on different scales stay comparable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass
class FeatureImportance:
    """Importance of a single feature for a model's output.

    Attributes:
        feature: The feature name.
        importance: Non-negative magnitude of the feature's effect.
        direction: ``"positive"`` if raising the feature raises the output,
            ``"negative"`` if it lowers it, ``"neutral"`` if it has no effect.
    """

    feature: str
    importance: float
    direction: str


def _predict(model: Callable[[dict[str, Any]], Any], data: dict[str, Any]) -> float:
    """Call ``model`` on ``data`` and coerce the result to a float."""
    predict = getattr(model, "predict", None)
    result: Any
    if callable(predict):
        result = predict(data)
    else:
        result = model(data)
    if isinstance(result, dict):
        return float(result.get("value", result.get("confidence", 0.0)))
    return float(result)


def calculate_importance(
    features: Sequence[str],
    model: Callable[[dict[str, Any]], Any],
    input_data: dict[str, Any],
) -> list[FeatureImportance]:
    """Compute per-feature importance by perturbing one feature at a time.

    Args:
        features: Names of the features to score.
        model: Callable (or object with a ``predict`` method) mapping an input
            dict to an output value.
        input_data: The baseline input to perturb.

    Returns:
        One :class:`FeatureImportance` per feature, in the order given.
    """
    baseline = _predict(model, dict(input_data))
    results: list[FeatureImportance] = []
    for feature in features:
        if feature not in input_data:
            results.append(FeatureImportance(feature=feature, importance=0.0, direction="neutral"))
            continue
        value = input_data[feature]
        delta = abs(value) if isinstance(value, (int, float)) and value != 0 else 1.0
        perturbed = dict(input_data)
        perturbed[feature] = value + delta
        shifted = _predict(model, perturbed)
        change = shifted - baseline
        importance = abs(change)
        if importance == 0.0:
            direction = "neutral"
        elif change > 0:
            direction = "positive"
        else:
            direction = "negative"
        results.append(
            FeatureImportance(feature=feature, importance=importance, direction=direction)
        )
    return results


def get_top_features(
    importances: Sequence[FeatureImportance],
    n: int | None = None,
) -> list[FeatureImportance]:
    """Return importances sorted by descending importance (optionally top ``n``)."""
    ordered = sorted(importances, key=lambda fi: fi.importance, reverse=True)
    return ordered if n is None else ordered[:n]


def get_importance_distribution(
    importances: Sequence[FeatureImportance],
) -> dict[str, float]:
    """Return each feature's share of total importance (sums to ~1.0).

    When the total importance is zero every feature is assigned ``0.0``.
    """
    total = sum(fi.importance for fi in importances)
    if total <= 0:
        return {fi.feature: 0.0 for fi in importances}
    return {fi.feature: fi.importance / total for fi in importances}
