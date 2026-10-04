"""Tests for the tenancy module."""

import pytest

from apex_autopilot_optimization.tenancy import (
    QuotaManager,
    TenantConfig,
    TenantContext,
    TenantManager,
    TenantTier,
    clear_current_tenant,
    get_current_tenant,
    get_tier_config,
    require_tenant,
    set_current_tenant,
)


# ---------------------------------------------------------------------------
# TenantContext tests
# ---------------------------------------------------------------------------


class TestTenantContext:
    """Tests for TenantContext dataclass."""

    def test_context_creation(self):
        ctx = TenantContext(tenant_id="t1", tier="free", metadata={"key": "val"})
        assert ctx.tenant_id == "t1"
        assert ctx.tier == "free"
        assert ctx.metadata == {"key": "val"}

    def test_context_default_metadata(self):
        ctx = TenantContext(tenant_id="t1", tier="pro")
        assert ctx.metadata == {}

    def test_context_equality(self):
        ctx1 = TenantContext(tenant_id="t1", tier="free")
        ctx2 = TenantContext(tenant_id="t1", tier="free")
        assert ctx1 == ctx2


class TestTenantContextManager:
    """Tests for get/set/clear current tenant."""

    def setup_method(self):
        clear_current_tenant()

    def teardown_method(self):
        clear_current_tenant()

    def test_get_current_tenant_default(self):
        assert get_current_tenant() is None

    def test_set_and_get_current_tenant(self):
        ctx = TenantContext(tenant_id="t1", tier="free")
        set_current_tenant(ctx)
        assert get_current_tenant() == ctx

    def test_clear_current_tenant(self):
        ctx = TenantContext(tenant_id="t1", tier="free")
        set_current_tenant(ctx)
        clear_current_tenant()
        assert get_current_tenant() is None

    def test_set_tenant_overwrites(self):
        ctx1 = TenantContext(tenant_id="t1", tier="free")
        ctx2 = TenantContext(tenant_id="t2", tier="pro")
        set_current_tenant(ctx1)
        set_current_tenant(ctx2)
        assert get_current_tenant() == ctx2


class TestRequireTenantDecorator:
    """Tests for require_tenant decorator."""

    def setup_method(self):
        clear_current_tenant()

    def teardown_method(self):
        clear_current_tenant()

    def test_require_tenant_passes_when_set(self):
        @require_tenant
        def my_func(ctx):
            return "ok"

        set_current_tenant(TenantContext(tenant_id="t1", tier="free"))
        assert my_func() == "ok"

    def test_require_tenant_raises_when_not_set(self):
        @require_tenant
        def my_func():
            return "ok"

        with pytest.raises(RuntimeError, match="No tenant context"):
            my_func()

    def test_require_tenant_passes_context_to_function(self):
        @require_tenant
        def my_func(ctx):
            return ctx.tenant_id

        set_current_tenant(TenantContext(tenant_id="t1", tier="free"))
        assert my_func() == "t1"


# ---------------------------------------------------------------------------
# TenantManager tests
# ---------------------------------------------------------------------------


