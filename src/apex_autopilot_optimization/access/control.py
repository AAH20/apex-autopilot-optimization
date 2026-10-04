"""Unified access control combining RBAC and ABAC policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apex_autopilot_optimization.access.abac import ABACPolicy, ABACRule
from apex_autopilot_optimization.access.rbac import Permission, RBACPolicy, Role


@dataclass
class AccessRequest:
    """An access request from a subject to perform an action on a resource."""

    user_id: str
    action: str
    resource: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessResult:
    """The outcome of an access control decision."""

    allowed: bool
    reason: str
    policy: str


class AccessControl:
    """Unified access control.

    Combines an RBAC policy (role-based permissions) with an ABAC
    policy (attribute-based rules). Decision order:

    1. ABAC deny rules take precedence — any matching deny rule
       rejects the request.
    2. ABAC allow rules grant access even without an assigned role.
    3. RBAC grants access when the user's role has the permission
       matching the request action.
    4. Otherwise the request is denied.
    """

    def __init__(
        self,
        rbac_policy: RBACPolicy | None = None,
        abac_policy: ABACPolicy | None = None,
    ) -> None:
        self._rbac = rbac_policy or RBACPolicy()
        self._abac = abac_policy or ABACPolicy()

    @property
    def rbac(self) -> RBACPolicy:
        """The underlying RBAC policy."""
        return self._rbac

    @property
    def abac(self) -> ABACPolicy:
        """The underlying ABAC policy."""
        return self._abac

    # -- RBAC passthrough helpers -------------------------------------------

    def assign_role(self, user_id: str, role: Role) -> None:
        """Assign a role to a user."""
        self._rbac.assign_role(user_id, role)

    def add_role_permission(self, role: Role, permission: Permission) -> None:
        """Grant an additional permission to a role."""
        self._rbac.add_role_permission(role, permission)

    # -- ABAC passthrough helpers -------------------------------------------

    def add_rule(self, rule: ABACRule) -> None:
        """Add an ABAC rule."""
        self._abac.add_rule(rule)

    def remove_rule(self, rule: ABACRule) -> None:
        """Remove an ABAC rule."""
        self._abac.remove_rule(rule)

    # -- Decision entry points ----------------------------------------------

    def authorize(self, request: AccessRequest) -> AccessResult:
        """Make an access control decision for a request."""
        # 1. ABAC deny rules take precedence.
        if self._abac_deny_matches(request):
            return AccessResult(
                allowed=False,
                reason="Denied by ABAC policy",
                policy="abac",
            )

        # 2. ABAC allow rules grant access.
        if self._abac_allow_matches(request):
            return AccessResult(
                allowed=True,
                reason="Allowed by ABAC policy",
                policy="abac",
            )

        # 3. RBAC role-based permission check.
        permission = self._action_to_permission(request.action)
        if permission is not None and self._rbac.has_permission(request.user_id, permission):
            return AccessResult(
                allowed=True,
                reason="Allowed by RBAC policy",
                policy="rbac",
            )

        # 4. Default deny.
        return AccessResult(
            allowed=False,
            reason="No matching policy grants access",
            policy="rbac",
        )

    def check_permission(self, user_id: str, permission: Permission, resource: str) -> bool:
        """Check whether a user has a permission on a resource."""
        return self._rbac.has_permission(user_id, permission)

    def get_user_permissions(self, user_id: str) -> set[Permission]:
        """Return the permissions granted to a user via their role."""
        role = self._rbac.get_role(user_id)
        if role is None:
            return set()
        return self._rbac.get_permissions(role)

    # -- Internals ------------------------------------------------------------

    def _abac_deny_matches(self, request: AccessRequest) -> bool:
        for rule in self._abac.get_rules():
            if rule.effect != "deny":
                continue
            resource_attrs = {"resource": request.resource, **request.context}
            if self._abac._matches(
                rule,
                request.context,
                resource_attrs,
                request.action,
                request.context,
            ):
                return True
        return False

    def _abac_allow_matches(self, request: AccessRequest) -> bool:
        for rule in self._abac.get_rules():
            if rule.effect != "allow":
                continue
            resource_attrs = {"resource": request.resource, **request.context}
            if self._abac._matches(
                rule,
                request.context,
                resource_attrs,
                request.action,
                request.context,
            ):
                return True
        return False

    @staticmethod
    def _action_to_permission(action: str) -> Permission | None:
        """Map an action string to a Permission, if one exists."""
        try:
            return Permission(action)
        except ValueError:
            return None
