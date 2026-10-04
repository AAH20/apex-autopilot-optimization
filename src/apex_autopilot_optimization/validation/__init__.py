"""Request validation and sanitization for apex-autopilot-optimization.

This package provides strict input validation for all public API entry points
that accept raw untrusted data. It includes a rule-based Validator, a
Sanitizer for cleaning individual values, and Pydantic schemas for structured
inputs.
"""

from apex_autopilot_optimization.validation.sanitizer import Sanitizer
from apex_autopilot_optimization.validation.validator import (
    ValidationResult,
    ValidationRule,
    Validator,
)

__all__ = [
    "Validator",
    "ValidationRule",
    "ValidationResult",
    "Sanitizer",
]
