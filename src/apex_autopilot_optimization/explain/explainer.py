"""The :class:`Explainer` — turns a decision and its context into an auditable
:class:`Explanation`.

Factor weights are derived from the context by normalizing the absolute
magnitude of each context value, so every factor list sums to ~1.0 and the
largest-magnitude inputs dominate. When a model is supplied, its confidence is
recorded on the explanation.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from apex_autopilot_optimization.explain.config import ExplainConfig
from apex_autopilot_optimization.explain.explanation import Explanation


class Explainer:
    """Produce and retain explanations for decisions.

    Args:
        config: Behavioural configuration. Defaults to :class:`ExplainConfig`.
        model: Optional model callable (or object with a ``predict`` method)
            used to derive confidence and the model identifier.
    """

    def __init__(
        self,
        config: ExplainConfig | None = None,
        model: Any | None = None,
    ) -> None:
        self._config = config or ExplainConfig()
        self._model = model
        self._explanations: dict[str, Explanation] = {}

    # ── configuration ────────────────────────────────────────────────────────

    @property
    def config(self) -> ExplainConfig:
        """The active configuration."""
        return self._config

    # ── explanation ──────────────────────────────────────────────────────────

    def explain(self, decision: str, context: dict[str, Any]) -> Explanation:
        """Build and store an explanation for ``decision`` given ``context``.

        Args:
            decision: The decision label to explain.
            context: The inputs the decision was made from.

        Returns:
            The stored :class:`Explanation`.

        Raises:
            RuntimeError: If explanations are disabled in the configuration.
        """
        if not self._config.enabled:
            raise RuntimeError("explainability is disabled")

        factors = self._build_factors(context)
        confidence = self._derive_confidence(context)
        explanation = Explanation(
            id=uuid.uuid4().hex,
            decision=decision,
            context=dict(context),
            factors=factors,
            confidence=confidence,
            timestamp=time.time(),
            model=self._model_name(),
        )
        self._explanations[explanation.id] = explanation
        return explanation

    def get_explanation(self, explanation_id: str) -> Explanation | None:
        """Return a stored explanation by id, or ``None`` if unknown."""
        return self._explanations.get(explanation_id)

    def list_explanations(self) -> list[Explanation]:
        """Return all stored explanations in insertion order."""
        return list(self._explanations.values())

    def clear_explanations(self) -> None:
        """Remove every stored explanation."""
        self._explanations.clear()

    def get_explanation_count(self) -> int:
        """Return the number of stored explanations."""
        return len(self._explanations)

    # ── internals ────────────────────────────────────────────────────────────

    def _build_factors(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        magnitudes: list[tuple[str, Any, float]] = []
        for name, value in context.items():
            magnitude = abs(float(value)) if isinstance(value, (int, float)) else 0.0
            magnitudes.append((name, value, magnitude))

        total = sum(m for _, _, m in magnitudes)
        factors: list[dict[str, Any]] = []
        for name, value, magnitude in magnitudes:
            weight = magnitude / total if total > 0 else 0.0
            factors.append({"name": name, "value": value, "weight": weight, "type": "context"})

        factors.sort(key=lambda f: f["weight"], reverse=True)
        factors = factors[: self._config.max_factors]

        if self._config.include_counterfactuals:
            for factor in factors:
                factors.append(
                    {
                        "name": f"counterfactual:{factor['name']}",
                        "value": factor["value"],
                        "weight": 0.0,
                        "type": "counterfactual",
                        "description": (
                            f"Changing {factor['name']} would alter the decision"
                        ),
                    }
                )
        return factors

    def _derive_confidence(self, context: dict[str, Any]) -> float:
        if self._model is None:
            return 1.0
        predict = getattr(self._model, "predict", None)
        result: Any
        if callable(predict):
            result = predict(dict(context))
        elif callable(self._model):
            result = self._model(dict(context))
        else:
            return 1.0
        if isinstance(result, dict):
            return float(result.get("confidence", 1.0))
        try:
            return float(result)
        except (TypeError, ValueError):
            return 1.0

    def _model_name(self) -> str:
        if self._model is None:
            return "heuristic"
        name = getattr(self._model, "name", None)
        if isinstance(name, str) and name:
            return name
        return type(self._model).__name__