class TestTenantManager:
    """Tests for TenantManager CRUD operations."""

    def setup_method(self):
        self.mgr = TenantManager()

    def test_create_tenant(self):
        tenant = self.mgr.create_tenant("t1", "free")
        assert tenant.tenant_id == "t1"
        assert tenant.tier == "free"

    def test_create_tenant_with_config(self):
        config = TenantConfig(
            tier=TenantTier.FREE,
            max_agents=5,
            max_plans_per_hour=100,
            max_storage_mb=100,
            features=["basic"],
        )
        tenant = self.mgr.create_tenant("t1", "free", config=config)
        assert tenant.tenant_id == "t1"

    def test_get_tenant(self):
        self.mgr.create_tenant("t1", "free")
        tenant = self.mgr.get_tenant("t1")
        assert tenant is not None
        assert tenant.tenant_id == "t1"

    def test_get_tenant_not_found(self):
        assert self.mgr.get_tenant("nonexistent") is None

    def test_update_tenant(self):
        self.mgr.create_tenant("t1", "free")
        updated = self.mgr.update_tenant("t1", tier="pro")
        assert updated.tier == "pro"
        assert self.mgr.get_tenant("t1").tier == "pro"

    def test_update_tenant_not_found(self):
        with pytest.raises(KeyError):
            self.mgr.update_tenant("nonexistent", tier="pro")

    def test_delete_tenant(self):
        self.mgr.create_tenant("t1", "free")
        self.mgr.delete_tenant("t1")
        assert self.mgr.get_tenant("t1") is None

    def test_delete_tenant_not_found(self):
        with pytest.raises(KeyError):
            self.mgr.delete_tenant("nonexistent")

    def test_list_tenants(self):
        self.mgr.create_tenant("t1", "free")
        self.mgr.create_tenant("t2", "pro")
        tenants = self.mgr.list_tenants()
        assert len(tenants) == 2
        ids = {t.tenant_id for t in tenants}
        assert ids == {"t1", "t2"}

    def test_list_tenants_empty(self):
        assert self.mgr.list_tenants() == []

    def test_get_tenant_config(self):
        config = TenantConfig(
            tier=TenantTier.FREE,
            max_agents=5,
            max_plans_per_hour=100,
            max_storage_mb=100,
            features=["basic"],
        )
        self.mgr.create_tenant("t1", "free", config=config)
        retrieved = self.mgr.get_tenant_config("t1")
        assert retrieved is not None
        assert retrieved.tier == TenantTier.FREE
        assert retrieved.max_agents == 5

    def test_get_tenant_config_default(self):
        self.mgr.create_tenant("t1", "free")
        config = self.mgr.get_tenant_config("t1")
        assert config is not None
        assert config.tier == TenantTier.FREE

    def test_set_tenant_config(self):
        self.mgr.create_tenant("t1", "free")
        new_config = TenantConfig(
            tier=TenantTier.PRO,
            max_agents=50,
            max_plans_per_hour=1000,
            max_storage_mb=1000,
            features=["basic", "advanced"],
        )
        self.mgr.set_tenant_config("t1", new_config)
        retrieved = self.mgr.get_tenant_config("t1")
        assert retrieved.tier == TenantTier.PRO
        assert retrieved.max_agents == 50

    def test_set_tenant_config_not_found(self):
        config = TenantConfig(
            tier=TenantTier.FREE,
            max_agents=5,
            max_plans_per_hour=100,
            max_storage_mb=100,
            features=["basic"],
        )
        with pytest.raises(KeyError):
            self.mgr.set_tenant_config("nonexistent", config)


# ---------------------------------------------------------------------------
# QuotaManager tests
# ---------------------------------------------------------------------------


