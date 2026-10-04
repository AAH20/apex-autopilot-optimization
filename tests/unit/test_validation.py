"""Tests for the validation package: Validator, Sanitizer, and Pydantic schemas."""

import math

import pytest
from pydantic import ValidationError

from apex_autopilot_optimization.validation import (
    Sanitizer,
    ValidationResult,
    ValidationRule,
    Validator,
)
from apex_autopilot_optimization.validation.schemas import (
    ConfigInput,
    PlanningProblemInput,
    PlanningResultInput,
)


class TestValidatorValidData:
    """Validator accepts well-formed data that satisfies every rule."""

    def test_valid_data_passes(self):
        data = {"name": "alpha", "count": 5, "mode": "fast"}
        rules = [
            ValidationRule(field="name", rule_type="required", params={}),
            ValidationRule(field="count", rule_type="type", params={"expected_type": "int"}),
            ValidationRule(field="mode", rule_type="enum", params={"choices": ["fast", "slow"]}),
        ]
        result = Validator().validate(data, rules)
        assert result.valid is True
        assert result.errors == []

    def test_valid_data_populates_sanitized(self):
        data = {"name": "  alpha  ", "count": 5}
        rules = [
            ValidationRule(field="name", rule_type="required", params={}),
            ValidationRule(field="count", rule_type="type", params={"expected_type": "int"}),
        ]
        result = Validator().validate(data, rules)
        assert result.sanitized["name"] == "alpha"
        assert result.sanitized["count"] == 5

    def test_empty_rules_always_valid(self):
        result = Validator().validate({"anything": 1}, [])
        assert result.valid is True
        assert result.errors == []


class TestValidatorInvalidData:
    """Validator rejects data that violates one or more rules."""

    def test_invalid_data_fails(self):
        data = {"name": "", "count": "not-a-number"}
        rules = [
            ValidationRule(field="name", rule_type="required", params={}),
            ValidationRule(field="count", rule_type="type", params={"expected_type": "int"}),
        ]
        result = Validator().validate(data, rules)
        assert result.valid is False
        assert len(result.errors) >= 1

    def test_errors_are_descriptive_strings(self):
        data = {}
        rules = [ValidationRule(field="name", rule_type="required", params={})]
        result = Validator().validate(data, rules)
        assert result.valid is False
        assert any("name" in err for err in result.errors)

    def test_multiple_errors_collected(self):
        data = {"count": "x", "mode": "turbo"}
        rules = [
            ValidationRule(field="count", rule_type="type", params={"expected_type": "int"}),
            ValidationRule(field="mode", rule_type="enum", params={"choices": ["fast", "slow"]}),
        ]
        result = Validator().validate(data, rules)
        assert result.valid is False
        assert len(result.errors) == 2


