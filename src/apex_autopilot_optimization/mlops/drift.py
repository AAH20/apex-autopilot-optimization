"""Data drift detection for the MLOps layer.

:class:`DriftDetector` compares a reference (training-time) sample against a
current (production) sample and reports a normalized drift score. The score is
the absolute mean shift between the two samples, expressed in units of the
reference standard deviation, so it is scale-free and directly comparable to a
configurable threshold.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

_EPSILON = 1e-9


class DriftDetector:
    """Detect distribution drift between reference and current data.

    Args:
        threshold: Drift score at or above which drift is reported.
    """

    def __init__(self, threshold: float = 0.1) -> None:
        if threshold < 0:
            raise ValueError("threshold must be non-negative")
        self._threshold = float(threshold)
        self._drift_score = 0.0
        self._drift_detected = False
        self._report: dict[str, Any] = self._empty_report()

    # ── configuration ────────────────────────────────────────────────────────

    def set_threshold(self, threshold: float) -> None:
        """Update the drift threshold and re-evaluate the last comparison.

        Raises:
            ValueError: If ``threshold`` is negative.
        """
        if threshold < 0:
            raise ValueError("threshold must be non-negative")
        self._threshold = float(threshold)
        self._drift_detected = self._drift_score >= self._threshold
        self._report["threshold"] = self._threshold
        self._report["drift_detected"] = self._drift_detected

    # ── detection ────────────────────────────────────────────────────────────

    def detect_drift(
        self,
        reference_data: Sequence[float],
        current_data: Sequence[float],
    ) -> dict[str, Any]:
        """Compare ``reference_data`` against ``current_data``.

        Returns:
            A report dict describing the comparison.

        Raises:
            ValueError: If either sample is empty.
        """
        reference = np.asarray(reference_data, dtype=float)
        current = np.asarray(current_data, dtype=float)
        if reference.size == 0 or current.size == 0:
            raise ValueError("reference_data and current_data must be non-empty")

        ref_mean = float(np.mean(reference))
        cur_mean = float(np.mean(current))
        ref_std = float(np.std(reference))

        self._drift_score = abs(cur_mean - ref_mean) / (ref_std + _EPSILON)
        self._drift_detected = self._drift_score >= self._threshold
        self._report = {
            "drift_score": self._drift_score,
            "threshold": self._threshold,
            "drift_detected": self._drift_detected,
            "reference_mean": ref_mean,
            "current_mean": cur_mean,
            "reference_std": ref_std,
            "n_reference": int(reference.size),
            "n_current": int(current.size),
        }
        return self._report

    def get_drift_score(self) -> float:
        """Return the most recent drift score (``0.0`` if none computed)."""
        return self._drift_score

    def get_drift_report(self) -> dict[str, Any]:
        """Return the most recent drift report."""
        return dict(self._report)

    def is_drift_detected(self) -> bool:
        """Return whether the last comparison exceeded the threshold."""
        return self._drift_detected

    def _empty_report(self) -> dict[str, Any]:
        return {
            "drift_score": 0.0,
            "threshold": self._threshold,
            "drift_detected": False,
        }
