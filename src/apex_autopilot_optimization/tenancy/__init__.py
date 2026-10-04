"""Multi-tenancy support for apex-autopilot-optimization."""

from apex_autopilot_optimization.tenancy.context import (
    TenantContext,
    clear_current_tenant,
    get_current_tenant,
    require_tenant,
    set_current_tenant,
)
from apex_autopilot_optimization.tenancy.manager import TenantManager
from apex_autopilot_optimization.tenancy.quota import QuotaManager
from apex_autopilot_optimization.tenancy.tiers import (
    TenantConfig,
    TenantTier,
    get_tier_config,
)

__all__ = [
    "QuotaManager",
    "TenantConfig",
    "TenantContext",
    "TenantManager",
    "TenantTier",
    "clear_current_tenant",
    "get_current_tenant",
    "get_tier_config",
    "require_tenant",
    "set_current_tenant",
]