class TestValidationRuleTypes:
    """Each rule type (required, type, range, regex, enum) is enforced."""

    def test_required_missing_field(self):
        rules = [ValidationRule(field="name", rule_type="required", params={})]
        result = Validator().validate({}, rules)
        assert result.valid is False

    def test_required_rejects_empty_string(self):
        rules = [ValidationRule(field="name", rule_type="required", params={})]
        result = Validator().validate({"name": ""}, rules)
        assert result.valid is False

    def test_required_rejects_none(self):
        rules = [ValidationRule(field="name", rule_type="required", params={})]
        result = Validator().validate({"name": None}, rules)
        assert result.valid is False

    def test_required_accepts_present_value(self):
        rules = [ValidationRule(field="name", rule_type="required", params={})]
        result = Validator().validate({"name": "x"}, rules)
        assert result.valid is True

    def test_type_int_accepts_int(self):
        rules = [ValidationRule(field="n", rule_type="type", params={"expected_type": "int"})]
        result = Validator().validate({"n": 3}, rules)
        assert result.valid is True

    def test_type_int_rejects_string(self):
        rules = [ValidationRule(field="n", rule_type="type", params={"expected_type": "int"})]
        result = Validator().validate({"n": "3"}, rules)
        assert result.valid is False

    def test_type_str_rejects_int(self):
        rules = [ValidationRule(field="s", rule_type="type", params={"expected_type": "str"})]
        result = Validator().validate({"s": 42}, rules)
        assert result.valid is False

    def test_type_float_accepts_float(self):
        rules = [ValidationRule(field="f", rule_type="type", params={"expected_type": "float"})]
        result = Validator().validate({"f": 1.5}, rules)
        assert result.valid is True

    def test_range_within_bounds(self):
        rules = [ValidationRule(field="n", rule_type="range", params={"min": 0, "max": 10})]
        result = Validator().validate({"n": 5}, rules)
        assert result.valid is True

    def test_range_below_min(self):
        rules = [ValidationRule(field="n", rule_type="range", params={"min": 0, "max": 10})]
        result = Validator().validate({"n": -1}, rules)
        assert result.valid is False

    def test_range_above_max(self):
        rules = [ValidationRule(field="n", rule_type="range", params={"min": 0, "max": 10})]
        result = Validator().validate({"n": 11}, rules)
        assert result.valid is False

    def test_regex_matching_pattern(self):
        rules = [
            ValidationRule(field="email", rule_type="regex", params={"pattern": r"^[^@]+@[^@]+\.[^@]+$"})
        ]
        result = Validator().validate({"email": "user@example.com"}, rules)
        assert result.valid is True

    def test_regex_non_matching_pattern(self):
        rules = [
            ValidationRule(field="email", rule_type="regex", params={"pattern": r"^[^@]+@[^@]+\.[^@]+$"})
        ]
        result = Validator().validate({"email": "not-an-email"}, rules)
        assert result.valid is False

    def test_enum_allowed_value(self):
        rules = [ValidationRule(field="mode", rule_type="enum", params={"choices": ["fast", "slow"]})]
        result = Validator().validate({"mode": "fast"}, rules)
        assert result.valid is True

    def test_enum_disallowed_value(self):
        rules = [ValidationRule(field="mode", rule_type="enum", params={"choices": ["fast", "slow"]})]
        result = Validator().validate({"mode": "turbo"}, rules)
        assert result.valid is False


class TestSanitizerString:
    """Sanitizer.sanitize_string strips, escapes HTML, and removes null bytes."""

    def test_strips_whitespace(self):
        assert Sanitizer.sanitize_string("  hello  ") == "hello"

    def test_escapes_html(self):
        assert Sanitizer.sanitize_string("<script>alert(1)</script>") == (
            "&lt;script&gt;alert(1)&lt;/script&gt;"
        )

    def test_removes_null_bytes(self):
        assert Sanitizer.sanitize_string("he\x00llo") == "hello"

    def test_combined_cleaning(self):
        assert Sanitizer.sanitize_string("  <b>\x00</b>  ") == "&lt;b&gt;&lt;/b&gt;"

    def test_plain_string_unchanged(self):
        assert Sanitizer.sanitize_string("clean") == "clean"


class TestSanitizerNumeric:
    """Sanitizer.sanitize_numeric coerces and clamps to bounds."""

    def test_coerces_string_to_float(self):
        assert Sanitizer.sanitize_numeric("3.5", 0.0, 10.0) == 3.5

    def test_clamps_below_min(self):
        assert Sanitizer.sanitize_numeric(-5.0, 0.0, 10.0) == 0.0

    def test_clamps_above_max(self):
        assert Sanitizer.sanitize_numeric(99.0, 0.0, 10.0) == 10.0

    def test_value_within_bounds_unchanged(self):
        assert Sanitizer.sanitize_numeric(5.0, 0.0, 10.0) == 5.0

    def test_returns_float(self):
        result = Sanitizer.sanitize_numeric(7, 0.0, 10.0)
        assert isinstance(result, float)


class TestSanitizerCollection:
    """Sanitizer.sanitize_collection converts to list and enforces max_size."""

    def test_converts_tuple_to_list(self):
        result = Sanitizer.sanitize_collection((1, 2, 3), max_size=10)
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_truncates_to_max_size(self):
        result = Sanitizer.sanitize_collection([1, 2, 3, 4, 5], max_size=3)
        assert result == [1, 2, 3]

    def test_within_limit_unchanged(self):
        result = Sanitizer.sanitize_collection([1, 2], max_size=5)
        assert result == [1, 2]

    def test_empty_collection(self):
        assert Sanitizer.sanitize_collection([], max_size=5) == []


