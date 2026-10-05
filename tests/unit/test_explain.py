"""Tests for the explainability / interpretability module.

Covers the public contract of :mod:`apex_autopilot_optimization.explain`:
the :class:`Explainer`, the :class:`Explanation` dataclass, feature
importance calculation, the decision audit trail, and :class:`ExplainConfig`.
"""

from __future__ import annotations

import json
import time

import pytest

from apex_autopilot_optimization.explain import (
    DecisionAudit,
    ExplainConfig,
    Explainer,
    Explanation,
    FeatureImportance,
)
from apex_autopilot_optimization.explain.importance import (
    calculate_importance,
    get_importance_distribution,
    get_top_features,
)

# ── Test models ──────────────────────────────────────────────────────────────


def _linear_model(data: dict) -> float:
    """Output is dominated by ``y`` and mildly by ``x``."""
    return data["x"] * 2.0 + data["y"]


def _negating_model(data: dict) -> float:
    """Increasing ``x`` decreases the output."""
    return -data["x"]


class _ConfidentModel:
    """A model exposing a confidence alongside its prediction."""

    name = "confident-model"

    def predict(self, data: dict) -> dict:
        return {"confidence": 0.9, "value": data.get("x", 0.0)}


class _PredictModel:
    """A model whose callable returns a bare float in [0, 1]."""

    name = "predict-model"

    def predict(self, data: dict) -> float:
        return 0.77


# ── ExplainConfig ────────────────────────────────────────────────────────────


class TestExplainConfig:
    def test_explain_config_defaults(self) -> None:
        cfg = ExplainConfig()
        assert cfg.enabled is True
        assert cfg.min_confidence == 0.5
        assert cfg.max_factors == 10
        assert cfg.include_counterfactuals is False
        assert cfg.audit_all is False

    def test_explain_config_custom(self) -> None:
        cfg = ExplainConfig(
            enabled=False,
            min_confidence=0.8,
            max_factors=3,
            include_counterfactuals=True,
            audit_all=True,
        )
        assert cfg.enabled is False
        assert cfg.min_confidence == 0.8
        assert cfg.max_factors == 3
        assert cfg.include_counterfactuals is True
        assert cfg.audit_all is True


# ── Explainer ────────────────────────────────────────────────────────────────


class TestExplainer:
    def test_explain_returns_explanation(self) -> None:
        explainer = Explainer()
        before = time.time()
        exp = explainer.explain("reroute", {"wind": 3.0, "fuel": 12.0})
        after = time.time()
        assert isinstance(exp, Explanation)
        assert exp.decision == "reroute"
        assert exp.context == {"wind": 3.0, "fuel": 12.0}
        assert before <= exp.timestamp <= after
        assert exp.id

    def test_explain_factors_derived_from_context(self) -> None:
        explainer = Explainer()
        exp = explainer.explain("reroute", {"wind": 3.0, "fuel": 12.0})
        names = {f["name"] for f in exp.factors}
        assert names == {"wind", "fuel"}
        # Normalized weights sum to ~1.
        assert sum(f["weight"] for f in exp.factors) == pytest.approx(1.0)

    def test_explain_respects_max_factors(self) -> None:
        explainer = Explainer(config=ExplainConfig(max_factors=2))
        exp = explainer.explain("reroute", {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0})
        assert len(exp.factors) == 2
        # The two largest-magnitude features survive.
        assert {f["name"] for f in exp.factors} == {"c", "d"}

    def test_explain_disabled_raises(self) -> None:
        explainer = Explainer(config=ExplainConfig(enabled=False))
        with pytest.raises(RuntimeError):
            explainer.explain("reroute", {"wind": 1.0})

    def test_explain_includes_counterfactuals_when_enabled(self) -> None:
        explainer = Explainer(config=ExplainConfig(include_counterfactuals=True))
        exp = explainer.explain("reroute", {"wind": 3.0})
        assert any(f.get("type") == "counterfactual" for f in exp.factors)

    def test_explain_no_counterfactuals_by_default(self) -> None:
        explainer = Explainer()
        exp = explainer.explain("reroute", {"wind": 3.0})
        assert not any(f.get("type") == "counterfactual" for f in exp.factors)

    def test_explain_uses_model_confidence(self) -> None:
        explainer = Explainer(model=_ConfidentModel())
        exp = explainer.explain("reroute", {"x": 2.0})
        assert exp.confidence == pytest.approx(0.9)
        assert exp.model == "confident-model"

    def test_explain_model_float_confidence(self) -> None:
        explainer = Explainer(model=_PredictModel())
        exp = explainer.explain("reroute", {"x": 2.0})
        assert exp.confidence == pytest.approx(0.77)

    def test_get_explanation_roundtrip(self) -> None:
        explainer = Explainer()
        exp = explainer.explain("reroute", {"wind": 1.0})
        assert explainer.get_explanation(exp.id) is exp

    def test_get_explanation_missing_returns_none(self) -> None:
        explainer = Explainer()
        assert explainer.get_explanation("does-not-exist") is None

    def test_list_explanations(self) -> None:
        explainer = Explainer()
        a = explainer.explain("a", {"x": 1.0})
        b = explainer.explain("b", {"x": 2.0})
        listed = explainer.list_explanations()
        assert {e.id for e in listed} == {a.id, b.id}

    def test_get_explanation_count(self) -> None:
        explainer = Explainer()
        assert explainer.get_explanation_count() == 0
        explainer.explain("a", {"x": 1.0})
        explainer.explain("b", {"x": 2.0})
        assert explainer.get_explanation_count() == 2

    def test_clear_explanations(self) -> None:
        explainer = Explainer()
        explainer.explain("a", {"x": 1.0})
        explainer.clear_explanations()
        assert explainer.get_explanation_count() == 0
        assert explainer.list_explanations() == []


