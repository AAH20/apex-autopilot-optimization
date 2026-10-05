"""Role-Based Access Control (RBAC) policy."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """User roles in the access control system."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class Permission(StrEnum):
    """Permissions that can be granted to roles."""

    PLAN = "plan"
    OPTIMIZE = "optimize"
    CONTROL = "control"
    CONFIGURE = "configure"
    MONITOR = "monitor"
    AUDIT = "audit"


# Default role-permission mapping.
DEFAULT_ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        Permission.PLAN,
        Permission.OPTIMIZE,
        Permission.CONTROL,
        Permission.CONFIGURE,
        Permission.MONITOR,
        Permission.AUDIT,
    },
    Role.OPERATOR: {
        Permission.PLAN,
        Permission.OPTIMIZE,
        Permission.CONTROL,
        Permission.MONITOR,
    },
    Role.VIEWER: {
        Permission.MONITOR,
    },
    Role.AUDITOR: {
        Permission.AUDIT,
        Permission.MONITOR,
    },
}


class RBACPolicy:
    """Role-Based Access Control policy.

    Maps users to roles and roles to permission sets. Supports custom
    role-permission overrides on top of the defaults.
    """

    def __init__(self) -> None:
        self._user_roles: dict[str, Role] = {}
        self._role_permissions: dict[Role, set[Permission]] = {
            role: set(perms) for role, perms in DEFAULT_ROLE_PERMISSIONS.items()
        }

    def assign_role(self, user_id: str, role: Role) -> None:
        """Assign a role to a user, replacing any previous role."""
        if not isinstance(role, Role):
            raise ValueError(f"Invalid role: {role!r}")
        self._user_roles[user_id] = role

    def get_role(self, user_id: str) -> Role | None:
        """Return the role assigned to a user, or None if unassigned."""
        return self._user_roles.get(user_id)

    def has_permission(self, user_id: str, permission: Permission) -> bool:
        """Check whether a user's role grants the given permission."""
        if not isinstance(permission, Permission):
            raise ValueError(f"Invalid permission: {permission!r}")
        # Also accept a role name directly (e.g. "admin" -> Role.ADMIN)
        try:
            role_from_name = Role(user_id)
            return permission in self._role_permissions.get(role_from_name, set())
        except ValueError:
            pass
        user_role = self._user_roles.get(user_id)
        if user_role is None:
            return False
        return permission in self._role_permissions.get(user_role, set())

    def get_permissions(self, role: Role) -> set[Permission]:
        """Return the permission set for a role (a copy)."""
        return set(self._role_permissions.get(role, set()))

    def add_role_permission(self, role: Role, permission: Permission) -> None:
        """Grant an additional permission to a role."""
        if not isinstance(role, Role):
            raise ValueError(f"Invalid role: {role!r}")
        if not isinstance(permission, Permission):
            raise ValueError(f"Invalid permission: {permission!r}")
        self._role_permissions.setdefault(role, set()).add(permission)

    def remove_role_permission(self, role: Role, permission: Permission) -> None:
        """Revoke a permission from a role."""
        if not isinstance(role, Role):
            raise ValueError(f"Invalid role: {role!r}")
        if not isinstance(permission, Permission):
            raise ValueError(f"Invalid permission: {permission!r}")
        self._role_permissions.get(role, set()).discard(permission)