class TestSanitizerNanInf:
    """Sanitizer.validate_no_nan_inf detects non-finite numbers."""

    def test_finite_number_passes(self):
        assert Sanitizer.validate_no_nan_inf(1.5) is True

    def test_zero_passes(self):
        assert Sanitizer.validate_no_nan_inf(0.0) is True

    def test_nan_fails(self):
        assert Sanitizer.validate_no_nan_inf(float("nan")) is False

    def test_positive_infinity_fails(self):
        assert Sanitizer.validate_no_nan_inf(float("inf")) is False

    def test_negative_infinity_fails(self):
        assert Sanitizer.validate_no_nan_inf(float("-inf")) is False

    def test_non_numeric_fails(self):
        assert Sanitizer.validate_no_nan_inf("not-a-number") is False


class TestValidationResult:
    """ValidationResult dataclass shape."""

    def test_defaults(self):
        result = ValidationResult(valid=True, errors=[], sanitized={})
        assert result.valid is True
        assert result.errors == []
        assert result.sanitized == {}


class TestPydanticSchemas:
    """Pydantic models accept well-formed input."""

    def test_planning_problem_input_valid(self):
        model = PlanningProblemInput(
            vehicle_type="uav_multirotor",
            start={"x": 0.0, "y": 0.0, "z": 0.0},
            goal={"x": 10.0, "y": 10.0, "z": 5.0},
            time_horizon_s=60.0,
            resolution_m=1.0,
        )
        assert model.vehicle_type == "uav_multirotor"
        assert model.time_horizon_s == 60.0

    def test_planning_result_input_valid(self):
        model = PlanningResultInput(
            success=True,
            computation_time_ms=12.5,
            iterations=100,
            cost=42.0,
            message="ok",
        )
        assert model.success is True
        assert model.iterations == 100

    def test_config_input_valid(self):
        model = ConfigInput(
            scale="startup",
            planner="astar",
            optimizer="minimum_snap",
            max_iterations=10000,
            log_level="INFO",
        )
        assert model.planner == "astar"
        assert model.max_iterations == 10000


class TestPydanticInvalidData:
    """Pydantic models reject malformed input."""

    def test_planning_problem_rejects_non_positive_horizon(self):
        with pytest.raises(ValidationError):
            PlanningProblemInput(
                vehicle_type="uav_multirotor",
                start={"x": 0.0, "y": 0.0, "z": 0.0},
                goal={"x": 1.0, "y": 1.0, "z": 1.0},
                time_horizon_s=-1.0,
            )

    def test_planning_problem_rejects_non_positive_resolution(self):
        with pytest.raises(ValidationError):
            PlanningProblemInput(
                vehicle_type="uav_multirotor",
                start={"x": 0.0, "y": 0.0, "z": 0.0},
                goal={"x": 1.0, "y": 1.0, "z": 1.0},
                resolution_m=0.0,
            )

    def test_planning_result_rejects_negative_iterations(self):
        with pytest.raises(ValidationError):
            PlanningResultInput(success=True, iterations=-5)

    def test_planning_result_rejects_negative_cost(self):
        with pytest.raises(ValidationError):
            PlanningResultInput(success=True, cost=-1.0)

    def test_config_rejects_invalid_scale(self):
        with pytest.raises(ValidationError):
            ConfigInput(scale="invalid-scale")

    def test_config_rejects_invalid_planner(self):
        with pytest.raises(ValidationError):
            ConfigInput(planner="invalid-planner")

    def test_config_rejects_non_positive_max_iterations(self):
        with pytest.raises(ValidationError):
            ConfigInput(max_iterations=0)

    def test_config_rejects_invalid_log_level(self):
        with pytest.raises(ValidationError):
            ConfigInput(log_level="VERBOSE")
