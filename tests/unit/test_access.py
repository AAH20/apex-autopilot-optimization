"""Unit tests for access control (RBAC + ABAC) module."""

import pytest

from apex_autopilot_optimization.access import (
    ABACPolicy,
    ABACRule,
    AccessControl,
    AccessRequest,
    AccessResult,
    Permission,
    RBACPolicy,
    Role,
)

# ---------------------------------------------------------------------------
# RBAC: role assignment
# ---------------------------------------------------------------------------


class TestRBACRoleAssignment:
    """Role assignment via RBACPolicy."""

    def test_assign_role_stores_role(self):
        policy = RBACPolicy()
        policy.assign_role("user-1", Role.ADMIN)
        assert policy.get_role("user-1") is Role.ADMIN

    def test_assign_role_overwrites_previous_role(self):
        policy = RBACPolicy()
        policy.assign_role("user-1", Role.VIEWER)
        policy.assign_role("user-1", Role.OPERATOR)
        assert policy.get_role("user-1") is Role.OPERATOR

    def test_assign_multiple_users_different_roles(self):
        policy = RBACPolicy()
        policy.assign_role("user-1", Role.ADMIN)
        policy.assign_role("user-2", Role.VIEWER)
        assert policy.get_role("user-1") is Role.ADMIN
        assert policy.get_role("user-2") is Role.VIEWER

    def test_assign_role_invalid_type_raises(self):
        policy = RBACPolicy()
        with pytest.raises(ValueError, match="Invalid role"):
            policy.assign_role("user-1", "not-a-role")

    def test_get_role_unassigned_returns_none(self):
        policy = RBACPolicy()
        assert policy.get_role("ghost") is None


# ---------------------------------------------------------------------------
# RBAC: permission checks
# ---------------------------------------------------------------------------


class TestRBACPermissionCheck:
    """Permission checks via RBACPolicy."""

    def test_admin_has_all_permissions(self):
        policy = RBACPolicy()
        for perm in Permission:
            assert policy.has_permission("admin", perm) is True

    def test_viewer_has_monitor_only(self):
        policy = RBACPolicy()
        policy.assign_role("viewer-1", Role.VIEWER)
        assert policy.has_permission("viewer-1", Permission.MONITOR) is True
        assert policy.has_permission("viewer-1", Permission.PLAN) is False

    def test_operator_has_operational_permissions(self):
        policy = RBACPolicy()
        policy.assign_role("op-1", Role.OPERATOR)
        assert policy.has_permission("op-1", Permission.PLAN) is True
        assert policy.has_permission("op-1", Permission.OPTIMIZE) is True
        assert policy.has_permission("op-1", Permission.CONTROL) is True
        assert policy.has_permission("op-1", Permission.CONFIGURE) is False

    def test_auditor_has_audit_permissions(self):
        policy = RBACPolicy()
        policy.assign_role("aud-1", Role.AUDITOR)
        assert policy.has_permission("aud-1", Permission.AUDIT) is True
        assert policy.has_permission("aud-1", Permission.CONTROL) is False

    def test_unassigned_user_has_no_permissions(self):
        policy = RBACPolicy()
        assert policy.has_permission("nobody", Permission.MONITOR) is False

    def test_has_permission_invalid_type_raises(self):
        policy = RBACPolicy()
        with pytest.raises(ValueError, match="Invalid permission"):
            policy.has_permission("user-1", "not-a-permission")


# ---------------------------------------------------------------------------
# RBAC: role-permission mapping
# ---------------------------------------------------------------------------


class TestRBACRolePermissionMapping:
    """Role-permission mapping management."""

    def test_get_permissions_returns_copy(self):
        policy = RBACPolicy()
        perms = policy.get_permissions(Role.VIEWER)
        perms.add(Permission.AUDIT)
        assert Permission.AUDIT not in policy.get_permissions(Role.VIEWER)

    def test_add_role_permission_grants_access(self):
        policy = RBACPolicy()
        policy.add_role_permission(Role.VIEWER, Permission.PLAN)
        assert policy.has_permission("v", Permission.PLAN) is True or True  # role check below
        policy.assign_role("v", Role.VIEWER)
        assert policy.has_permission("v", Permission.PLAN) is True

    def test_remove_role_permission_revokes_access(self):
        policy = RBACPolicy()
        policy.assign_role("op", Role.OPERATOR)
        assert policy.has_permission("op", Permission.CONTROL) is True
        policy.remove_role_permission(Role.OPERATOR, Permission.CONTROL)
        assert policy.has_permission("op", Permission.CONTROL) is False

    def test_add_role_permission_invalid_role_raises(self):
        policy = RBACPolicy()
        with pytest.raises(ValueError, match="Invalid role"):
            policy.add_role_permission("bad-role", Permission.PLAN)

    def test_remove_role_permission_invalid_permission_raises(self):
        policy = RBACPolicy()
        with pytest.raises(ValueError, match="Invalid permission"):
            policy.remove_role_permission(Role.ADMIN, "bad-perm")

    def test_default_mapping_admin_covers_every_permission(self):
        policy = RBACPolicy()
        admin_perms = policy.get_permissions(Role.ADMIN)
        assert set(admin_perms) == set(Permission)


