"""Unit tests for the ethics, bias detection, and fairness module.

Covers ethics policy creation/evaluation, bias detection and scoring,
fairness metrics and reporting, ethics review workflow, and configuration.
"""

import pytest

from apex_autopilot_optimization.ethics import (
    BiasDetector,
    BiasMetric,
    EthicsConfig,
    EthicsPolicy,
    EthicsPrinciple,
    EthicsReview,
    FairnessMetric,
)
from apex_autopilot_optimization.ethics.fairness import FairnessAuditor
from apex_autopilot_optimization.ethics.policy import (
    evaluate_action,
    get_policy_summary,
    get_violations,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_policy() -> EthicsPolicy:
    return EthicsPolicy(
        name="Autopilot Ethics Policy",
        description="Core ethical guardrails for autonomous decisions",
        principles=[EthicsPrinciple.SAFETY.value, EthicsPrinciple.PRIVACY.value],
        constraints=[
            {"principle": "safety", "field": "risk_score", "operator": "max", "value": 0.5},
            {"principle": "transparency", "field": "explainable", "operator": "must_be_true"},
            {"principle": "privacy", "field": "contains_pii", "operator": "must_be_false"},
        ],
        enforcement="strict",
    )


COMPLIANT_ACTION = {"risk_score": 0.2, "explainable": True, "contains_pii": False}


# ---------------------------------------------------------------------------
# EthicsPrinciple enumeration
# ---------------------------------------------------------------------------


class TestEthicsPrinciple:
    """Ethics principle enumeration."""

    def test_principle_values(self):
        assert EthicsPrinciple.TRANSPARENCY.value == "transparency"
        assert EthicsPrinciple.FAIRNESS.value == "fairness"
        assert EthicsPrinciple.ACCOUNTABILITY.value == "accountability"
        assert EthicsPrinciple.PRIVACY.value == "privacy"
        assert EthicsPrinciple.SAFETY.value == "safety"

    def test_principle_member_count(self):
        assert len(list(EthicsPrinciple)) == 5

    def test_principle_lookup_by_value(self):
        assert EthicsPrinciple("fairness") is EthicsPrinciple.FAIRNESS


# ---------------------------------------------------------------------------
# EthicsPolicy creation
# ---------------------------------------------------------------------------


class TestEthicsPolicy:
    """Ethics policy creation and structure."""

    def test_policy_fields(self):
        policy = make_policy()
        assert policy.name == "Autopilot Ethics Policy"
        assert policy.description == "Core ethical guardrails for autonomous decisions"
        assert policy.enforcement == "strict"

    def test_policy_principles(self):
        policy = make_policy()
        assert policy.principles == ["safety", "privacy"]
        assert len(policy.principles) == 2

    def test_policy_constraints(self):
        policy = make_policy()
        assert len(policy.constraints) == 3
        assert policy.constraints[0]["field"] == "risk_score"

    def test_policy_defaults_are_independent(self):
        a = EthicsPolicy(
            name="a", description="d", principles=[], constraints=[], enforcement="warn"
        )
        b = EthicsPolicy(
            name="b", description="d", principles=[], constraints=[], enforcement="warn"
        )
        a.principles.append("safety")
        assert b.principles == []


# ---------------------------------------------------------------------------
# Ethics action evaluation
# ---------------------------------------------------------------------------


class TestEvaluateAction:
    """Evaluating actions against an ethics policy."""

    def test_compliant_action_passes(self):
        assert evaluate_action(COMPLIANT_ACTION, make_policy()) is True

    def test_high_risk_action_fails(self):
        action = dict(COMPLIANT_ACTION, risk_score=0.9)
        assert evaluate_action(action, make_policy()) is False

    def test_non_explainable_action_fails(self):
        action = dict(COMPLIANT_ACTION, explainable=False)
        assert evaluate_action(action, make_policy()) is False

    def test_pii_action_fails(self):
        action = dict(COMPLIANT_ACTION, contains_pii=True)
        assert evaluate_action(action, make_policy()) is False

    def test_empty_policy_passes_everything(self):
        policy = EthicsPolicy(
            name="empty", description="d", principles=[], constraints=[], enforcement="advisory"
        )
        assert evaluate_action({"anything": 1}, policy) is True

    def test_missing_required_field_fails(self):
        action = {"explainable": True, "contains_pii": False}  # risk_score missing
        assert evaluate_action(action, make_policy()) is False

    def test_boundary_max_is_inclusive(self):
        action = dict(COMPLIANT_ACTION, risk_score=0.5)
        assert evaluate_action(action, make_policy()) is True

    def test_min_operator_passes(self):
        policy = EthicsPolicy(
            name="min", description="d", principles=[], constraints=[
                {"principle": "safety", "field": "confidence", "operator": "min", "value": 0.5}
            ]
        )
        assert evaluate_action({"confidence": 0.7}, policy) is True

    def test_min_operator_fails(self):
        policy = EthicsPolicy(
            name="min", description="d", principles=[], constraints=[
                {"principle": "safety", "field": "confidence", "operator": "min", "value": 0.5}
            ]
        )
        assert evaluate_action({"confidence": 0.3}, policy) is False

    def test_equals_operator(self):
        policy = EthicsPolicy(
            name="eq", description="d", principles=[], constraints=[
                {
                    "principle": "privacy",
                    "field": "data_class",
                    "operator": "equals",
                    "value": "public",
                }
            ]
        )
        assert evaluate_action({"data_class": "public"}, policy) is True
        assert evaluate_action({"data_class": "private"}, policy) is False

    def test_not_equals_operator(self):
        policy = EthicsPolicy(
            name="neq", description="d", principles=[], constraints=[
                {
                    "principle": "privacy",
                    "field": "data_class",
                    "operator": "not_equals",
                    "value": "sensitive",
                }
            ]
        )
        assert evaluate_action({"data_class": "public"}, policy) is True
        assert evaluate_action({"data_class": "sensitive"}, policy) is False

    def test_unknown_operator_fails(self):
        policy = EthicsPolicy(
            name="unk", description="d", principles=[], constraints=[
                {"principle": "safety", "field": "x", "operator": "nope", "value": 1}
            ]
        )
        assert evaluate_action({"x": 1}, policy) is False


# ---------------------------------------------------------------------------
# Ethics violations
# ---------------------------------------------------------------------------


class TestGetViolations:
    """Extracting ethics violations."""

    def test_compliant_action_has_no_violations(self):
        assert get_violations(COMPLIANT_ACTION, make_policy()) == []

    def test_high_risk_produces_one_violation(self):
        violations = get_violations(dict(COMPLIANT_ACTION, risk_score=0.9), make_policy())
        assert len(violations) == 1
        assert violations[0]["field"] == "risk_score"
        assert violations[0]["principle"] == "safety"

    def test_multiple_violations(self):
        action = {"risk_score": 0.9, "explainable": False, "contains_pii": True}
        violations = get_violations(action, make_policy())
        assert len(violations) == 3
        fields = {v["field"] for v in violations}
        assert fields == {"risk_score", "explainable", "contains_pii"}

    def test_violation_has_message_and_constraint(self):
        violations = get_violations(dict(COMPLIANT_ACTION, risk_score=0.9), make_policy())
        assert "message" in violations[0]
        assert violations[0]["constraint"]["operator"] == "max"


# ---------------------------------------------------------------------------
# Ethics policy summary
# ---------------------------------------------------------------------------


class TestPolicySummary:
    """Policy summary reporting."""

    def test_summary_fields(self):
        summary = get_policy_summary(make_policy())
        assert summary["name"] == "Autopilot Ethics Policy"
        assert summary["enforcement"] == "strict"
        assert summary["num_constraints"] == 3
        assert summary["num_principles"] == 2

    def test_summary_constraints_by_principle(self):
        summary = get_policy_summary(make_policy())
        assert summary["constraints_by_principle"]["safety"] == 1
        assert summary["constraints_by_principle"]["privacy"] == 1

    def test_summary_principles_list(self):
        summary = get_policy_summary(make_policy())
        assert summary["principles"] == ["safety", "privacy"]


# ---------------------------------------------------------------------------
# Bias detection
# ---------------------------------------------------------------------------


BIASED_DATA = [
    {"selected": True, "gender": "M"},
    {"selected": True, "gender": "M"},
    {"selected": True, "gender": "M"},
    {"selected": False, "gender": "F"},
    {"selected": False, "gender": "F"},
]

FAIR_DATA = [
    {"selected": True, "gender": "M"},
    {"selected": False, "gender": "M"},
    {"selected": True, "gender": "F"},
    {"selected": False, "gender": "F"},
]


class TestBiasDetector:
    """Bias detection and reporting."""

    def test_detect_bias_returns_report(self):
        detector = BiasDetector()
        report = detector.detect_bias(BIASED_DATA, ["gender"])
        assert isinstance(report, dict)
        assert report["protected_attrs"] == ["gender"]

    def test_biased_data_detected(self):
        detector = BiasDetector()
        detector.detect_bias(BIASED_DATA, ["gender"])
        assert detector.get_bias_report()["bias_detected"] is True

    def test_fair_data_not_detected(self):
        detector = BiasDetector()
        detector.detect_bias(FAIR_DATA, ["gender"])
        assert detector.get_bias_report()["bias_detected"] is False

    def test_selection_rates_reported(self):
        detector = BiasDetector()
        report = detector.detect_bias(BIASED_DATA, ["gender"])
        assert report["groups"]["gender"]["M"]["selection_rate"] == 1.0
        assert report["groups"]["gender"]["F"]["selection_rate"] == 0.0

    def test_demographic_parity_value(self):
        detector = BiasDetector()
        report = detector.detect_bias(BIASED_DATA, ["gender"])
        assert report["metrics"]["demographic_parity"] == pytest.approx(1.0)

    def test_bias_score_fair_is_one(self):
        detector = BiasDetector()
        detector.detect_bias(FAIR_DATA, ["gender"])
        assert detector.get_bias_score() == pytest.approx(1.0)

    def test_bias_score_biased_is_lower(self):
        detector = BiasDetector()
        detector.detect_bias(BIASED_DATA, ["gender"])
        assert detector.get_bias_score() < 1.0

    def test_bias_score_before_detection_is_one(self):
        assert BiasDetector().get_bias_score() == pytest.approx(1.0)

    def test_clear_bias_data_resets(self):
        detector = BiasDetector()
        detector.detect_bias(BIASED_DATA, ["gender"])
        detector.clear_bias_data()
        assert detector.get_bias_report()["bias_detected"] is False
        assert detector.get_bias_score() == pytest.approx(1.0)

    def test_multiple_protected_attrs(self):
        data = [
            {"selected": True, "gender": "M", "age": "young"},
            {"selected": False, "gender": "F", "age": "young"},
        ]
        detector = BiasDetector()
        report = detector.detect_bias(data, ["gender", "age"])
        assert set(report["protected_attrs"]) == {"gender", "age"}
        assert "gender" in report["groups"]

    def test_equal_opportunity_metric_present_with_labels(self):
        data = [
            {"selected": True, "gender": "M", "label": True},
            {"selected": True, "gender": "M", "label": False},
            {"selected": False, "gender": "F", "label": True},
            {"selected": False, "gender": "F", "label": False},
        ]
        detector = BiasDetector()
        report = detector.detect_bias(data, ["gender"])
        assert report["metrics"]["equal_opportunity"] is not None

    def test_bias_metric_enum(self):
        assert BiasMetric.DEMOGRAPHIC_PARITY.value == "demographic_parity"
        assert BiasMetric.EQUAL_OPPORTUNITY.value == "equal_opportunity"
        assert BiasMetric.EQUALIZED_ODDS.value == "equalized_odds"
        assert len(list(BiasMetric)) == 3


# ---------------------------------------------------------------------------
# Fairness
# ---------------------------------------------------------------------------


class TestFairnessMetric:
    """Fairness metric dataclass."""

    def test_metric_fields(self):
        metric = FairnessMetric(
            name="demographic_parity", value=0.05, threshold="<= 0.1", passed=True
        )
        assert metric.name == "demographic_parity"
        assert metric.value == 0.05
        assert metric.threshold == "<= 0.1"
        assert metric.passed is True


class TestFairnessCalculation:
    """Fairness computation."""

    def test_calculate_fairness_returns_metrics(self):
        auditor = FairnessAuditor()
        metrics = auditor.calculate_fairness([1, 0, 1, 0], [1, 0, 1, 0], ["A", "A", "B", "B"])
        assert isinstance(metrics, list)
        assert all(isinstance(m, FairnessMetric) for m in metrics)

    def test_fair_predictions_all_pass(self):
        auditor = FairnessAuditor()
        metrics = auditor.calculate_fairness([1, 0, 1, 0], [1, 0, 1, 0], ["A", "A", "B", "B"])
        assert all(m.passed for m in metrics)
        assert auditor.get_fairness_score() == pytest.approx(1.0)

    def test_biased_predictions_fail_disparate_impact(self):
        auditor = FairnessAuditor()
        metrics = auditor.calculate_fairness([1, 1, 0, 0], [1, 0, 0, 0], ["A", "A", "B", "B"])
        di = next(m for m in metrics if m.name == "disparate_impact")
        assert di.passed is False

    def test_fairness_score_biased_is_lower(self):
        auditor = FairnessAuditor()
        auditor.calculate_fairness([1, 1, 0, 0], [1, 0, 0, 0], ["A", "A", "B", "B"])
        assert auditor.get_fairness_score() < 1.0

    def test_disparate_impact_value(self):
        auditor = FairnessAuditor()
        auditor.calculate_fairness([1, 1, 0, 0], [1, 0, 0, 0], ["A", "A", "B", "B"])
        assert auditor.get_disparate_impact() == pytest.approx(0.0)

    def test_fairness_report_fields(self):
        auditor = FairnessAuditor()
        auditor.calculate_fairness([1, 0, 1, 0], [1, 0, 1, 0], ["A", "A", "B", "B"])
        report = auditor.get_fairness_report()
        assert "metrics" in report
        assert "score" in report
        assert "fair" in report
        assert report["fair"] is True

    def test_equal_opportunity_metric(self):
        auditor = FairnessAuditor()
        metrics = auditor.calculate_fairness([1, 1, 0, 0], [1, 1, 0, 0], ["A", "A", "B", "B"])
        names = {m.name for m in metrics}
        assert "equal_opportunity" in names

    def test_fairness_report_before_calculation(self):
        auditor = FairnessAuditor()
        assert auditor.get_fairness_score() == pytest.approx(1.0)

    def test_module_level_fairness_api(self):
        from apex_autopilot_optimization.ethics import fairness

        fairness.calculate_fairness([1, 0, 1, 0], [1, 0, 1, 0], ["A", "A", "B", "B"])
        assert fairness.get_fairness_score() == pytest.approx(1.0)
        assert isinstance(fairness.get_fairness_report(), dict)
        assert isinstance(fairness.get_disparate_impact(), float)


# ---------------------------------------------------------------------------
# Ethics review
# ---------------------------------------------------------------------------


class TestEthicsReview:
    """Ethics review workflow."""

    def test_submit_returns_id(self):
        review = EthicsReview()
        review_id = review.submit_for_review(COMPLIANT_ACTION, {"requester": "alice"})
        assert isinstance(review_id, str)
        assert review_id

    def test_submitted_review_is_pending(self):
        review = EthicsReview()
        review_id = review.submit_for_review(COMPLIANT_ACTION, {})
        assert review.get_review_status(review_id) == "pending"

    def test_pending_decision_has_no_reviewer(self):
        review = EthicsReview()
        review_id = review.submit_for_review(COMPLIANT_ACTION, {})
        decision = review.get_review_decision(review_id)
        assert decision["status"] == "pending"
        assert decision["reviewer"] is None

    def test_approve_review(self):
        review = EthicsReview()
        review_id = review.submit_for_review(COMPLIANT_ACTION, {})
        assert review.approve_review(review_id, "bob") is True
        assert review.get_review_status(review_id) == "approved"
        assert review.get_review_decision(review_id)["reviewer"] == "bob"

    def test_reject_review(self):
        review = EthicsReview()
        review_id = review.submit_for_review(COMPLIANT_ACTION, {})
        assert review.reject_review(review_id, "bob", "unacceptable risk") is True
        assert review.get_review_status(review_id) == "rejected"
        decision = review.get_review_decision(review_id)
        assert decision["reason"] == "unacceptable risk"

    def test_get_pending_reviews(self):
        review = EthicsReview()
        first = review.submit_for_review(COMPLIANT_ACTION, {})
        second = review.submit_for_review(COMPLIANT_ACTION, {})
        review.approve_review(first, "bob")
        pending = review.get_pending_reviews()
        assert len(pending) == 1
        assert pending[0]["review_id"] == second

    def test_unknown_review_status_is_none(self):
        assert EthicsReview().get_review_status("nope") is None

    def test_approve_unknown_returns_false(self):
        assert EthicsReview().approve_review("nope", "bob") is False

    def test_reject_unknown_returns_false(self):
        assert EthicsReview().reject_review("nope", "bob", "why") is False

    def test_cannot_approve_twice(self):
        review = EthicsReview()
        review_id = review.submit_for_review(COMPLIANT_ACTION, {})
        review.approve_review(review_id, "bob")
        assert review.approve_review(review_id, "carol") is False


# ---------------------------------------------------------------------------
# Ethics config
# ---------------------------------------------------------------------------


class TestEthicsConfig:
    """Ethics configuration."""

    def test_config_defaults(self):
        config = EthicsConfig()
        assert config.enabled is True
        assert config.auto_review is True
        assert config.bias_threshold == pytest.approx(0.1)
        assert config.fairness_threshold == pytest.approx(0.8)
        assert config.require_human_approval is True

    def test_config_custom_values(self):
        config = EthicsConfig(
            enabled=False,
            auto_review=False,
            bias_threshold=0.2,
            fairness_threshold=0.9,
            require_human_approval=False,
        )
        assert config.enabled is False
        assert config.auto_review is False
        assert config.bias_threshold == pytest.approx(0.2)
        assert config.fairness_threshold == pytest.approx(0.9)
        assert config.require_human_approval is False