class TestQuotaManager:
    """Tests for QuotaManager."""

    def setup_method(self):
        self.qm = QuotaManager()

    def test_set_quota(self):
        self.qm.set_quota("t1", "agents", 10)
        assert self.qm.get_usage("t1", "agents") == 0

    def test_check_quota_within_limit(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.increment_usage("t1", "agents", 5)
        assert self.qm.check_quota("t1", "agents") is True

    def test_check_quota_exceeds_limit(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.increment_usage("t1", "agents", 15)
        assert self.qm.check_quota("t1", "agents") is False

    def test_increment_usage(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.increment_usage("t1", "agents", 3)
        assert self.qm.get_usage("t1", "agents") == 3

    def test_increment_usage_default_amount(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.increment_usage("t1", "agents")
        assert self.qm.get_usage("t1", "agents") == 1

    def test_get_usage_no_quota(self):
        assert self.qm.get_usage("t1", "agents") == 0

    def test_reset_usage(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.increment_usage("t1", "agents", 5)
        self.qm.reset_usage("t1", "agents")
        assert self.qm.get_usage("t1", "agents") == 0

    def test_is_quota_exceeded_false(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.increment_usage("t1", "agents", 5)
        assert self.qm.is_quota_exceeded("t1", "agents") is False

    def test_is_quota_exceeded_true(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.increment_usage("t1", "agents", 15)
        assert self.qm.is_quota_exceeded("t1", "agents") is True

    def test_is_quota_exceeded_no_quota(self):
        assert self.qm.is_quota_exceeded("t1", "agents") is False

    def test_multiple_resources(self):
        self.qm.set_quota("t1", "agents", 10)
        self.qm.set_quota("t1", "storage", 100)
        self.qm.increment_usage("t1", "agents", 3)
        self.qm.increment_usage("t1", "storage", 50)
        assert self.qm.get_usage("t1", "agents") == 3
        assert self.qm.get_usage("t1", "storage") == 50


# ---------------------------------------------------------------------------
# TenantTier and TenantConfig tests
# ---------------------------------------------------------------------------


class TestTenantTier:
    """Tests for TenantTier enum."""

    def test_tier_values(self):
        assert TenantTier.FREE.value == "free"
        assert TenantTier.PRO.value == "pro"
        assert TenantTier.ENTERPRISE.value == "enterprise"

    def test_tier_count(self):
        assert len(TenantTier) == 3


class TestTenantConfig:
    """Tests for TenantConfig dataclass."""

    def test_config_creation(self):
        config = TenantConfig(
            tier=TenantTier.FREE,
            max_agents=5,
            max_plans_per_hour=100,
            max_storage_mb=100,
            features=["basic"],
        )
        assert config.tier == TenantTier.FREE
        assert config.max_agents == 5
        assert config.max_plans_per_hour == 100
        assert config.max_storage_mb == 100
        assert config.features == ["basic"]

    def test_config_default_features(self):
        config = TenantConfig(
            tier=TenantTier.FREE,
            max_agents=5,
            max_plans_per_hour=100,
            max_storage_mb=100,
        )
        assert config.features == []


class TestGetTierConfig:
    """Tests for get_tier_config function."""

    def test_get_free_tier_config(self):
        config = get_tier_config(TenantTier.FREE)
        assert config.tier == TenantTier.FREE
        assert config.max_agents > 0

    def test_get_pro_tier_config(self):
        config = get_tier_config(TenantTier.PRO)
        assert config.tier == TenantTier.PRO
        assert config.max_agents > 0

    def test_get_enterprise_tier_config(self):
        config = get_tier_config(TenantTier.ENTERPRISE)
        assert config.tier == TenantTier.ENTERPRISE
        assert config.max_agents > 0

    def test_tier_hierarchy(self):
        free = get_tier_config(TenantTier.FREE)
        pro = get_tier_config(TenantTier.PRO)
        enterprise = get_tier_config(TenantTier.ENTERPRISE)
        assert free.max_agents < pro.max_agents < enterprise.max_agents

    def test_tier_features_differ(self):
        free = get_tier_config(TenantTier.FREE)
        pro = get_tier_config(TenantTier.PRO)
        enterprise = get_tier_config(TenantTier.ENTERPRISE)
        assert set(free.features) < set(pro.features) < set(enterprise.features)


# ---------------------------------------------------------------------------
# Tenant isolation tests
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Tests that different tenants see different data."""

    def test_quota_isolation(self):
        qm = QuotaManager()
        qm.set_quota("t1", "agents", 10)
        qm.set_quota("t2", "agents", 20)
        qm.increment_usage("t1", "agents", 5)
        qm.increment_usage("t2", "agents", 15)
        assert qm.get_usage("t1", "agents") == 5
        assert qm.get_usage("t2", "agents") == 15
        assert qm.is_quota_exceeded("t1", "agents") is False
        assert qm.is_quota_exceeded("t2", "agents") is False

    def test_quota_exceeded_isolation(self):
        qm = QuotaManager()
        qm.set_quota("t1", "agents", 10)
        qm.set_quota("t2", "agents", 20)
        qm.increment_usage("t1", "agents", 15)
        qm.increment_usage("t2", "agents", 5)
        assert qm.is_quota_exceeded("t1", "agents") is True
        assert qm.is_quota_exceeded("t2", "agents") is False

    def test_tenant_config_isolation(self):
        mgr = TenantManager()
        mgr.create_tenant("t1", "free")
        mgr.create_tenant("t2", "pro")
        config1 = mgr.get_tenant_config("t1")
        config2 = mgr.get_tenant_config("t2")
        assert config1.tier == TenantTier.FREE
        assert config2.tier == TenantTier.PRO
        assert config1.max_agents != config2.max_agents

    def test_tenant_context_isolation(self):
        ctx1 = TenantContext(tenant_id="t1", tier="free")
        ctx2 = TenantContext(tenant_id="t2", tier="pro")
        set_current_tenant(ctx1)
        assert get_current_tenant().tenant_id == "t1"
        set_current_tenant(ctx2)
        assert get_current_tenant().tenant_id == "t2"
        clear_current_tenant()