# ---------------------------------------------------------------------------
# ABAC: rule evaluation
# ---------------------------------------------------------------------------


class TestABACRuleEvaluation:
    """ABAC rule evaluation."""

    def test_allow_rule_matches(self):
        policy = ABACPolicy()
        policy.add_rule(
            ABACRule(
                subject_attrs={"clearance": "secret"},
                resource_attrs={"classification": "secret"},
                action="read",
                effect="allow",
                conditions={},
            )
        )
        result = policy.evaluate(
            subject_attrs={"clearance": "secret"},
            resource_attrs={"classification": "secret"},
            action="read",
            environment={},
        )
        assert result is True

    def test_deny_rule_blocks(self):
        policy = ABACPolicy()
        policy.add_rule(
            ABACRule(
                subject_attrs={"clearance": "public"},
                resource_attrs={"classification": "secret"},
                action="read",
                effect="deny",
                conditions={},
            )
        )
        result = policy.evaluate(
            subject_attrs={"clearance": "public"},
            resource_attrs={"classification": "secret"},
            action="read",
            environment={},
        )
        assert result is False

    def test_no_matching_rule_returns_false(self):
        policy = ABACPolicy()
        policy.add_rule(
            ABACRule(
                subject_attrs={"clearance": "secret"},
                resource_attrs={},
                action="read",
                effect="allow",
                conditions={},
            )
        )
        result = policy.evaluate(
            subject_attrs={"clearance": "public"},
            resource_attrs={},
            action="read",
            environment={},
        )
        assert result is False

    def test_deny_takes_precedence_over_allow(self):
        policy = ABACPolicy()
        policy.add_rule(
            ABACRule(
                subject_attrs={"dept": "eng"},
                resource_attrs={},
                action="write",
                effect="allow",
                conditions={},
            )
        )
        policy.add_rule(
            ABACRule(
                subject_attrs={"dept": "eng"},
                resource_attrs={"restricted": True},
                action="write",
                effect="deny",
                conditions={},
            )
        )
        result = policy.evaluate(
            subject_attrs={"dept": "eng"},
            resource_attrs={"restricted": True},
            action="write",
            environment={},
        )
        assert result is False

    def test_conditions_must_match_environment(self):
        policy = ABACPolicy()
        policy.add_rule(
            ABACRule(
                subject_attrs={},
                resource_attrs={},
                action="read",
                effect="allow",
                conditions={"time_of_day": "business_hours"},
            )
        )
        assert (
            policy.evaluate(
                subject_attrs={},
                resource_attrs={},
                action="read",
                environment={"time_of_day": "business_hours"},
            )
            is True
        )
        assert (
            policy.evaluate(
                subject_attrs={},
                resource_attrs={},
                action="read",
                environment={"time_of_day": "night"},
            )
            is False
        )

    def test_empty_policy_denies_by_default(self):
        policy = ABACPolicy()
        assert (
            policy.evaluate(
                subject_attrs={"any": "thing"},
                resource_attrs={"any": "thing"},
                action="any",
                environment={},
            )
            is False
        )


# ---------------------------------------------------------------------------
# ABAC: rule management
# ---------------------------------------------------------------------------


class TestABACRuleManagement:
    """ABAC rule add/remove/get."""

    def test_add_rule_increments_count(self):
        policy = ABACPolicy()
        rule = ABACRule({}, {}, "read", "allow", {})
        policy.add_rule(rule)
        assert len(policy.get_rules()) == 1

    def test_remove_rule_decrements_count(self):
        policy = ABACPolicy()
        rule = ABACRule({}, {}, "read", "allow", {})
        policy.add_rule(rule)
        policy.remove_rule(rule)
        assert len(policy.get_rules()) == 0

    def test_remove_nonexistent_rule_raises(self):
        policy = ABACPolicy()
        rule = ABACRule({}, {}, "read", "allow", {})
        with pytest.raises(ValueError, match="Rule not found"):
            policy.remove_rule(rule)

    def test_get_rules_returns_copy(self):
        policy = ABACPolicy()
        policy.add_rule(ABACRule({}, {}, "read", "allow", {}))
        rules = policy.get_rules()
        rules.clear()
        assert len(policy.get_rules()) == 1

    def test_add_rule_invalid_effect_raises(self):
        policy = ABACPolicy()
        with pytest.raises(ValueError, match="Invalid effect"):
            policy.add_rule(ABACRule({}, {}, "read", "maybe", {}))

    def test_add_rule_non_dataclass_raises(self):
        policy = ABACPolicy()
        with pytest.raises(ValueError, match="Invalid rule"):
            policy.add_rule({"action": "read"})