# ── Explanation dataclass ────────────────────────────────────────────────────


class TestExplanation:
    def _make(self) -> Explanation:
        return Explanation(
            id="exp-1",
            decision="reroute",
            context={"wind": 3.0},
            factors=[
                {"name": "wind", "value": 3.0, "weight": 0.3},
                {"name": "fuel", "value": 12.0, "weight": 0.7},
                {"name": "traffic", "value": 1.0, "weight": 0.0},
            ],
            confidence=0.82,
            timestamp=123.0,
            model="planner",
        )

    def test_explanation_creation(self) -> None:
        exp = self._make()
        assert exp.id == "exp-1"
        assert exp.decision == "reroute"
        assert exp.context == {"wind": 3.0}
        assert exp.confidence == 0.82
        assert exp.timestamp == 123.0
        assert exp.model == "planner"
        assert len(exp.factors) == 3

    def test_explanation_top_factors(self) -> None:
        exp = self._make()
        top = exp.get_top_factors(2)
        assert [f["name"] for f in top] == ["fuel", "wind"]

    def test_explanation_top_factors_default_all_sorted(self) -> None:
        exp = self._make()
        top = exp.get_top_factors()
        assert [f["name"] for f in top] == ["fuel", "wind", "traffic"]

    def test_explanation_get_factor_by_name(self) -> None:
        exp = self._make()
        assert exp.get_factor_by_name("fuel") == {
            "name": "fuel",
            "value": 12.0,
            "weight": 0.7,
        }

    def test_explanation_get_factor_by_name_missing(self) -> None:
        exp = self._make()
        assert exp.get_factor_by_name("nope") is None

    def test_explanation_is_confident(self) -> None:
        exp = self._make()
        assert exp.is_confident(0.8) is True
        assert exp.is_confident(0.9) is False


# ── Feature importance ───────────────────────────────────────────────────────


