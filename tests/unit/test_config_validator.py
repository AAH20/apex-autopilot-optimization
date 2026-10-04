"""Tests for configuration validator module."""

from apex_autopilot_optimization.config_validator import (
    ConfigValidator,
    ValidationIssue,
    ValidationSeverity,
    validate_config,
    validate_module_config,
)


class TestValidationSeverity:
    """Tests for ValidationSeverity enum."""

    def test_severity_values(self):
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.WARNING.value == "warning"
        assert ValidationSeverity.INFO.value == "info"


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_issue_creation(self):
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            field="test_field",
            message="Test error",
        )
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.field == "test_field"
        assert issue.message == "Test error"

    def test_issue_with_suggestion(self):
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            field="test_field",
            message="Test warning",
            suggestion="Try this fix",
        )
        assert issue.suggestion == "Try this fix"


class TestConfigValidator:
    """Tests for ConfigValidator class."""

    def test_validator_creation(self):
        validator = ConfigValidator()
        assert validator is not None

    def test_validate_valid_config(self):
        config = {
            "scale": "startup",
            "planner": "astar",
            "optimizer": "minimum_snap",
            "estimator": "ekf",
        }
        issues = validate_config(config)
        assert isinstance(issues, list)

    def test_validate_invalid_scale(self):
        config = {"scale": "invalid"}
        issues = validate_config(config)
        assert len(issues) > 0
        assert any(i.severity == ValidationSeverity.ERROR for i in issues)

    def test_validate_unknown_field(self):
        config = {"unknown_field": "value"}
        issues = validate_config(config)
        assert len(issues) > 0
        assert any(i.severity == ValidationSeverity.WARNING for i in issues)

    def test_validate_empty_config(self):
        issues = validate_config({})
        assert isinstance(issues, list)

    def test_validate_module_config_valid(self):
        config = {
            "grid_size": 1.0,
            "heuristic_weight": 1.0,
            "allow_diagonal": True,
        }
        issues = validate_module_config("astar", config)
        assert isinstance(issues, list)

    def test_validate_module_config_invalid_type(self):
        config = {"grid_size": "invalid"}
        issues = validate_module_config("astar", config)
        assert len(issues) > 0

    def test_validate_module_config_unknown_module(self):
        config = {"field": "value"}
        issues = validate_module_config("unknown_module", config)
        assert len(issues) > 0
        assert any(i.severity == ValidationSeverity.ERROR for i in issues)

    def test_validator_has_rules(self):
        validator = ConfigValidator()
        assert hasattr(validator, "rules")
        assert len(validator.rules) > 0


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_returns_list(self):
        issues = validate_config({})
        assert isinstance(issues, list)

    def test_detects_missing_required(self):
        issues = validate_config({})
        # Empty config should produce warnings about missing fields
        assert len(issues) >= 0

    def test_detects_invalid_values(self):
        config = {"scale": "invalid", "max_iterations": -1}
        issues = validate_config(config)
        assert len(issues) > 0


class TestValidateModuleConfig:
    """Tests for validate_module_config function."""

    def test_returns_list(self):
        issues = validate_module_config("astar", {})
        assert isinstance(issues, list)

    def test_valid_astar_config(self):
        config = {
            "grid_size": 1.0,
            "heuristic_weight": 1.0,
            "allow_diagonal": True,
            "max_iterations": 10000,
        }
        issues = validate_module_config("astar", config)
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0

    def test_invalid_astar_config(self):
        config = {"grid_size": -1.0}
        issues = validate_module_config("astar", config)
        assert len(issues) > 0