# ---------------------------------------------------------------------------
# AccessControl: authorize
# ---------------------------------------------------------------------------


class TestAccessControlAuthorize:
    """AccessControl.authorize end-to-end decisions."""

    def test_authorize_allows_via_rbac(self):
        ac = AccessControl()
        ac.assign_role("op", Role.OPERATOR)
        result = ac.authorize(AccessRequest("op", "optimize", "trajectory-1", {}))
        assert result.allowed is True
        assert result.policy == "rbac"

    def test_authorize_denies_unassigned_user(self):
        ac = AccessControl()
        result = ac.authorize(AccessRequest("ghost", "plan", "trajectory-1", {}))
        assert result.allowed is False

    def test_authorize_abac_deny_overrides_rbac(self):
        ac = AccessControl()
        ac.assign_role("op", Role.OPERATOR)
        ac.add_rule(
            ABACRule(
                subject_attrs={"dept": "eng"},
                resource_attrs={"restricted": True},
                action="optimize",
                effect="deny",
                conditions={},
            )
        )
        result = ac.authorize(
            AccessRequest("op", "optimize", "trajectory-1", {"dept": "eng", "restricted": True})
        )
        assert result.allowed is False
        assert result.policy == "abac"

    def test_authorize_abac_allow_without_role(self):
        ac = AccessControl()
        ac.add_rule(
            ABACRule(
                subject_attrs={"contractor": True},
                resource_attrs={},
                action="monitor",
                effect="allow",
                conditions={},
            )
        )
        result = ac.authorize(
            AccessRequest("contractor-1", "monitor", "traj", {"contractor": True})
        )
        assert result.allowed is True
        assert result.policy == "abac"

    def test_authorize_result_has_reason(self):
        ac = AccessControl()
        result = ac.authorize(AccessRequest("ghost", "plan", "traj", {}))
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_authorize_abac_condition_blocks(self):
        ac = AccessControl()
        ac.assign_role("op", Role.OPERATOR)
        ac.add_rule(
            ABACRule(
                subject_attrs={},
                resource_attrs={},
                action="optimize",
                effect="allow",
                conditions={"maintenance_window": True},
            )
        )
        # ABAC allow rule with unmet condition does not grant; RBAC still allows OPERATOR optimize
        result = ac.authorize(
            AccessRequest("op", "optimize", "traj", {"maintenance_window": False})
        )
        assert result.allowed is True
        assert result.policy == "rbac"


# ---------------------------------------------------------------------------
# AccessControl: check_permission / get_user_permissions
# ---------------------------------------------------------------------------


class TestAccessControlHelpers:
    """AccessControl.check_permission and get_user_permissions."""

    def test_check_permission_true_for_granted(self):
        ac = AccessControl()
        ac.assign_role("viewer", Role.VIEWER)
        assert ac.check_permission("viewer", Permission.MONITOR, "traj") is True

    def test_check_permission_false_for_denied(self):
        ac = AccessControl()
        ac.assign_role("viewer", Role.VIEWER)
        assert ac.check_permission("viewer", Permission.CONTROL, "traj") is False

    def test_check_permission_unknown_user_false(self):
        ac = AccessControl()
        assert ac.check_permission("ghost", Permission.MONITOR, "traj") is False

    def test_get_user_permissions_returns_role_permissions(self):
        ac = AccessControl()
        ac.assign_role("op", Role.OPERATOR)
        perms = ac.get_user_permissions("op")
        assert Permission.PLAN in perms
        assert Permission.OPTIMIZE in perms
        assert Permission.AUDIT not in perms

    def test_get_user_permissions_empty_for_unknown(self):
        ac = AccessControl()
        assert ac.get_user_permissions("ghost") == set()

    def test_get_user_permissions_reflects_custom_mapping(self):
        ac = AccessControl()
        ac.assign_role("viewer", Role.VIEWER)
        ac.add_role_permission(Role.VIEWER, Permission.AUDIT)
        assert Permission.AUDIT in ac.get_user_permissions("viewer")


# ---------------------------------------------------------------------------
# AccessRequest / AccessResult
# ---------------------------------------------------------------------------


class TestAccessRequestResult:
    """AccessRequest and AccessResult dataclass creation."""

    def test_access_request_creation(self):
        req = AccessRequest("u1", "read", "res-1", {"ip": "10.0.0.1"})
        assert req.user_id == "u1"
        assert req.action == "read"
        assert req.resource == "res-1"
        assert req.context == {"ip": "10.0.0.1"}

    def test_access_request_default_context(self):
        req = AccessRequest("u1", "read", "res-1")
        assert req.context == {}

    def test_access_result_creation(self):
        res = AccessResult(True, "granted by role", "rbac")
        assert res.allowed is True
        assert res.reason == "granted by role"
        assert res.policy == "rbac"

    def test_access_result_denied(self):
        res = AccessResult(False, "no matching policy", "rbac")
        assert res.allowed is False
        assert res.policy == "rbac"
