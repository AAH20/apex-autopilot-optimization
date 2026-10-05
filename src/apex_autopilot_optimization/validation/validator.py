"""Rule-based validator for untrusted input data.

The Validator applies a list of ValidationRule objects to a dictionary and
returns a ValidationResult indicating whether the data is valid, any errors
encountered, and a sanitized copy of the data.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from apex_autopilot_optimization.validation.sanitizer import Sanitizer


@dataclass(frozen=True)
class ValidationRule:
    """A single validation rule to apply to a field.

    Attributes:
        field: The dictionary key this rule applies to.
        rule_type: One of "required", "type", "range", "regex", "enum".
        params: Rule-specific parameters (e.g., expected_type, min, max,
            pattern, choices).
    """

    field: str
    rule_type: str
    params: dict[str, Any] = dc_field(default_factory=lambda: {})


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating a dictionary against a set of rules.

    Attributes:
        valid: True if all rules passed.
        errors: Human-readable error messages for each failed rule.
        sanitized: A cleaned copy of the input data.
    """

    valid: bool
    errors: list[str] = dc_field(default_factory=list)
    sanitized: dict[str, Any] = dc_field(default_factory=dict)


class Validator:
    """Validates dictionaries against a list of ValidationRule objects."""

    def validate(self, data: dict[str, Any], rules: list[ValidationRule]) -> ValidationResult:
        """Validate data against the provided rules.

        Args:
            data: The raw input dictionary to validate.
            rules: The validation rules to apply.

        Returns:
            A ValidationResult with validity status, error messages, and
            sanitized data.
        """
        errors: list[str] = []
        sanitized: dict[str, Any] = {}

        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = Sanitizer.sanitize_string(value)
            else:
                sanitized[key] = value

        for rule in rules:
            value = data.get(rule.field)

            if rule.rule_type == "required":
                if value is None or (isinstance(value, str) and not value.strip()):
                    errors.append(f"Field '{rule.field}' is required")

            elif rule.rule_type == "type":
                expected = rule.params.get("expected_type", "")
                if not self._check_type(value, expected):
                    errors.append(
                        f"Field '{rule.field}' must be of type '{expected}', "
                        f"got '{type(value).__name__}'"
                    )

            elif rule.rule_type == "range":
                min_val = rule.params.get("min")
                max_val = rule.params.get("max")
                if not self._check_range(value, min_val, max_val):
                    errors.append(
                        f"Field '{rule.field}' must be between {min_val} and {max_val}, "
                        f"got {value!r}"
                    )

            elif rule.rule_type == "regex":
                pattern = rule.params.get("pattern", "")
                if not isinstance(value, str) or not re.match(pattern, value):
                    errors.append(f"Field '{rule.field}' does not match required pattern")

            elif rule.rule_type == "enum":
                choices = rule.params.get("choices", [])
                if value not in choices:
                    errors.append(f"Field '{rule.field}' must be one of {choices}, got {value!r}")

        return ValidationResult(valid=len(errors) == 0, errors=errors, sanitized=sanitized)

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        """Check that value matches the expected type name."""
        type_map: dict[str, type | tuple[type, ...]] = {
            "str": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        py_type = type_map.get(expected)
        if py_type is None:
            return True
        # bool is a subclass of int; exclude it when int is expected
        if expected == "int" and isinstance(value, bool):
            return False
        return isinstance(value, py_type)

    @staticmethod
    def _check_range(value: Any, min_val: Any, max_val: Any) -> bool:
        """Check that a numeric value falls within [min_val, max_val]."""
        if not isinstance(value, int | float) or isinstance(value, bool):
            return False
        if not math.isfinite(float(value)):
            return False
        if min_val is not None and value < min_val:
            return False
        return not (max_val is not None and value > max_val)
