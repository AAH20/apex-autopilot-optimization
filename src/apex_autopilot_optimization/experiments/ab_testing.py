"""A/B testing module for apex-autopilot-optimization."""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field

from scipy import stats


@dataclass
class ABTestConfig:
    """Configuration for an A/B test."""

    name: str
    variants: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)


def assign_variant(config: ABTestConfig, user_id: str) -> str:
    """Assign a variant to a user based on weighted random selection.

    Uses a hash of user_id for deterministic assignment.
    """
    if not config.variants:
        raise ValueError("ABTestConfig must have at least one variant")
    if len(config.variants) != len(config.weights):
        raise ValueError("variants and weights must have the same length")

    # Normalize weights
    total = sum(config.weights)
    if total <= 0:
        raise ValueError("Sum of weights must be positive")
    normalized = [w / total for w in config.weights]

    # Hash user_id to get a stable value between 0 and 1
    hash_val = int(hashlib.md5(f"{config.name}:{user_id}".encode()).hexdigest(), 16)
    bucket = (hash_val % 10000) / 10000.0

    # Select variant based on cumulative weights
    cumulative = 0.0
    for variant, weight in zip(config.variants, normalized):
        cumulative += weight
        if bucket < cumulative:
            return variant
    # Fallback to last variant (shouldn't reach here with proper weights)
    return config.variants[-1]


def is_statistically_significant(
    results_a: list[float],
    results_b: list[float],
    confidence_level: float = 0.95,
) -> bool:
    """Check if the difference between two result sets is statistically significant.

    Uses Welch's t-test (unequal variances).
    Returns True if p-value < (1 - confidence_level).
    """
    if not results_a or not results_b:
        return False
    if len(results_a) < 2 or len(results_b) < 2:
        return False

    # Check for zero variance in both groups — if both are constant and equal, not significant
    if statistics.stdev(results_a) == 0 and statistics.stdev(results_b) == 0:
        return results_a[0] != results_b[0]

    try:
        t_stat, p_value = stats.ttest_ind(results_a, results_b, equal_var=False)
        alpha = 1.0 - confidence_level
        return bool(p_value < alpha)
    except Exception:
        return False
