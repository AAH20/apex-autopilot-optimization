"""Configuration validator for apex-autopilot-optimization.

Validates configuration dictionaries against known rules,
providing actionable feedback for misconfigurations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class ValidationSeverity(str, Enum):
    """Severity levels for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation issue."""

    severity: ValidationSeverity
    field: str
    message: str
    suggestion: Optional[str] = None


# ── Validation Rules ────────────────────────────────────────────────────────

VALID_SCALES: Set[str] = {"startup", "smb", "mid_market", "enterprise", "large"}
VALID_PLANNERS: Set[str] = {"astar", "rrt", "prm", "hybrid_astar"}
VALID_OPTIMIZERS: Set[str] = {"minimum_snap"}
VALID_ESTIMATORS: Set[str] = {"ekf"}
VALID_SAFETY_FILTERS: Set[str] = {"cbf", "none"}
VALID_CONTROLLERS: Set[str] = {"mpc", "none"}

MODULE_RULES: Dict[str, Dict[str, Callable[[Any], bool]]] = {
    "astar": {
        "grid_size": lambda v: isinstance(v, (int, float)) and v > 0,
        "heuristic_weight": lambda v: isinstance(v, (int, float)) and v >= 0,
        "allow_diagonal": lambda v: isinstance(v, bool),
        "max_iterations": lambda v: isinstance(v, int) and v > 0,
    },
    "rrt": {
        "max_iterations": lambda v: isinstance(v, int) and v > 0,
        "step_size": lambda v: isinstance(v, (int, float)) and v > 0,
        "goal_bias": lambda v: isinstance(v, (int, float)) and 0 <= v <= 1,
        "goal_tolerance": lambda v: isinstance(v, (int, float)) and v > 0,
    },
    "prm": {
        "num_samples": lambda v: isinstance(v, int) and v > 0,
        "nearest_neighbors": lambda v: isinstance(v, int) and v > 0,
        "max_edge_length": lambda v: isinstance(v, (int, float)) and v > 0,
    },
    "hybrid_astar": {
        "grid_resolution": lambda v: isinstance(v, (int, float)) and v > 0,
        "angle_resolution": lambda v: isinstance(v, (int, float)) and v > 0,
        "max_iterations": lambda v: isinstance(v, int) and v > 0,
        "wheelbase": lambda v: isinstance(v, (int, float)) and v > 0,
    },
    "minimum_snap": {
        "num_segments": lambda v: isinstance(v, int) and v > 0,
        "time_horizon_s": lambda v: isinstance(v, (int, float)) and v > 0,
        "derivative_order": lambda v: isinstance(v, int) and v > 0,
    },
    "ekf": {
        "process_noise": lambda v: isinstance(v, (int, float)) and v >= 0,
        "measurement_noise": lambda v: isinstance(v, (int, float)) and v >= 0,
        "initial_covariance": lambda v: isinstance(v, (int, float)) and v >= 0,
    },
    "cbf": {
        "safety_margin": lambda v: isinstance(v, (int, float)) and v > 0,
        "alpha": lambda v: isinstance(v, (int, float)) and v > 0,
    },
    "mpc": {
        "horizon": lambda v: isinstance(v, int) and v > 0,
        "dt": lambda v: isinstance(v, (int, float)) and v > 0,
    },
}


class ConfigValidator:
    """Validates configuration dictionaries."""

    def __init__(self) -> None:
        self.rules: Dict[str, Dict[str, Callable[[Any], bool]]] = MODULE_RULES

    def validate(self, config: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate a configuration dictionary."""
        issues: List[ValidationIssue] = []

        # Validate scale
        if "scale" in config:
            if config["scale"] not in VALID_SCALES:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="scale",
                    message=f"Invalid scale: {config['scale']}",
                    suggestion=f"Use one of: {', '.join(sorted(VALID_SCALES))}",
                ))
        else:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field="scale",
                message="Scale not specified",
                suggestion="Set scale to one of: " + ", ".join(sorted(VALID_SCALES)),
            ))

        # Validate planner
        if "planner" in config:
            if config["planner"] not in VALID_PLANNERS:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="planner",
                    message=f"Invalid planner: {config['planner']}",
                    suggestion=f"Use one of: {', '.join(sorted(VALID_PLANNERS))}",
                ))

        # Validate optimizer
        if "optimizer" in config:
            if config["optimizer"] not in VALID_OPTIMIZERS:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="optimizer",
                    message=f"Invalid optimizer: {config['optimizer']}",
                    suggestion=f"Use one of: {', '.join(sorted(VALID_OPTIMIZERS))}",
                ))

        # Validate estimator
        if "estimator" in config:
            if config["estimator"] not in VALID_ESTIMATORS:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="estimator",
                    message=f"Invalid estimator: {config['estimator']}",
                    suggestion=f"Use one of: {', '.join(sorted(VALID_ESTIMATORS))}",
                ))

        # Validate safety_filter
        if "safety_filter" in config:
            if config["safety_filter"] not in VALID_SAFETY_FILTERS:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="safety_filter",
                    message=f"Invalid safety_filter: {config['safety_filter']}",
                    suggestion=f"Use one of: {', '.join(sorted(VALID_SAFETY_FILTERS))}",
                ))

        # Validate controller
        if "controller" in config:
            if config["controller"] not in VALID_CONTROLLERS:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="controller",
                    message=f"Invalid controller: {config['controller']}",
                    suggestion=f"Use one of: {', '.join(sorted(VALID_CONTROLLERS))}",
                ))

        # Validate max_iterations
        if "max_iterations" in config:
            if not isinstance(config["max_iterations"], int) or config["max_iterations"] <= 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="max_iterations",
                    message=f"max_iterations must be a positive integer, got {config['max_iterations']}",
                    suggestion="Set max_iterations to a positive integer (e.g., 10000)",
                ))

        # Validate log_level
        if "log_level" in config:
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            if config["log_level"] not in valid_levels:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="log_level",
                    message=f"Invalid log_level: {config['log_level']}",
                    suggestion=f"Use one of: {', '.join(sorted(valid_levels))}",
                ))

        # Warn about unknown fields
        known_fields = {
            "scale", "planner", "optimizer", "estimator", "safety_filter",
            "controller", "max_iterations", "log_level", "audit_log",
            "metrics_enabled", "distributed", "ha_enabled",
        }
        for field in config:
            if field not in known_fields:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    field=field,
                    message=f"Unknown configuration field: {field}",
                    suggestion="This field will be ignored",
                ))

        return issues


def validate_config(config: Dict[str, Any]) -> List[ValidationIssue]:
    """Validate a configuration dictionary."""
    validator = ConfigValidator()
    return validator.validate(config)


def validate_module_config(module_name: str, config: Dict[str, Any]) -> List[ValidationIssue]:
    """Validate a module-specific configuration."""
    issues: List[ValidationIssue] = []

    if module_name not in MODULE_RULES:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            field="module",
            message=f"Unknown module: {module_name}",
            suggestion=f"Use one of: {', '.join(sorted(MODULE_RULES.keys()))}",
        ))
        return issues

    rules = MODULE_RULES[module_name]
    for field, value in config.items():
        if field in rules:
            if not rules[field](value):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field=field,
                    message=f"Invalid value for {field}: {value}",
                    suggestion=f"Check the expected type and range for {field}",
                ))
        else:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field=field,
                message=f"Unknown field for {module_name}: {field}",
                suggestion=f"Known fields: {', '.join(sorted(rules.keys()))}",
            ))

    return issues
