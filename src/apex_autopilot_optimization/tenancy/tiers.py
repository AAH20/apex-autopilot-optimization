"""Tenant tier definitions and configuration for apex-autopilot-optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "TenantConfig",
    "TenantTier",
    "get_tier_config",
]


class TenantTier(str, Enum):
    """Tenant tier levels."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class TenantConfig:
    """Configuration for a tenant based on their tier."""

    tier: TenantTier
    max_agents: int
    max_plans_per_hour: int
    max_storage_mb: int
    features: list[str] = field(default_factory=list)


_TIER_CONFIGS: dict[TenantTier, TenantConfig] = {
    TenantTier.FREE: TenantConfig(
        tier=TenantTier.FREE,
        max_agents=5,
        max_plans_per_hour=100,
        max_storage_mb=100,
        features=["basic_planning", "basic_optimization"],
    ),
    TenantTier.PRO: TenantConfig(
        tier=TenantTier.PRO,
        max_agents=50,
        max_plans_per_hour=1000,
        max_storage_mb=1000,
        features=[
            "basic_planning",
            "basic_optimization",
            "advanced_planning",
            "advanced_optimization",
            "priority_support",
        ],
    ),
    TenantTier.ENTERPRISE: TenantConfig(
        tier=TenantTier.ENTERPRISE,
        max_agents=500,
        max_plans_per_hour=10000,
        max_storage_mb=10000,
        features=[
            "basic_planning",
            "basic_optimization",
            "advanced_planning",
            "advanced_optimization",
            "priority_support",
            "custom_integrations",
            "dedicated_support",
            "sla_guarantee",
        ],
    ),
}


def get_tier_config(tier: TenantTier) -> TenantConfig:
    """Get the default configuration for a tenant tier.

    Args:
        tier: The tenant tier.

    Returns:
        The TenantConfig for the given tier.
    """
    return _TIER_CONFIGS[tier]
