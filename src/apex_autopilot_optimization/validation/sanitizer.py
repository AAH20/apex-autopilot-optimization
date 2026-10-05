"""Sanitization utilities for untrusted input values.

The Sanitizer class provides methods to clean individual values before they
are processed by the optimization pipeline: stripping whitespace, escaping
HTML, removing null bytes, clamping numerics, limiting collection sizes, and
detecting NaN/Inf.
"""

from __future__ import annotations

import html
import math
from typing import Any


class Sanitizer:
    """Cleans and bounds individual untrusted values."""

    @staticmethod
    def sanitize_string(value: str) -> str:
        """Strip whitespace, escape HTML entities, and remove null bytes.

        Args:
            value: The raw string to clean.

        Returns:
            The sanitized string.
        """
        if not isinstance(value, str):
            value = str(value)
        value = value.replace("\x00", "")
        value = html.escape(value)
        return value.strip()

    @staticmethod
    def sanitize_numeric(value: Any, min_val: float, max_val: float) -> float:
        """Coerce a value to float and clamp it to [min_val, max_val].

        Args:
            value: The raw numeric value (int, float, or numeric string).
            min_val: The lower bound (inclusive).
            max_val: The upper bound (inclusive).

        Returns:
            The coerced and clamped float value.
        """
        num = float(value)
        if not math.isfinite(num):
            return float(min_val)
        return float(max(min_val, min(max_val, num)))

    @staticmethod
    def sanitize_collection(value: Any, max_size: int) -> list[Any]:
        """Convert an iterable to a list, truncating to max_size elements.

        Args:
            value: The raw collection (list, tuple, set, etc.).
            max_size: Maximum number of elements to keep.

        Returns:
            A list containing at most max_size elements.
        """
        items = list(value)
        return items[:max_size]

    @staticmethod
    def validate_no_nan_inf(value: Any) -> bool:
        """Check that a value is a finite number (not NaN, Inf, or -Inf).

        Args:
            value: The value to check.

        Returns:
            True if the value is a finite number, False otherwise.
        """
        if not isinstance(value, int | float) or isinstance(value, bool):
            return False
        return math.isfinite(float(value))
