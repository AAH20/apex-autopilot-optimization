"""Ethical principles and policy evaluation for apex-autopilot-optimization.

This module defines the :class:`EthicsPrinciple` enumeration and the
:class:`EthicsPolicy` dataclass, plus the functions used to evaluate a proposed
action against a policy and to summarise it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast


class EthicsPrinciple(Enum):
    """Core ethical principles recognised by the framework."""

    TRANSPARENCY = "transparency"
    FAIRNESS = "fairness"
    ACCOUNTABILITY = "accountability"
    PRIVACY = "privacy"
    SAFETY = "safety"


@dataclass
class EthicsPolicy:
    """A named ethics policy with principles, constraints and enforcement.

    Attributes:
        name: Human-readable policy name.
        description: What the policy governs.
        principles: Principle identifiers (usually :class:`EthicsPrinciple`
            values) that the policy is grounded in.
        constraints: Machine-checkable constraints. Each constraint is a dict
            with ``principle``, ``field``, ``operator`` and ``value`` keys.
        enforcement: Enforcement level, e.g. ``"strict"``, ``"warn"`` or
            ``"advisory"``.
    """

    name: str
    description: str
    principles: list[str] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    enforcement: str = "strict"


def _constraint_satisfied(action: dict[str, Any], constraint: dict[str, Any]) -> bool:
    """Return True if a single constraint holds for ``action``."""
    field_name = constraint.get("field")
    if field_name not in action:
        return False

    value = action[field_name]
    operator = constraint.get("operator")
    threshold = constraint.get("value")

    if operator == "max":
        return cast(bool, value <= threshold)
    if operator == "min":
        return cast(bool, value >= threshold)
    if operator == "must_be_true":
        return value is True
    if operator == "must_be_false":
        return value is False
    if operator == "equals":
        return cast(bool, value == threshold)
    if operator == "not_equals":
        return cast(bool, value != threshold)

    # Unknown operator: treat as unsatisfied rather than silently passing.
    return False


def _describe_constraint(constraint: dict[str, Any]) -> str:
    """Build a human-readable message for a violated constraint."""
    field_name = constraint.get("field")
    operator = constraint.get("operator")
    threshold = constraint.get("value")

    if operator == "max":
        return f"Field '{field_name}' must be at most {threshold}"
    if operator == "min":
        return f"Field '{field_name}' must be at least {threshold}"
    if operator == "must_be_true":
        return f"Field '{field_name}' must be true"
    if operator == "must_be_false":
        return f"Field '{field_name}' must be false"
    if operator == "equals":
        return f"Field '{field_name}' must equal {threshold}"
    if operator == "not_equals":
        return f"Field '{field_name}' must not equal {threshold}"
    return f"Field '{field_name}' violates constraint ({operator})"


def evaluate_action(action: dict[str, Any], policy: EthicsPolicy) -> bool:
    """Evaluate ``action`` against ``policy``.

    Returns True when every constraint in the policy is satisfied. A policy
    with no constraints passes all actions.
    """
    return all(_constraint_satisfied(action, c) for c in policy.constraints)


def get_violations(action: dict[str, Any], policy: EthicsPolicy) -> list[dict[str, Any]]:
    """Return the constraints of ``policy`` that ``action`` violates."""
    violations: list[dict[str, Any]] = []
    for constraint in policy.constraints:
        if not _constraint_satisfied(action, constraint):
            violations.append(
                {
                    "principle": constraint.get("principle"),
                    "field": constraint.get("field"),
                    "message": _describe_constraint(constraint),
                    "constraint": constraint,
                }
            )
    return violations


def get_policy_summary(policy: EthicsPolicy) -> dict[str, Any]:
    """Return a structured summary of ``policy``."""
    constraints_by_principle: dict[str, int] = {}
    for constraint in policy.constraints:
        principle = constraint.get("principle", "unspecified")
        constraints_by_principle[principle] = constraints_by_principle.get(principle, 0) + 1

    return {
        "name": policy.name,
        "description": policy.description,
        "enforcement": policy.enforcement,
        "principles": list(policy.principles),
        "num_principles": len(policy.principles),
        "num_constraints": len(policy.constraints),
        "constraints_by_principle": constraints_by_principle,
    }