class TestFeatureImportance:
    def test_feature_importance_creation(self) -> None:
        fi = FeatureImportance(feature="wind", importance=0.4, direction="positive")
        assert fi.feature == "wind"
        assert fi.importance == 0.4
        assert fi.direction == "positive"

    def test_calculate_importance(self) -> None:
        result = calculate_importance(["x", "y"], _linear_model, {"x": 1.0, "y": 5.0})
        assert {fi.feature for fi in result} == {"x", "y"}
        by_name = {fi.feature: fi for fi in result}
        # y contributes more absolute change than x.
        assert by_name["y"].importance > by_name["x"].importance
        assert all(fi.importance >= 0 for fi in result)

    def test_calculate_importance_direction(self) -> None:
        result = calculate_importance(["x"], _negating_model, {"x": 4.0})
        assert result[0].direction == "negative"

    def test_calculate_importance_neutral_for_missing(self) -> None:
        result = calculate_importance(["missing"], _linear_model, {"x": 1.0})
        assert result[0].importance == 0.0
        assert result[0].direction == "neutral"

    def test_get_top_features(self) -> None:
        importances = [
            FeatureImportance(feature="a", importance=0.1, direction="positive"),
            FeatureImportance(feature="b", importance=0.9, direction="negative"),
            FeatureImportance(feature="c", importance=0.5, direction="positive"),
        ]
        top = get_top_features(importances, 2)
        assert [fi.feature for fi in top] == ["b", "c"]

    def test_get_importance_distribution(self) -> None:
        importances = [
            FeatureImportance(feature="a", importance=0.2, direction="positive"),
            FeatureImportance(feature="b", importance=0.6, direction="negative"),
        ]
        dist = get_importance_distribution(importances)
        assert dist["a"] == pytest.approx(0.25)
        assert dist["b"] == pytest.approx(0.75)
        assert sum(dist.values()) == pytest.approx(1.0)

    def test_get_importance_distribution_all_zero(self) -> None:
        importances = [
            FeatureImportance(feature="a", importance=0.0, direction="neutral"),
        ]
        dist = get_importance_distribution(importances)
        assert dist["a"] == 0.0


# ── Decision audit ───────────────────────────────────────────────────────────


class TestDecisionAudit:
    def test_log_decision(self) -> None:
        audit = DecisionAudit()
        entry_id = audit.log_decision("reroute", {"wind": 3.0}, {"confidence": 0.9})
        assert isinstance(entry_id, str)
        assert entry_id

    def test_get_audit_trail(self) -> None:
        audit = DecisionAudit()
        explainer = Explainer()
        exp = explainer.explain("reroute", {"wind": 3.0})
        audit.log_decision("reroute", {"wind": 3.0}, exp)
        audit.log_decision("land", {"fuel": 1.0}, None)
        trail = audit.get_audit_trail("reroute")
        assert len(trail) == 1
        assert trail[0]["decision"] == "reroute"
        assert trail[0]["context"] == {"wind": 3.0}

    def test_get_audit_trail_unknown(self) -> None:
        audit = DecisionAudit()
        audit.log_decision("reroute", {}, None)
        assert audit.get_audit_trail("nope") == []

    def test_get_audit_stats(self) -> None:
        audit = DecisionAudit()
        audit.log_decision("reroute", {}, {"confidence": 0.9})
        audit.log_decision("reroute", {}, None)
        audit.log_decision("land", {}, None)
        stats = audit.get_audit_stats()
        assert stats["total_entries"] == 3
        assert stats["unique_decisions"] == 2
        assert stats["by_decision"]["reroute"] == 2
        assert stats["by_decision"]["land"] == 1
        assert stats["explanations_logged"] == 1

    def test_get_audit_stats_empty(self) -> None:
        stats = DecisionAudit().get_audit_stats()
        assert stats["total_entries"] == 0
        assert stats["unique_decisions"] == 0

    def test_export_audit_json(self) -> None:
        audit = DecisionAudit()
        audit.log_decision("reroute", {"wind": 3.0}, None)
        payload = audit.export_audit("json")
        parsed = json.loads(payload)
        assert isinstance(parsed, list)
        assert parsed[0]["decision"] == "reroute"

    def test_export_audit_csv(self) -> None:
        audit = DecisionAudit()
        audit.log_decision("reroute", {"wind": 3.0}, None)
        payload = audit.export_audit("csv")
        lines = payload.strip().splitlines()
        assert "decision" in lines[0]
        assert "reroute" in payload

    def test_export_audit_invalid_format(self) -> None:
        audit = DecisionAudit()
        with pytest.raises(ValueError):
            audit.export_audit("xml")

    def test_clear_audit(self) -> None:
        audit = DecisionAudit()
        audit.log_decision("reroute", {}, None)
        audit.clear_audit()
        assert audit.get_audit_stats()["total_entries"] == 0
