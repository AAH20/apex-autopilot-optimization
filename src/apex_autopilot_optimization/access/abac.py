"""Attribute-Based Access Control (ABAC) policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ABACRule:
    """A single ABAC rule.

    Attributes:
        subject_attrs: Attributes the subject must match (subset match).
        resource_attrs: Attributes the resource must match (subset match).
        action: The action this rule applies to.
        effect: "allow" or "deny".
        conditions: Additional environment conditions that must all hold.
    """

    subject_attrs: dict[str, Any] = field(default_factory=dict)
    resource_attrs: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    effect: str = "allow"
    conditions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.effect not in ("allow", "deny"):
            raise ValueError(f"Invalid effect: {self.effect!r}")


class ABACPolicy:
    """Attribute-Based Access Control policy.

    Evaluates requests against an ordered rule list. Deny rules take
    precedence over allow rules. If no rule matches, the request is
    denied by default.
    """

    def __init__(self) -> None:
        self._rules: list[ABACRule] = []

    def evaluate(
        self,
        subject_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
        action: str,
        environment: dict[str, Any],
    ) -> bool:
        """Evaluate the policy for a request. Returns True if allowed."""
        matched_allow = False
        for rule in self._rules:
            if not self._matches(rule, subject_attrs, resource_attrs, action, environment):
                continue
            if rule.effect == "deny":
                return False
            matched_allow = True
        return matched_allow

    def add_rule(self, rule: ABACRule) -> None:
        """Add a rule to the policy."""
        if not isinstance(rule, ABACRule):
            raise ValueError(f"Invalid rule: {rule!r}")
        self._rules.append(rule)

    def remove_rule(self, rule: ABACRule) -> None:
        """Remove a rule from the policy."""
        try:
            self._rules.remove(rule)
        except ValueError:
            raise ValueError("Rule not found in policy") from None

    def get_rules(self) -> list[ABACRule]:
        """Return a copy of the rule list."""
        return list(self._rules)

    @staticmethod
    def _matches(
        rule: ABACRule,
        subject_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
        action: str,
        environment: dict[str, Any],
    ) -> bool:
        if rule.action != action:
            return False
        if not rule.subject_attrs.items() <= subject_attrs.items():
            return False
        if not rule.resource_attrs.items() <= resource_attrs.items():
            return False
        if not rule.conditions.items() <= environment.items():
            return False
        return True
