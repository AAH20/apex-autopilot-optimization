"""Tenant manager for apex-autopilot-optimization."""

from __future__ import annotations

from typing import Any

from apex_autopilot_optimization.tenancy.context import TenantContext
from apex_autopilot_optimization.tenancy.tiers import TenantConfig, TenantTier, get_tier_config

__all__ = ["TenantManager"]


class TenantManager:
    """Manages tenant lifecycle: creation, retrieval, update, deletion."""

    def __init__(self) -> None:
        self._tenants: dict[str, TenantContext] = {}
        self._configs: dict[str, TenantConfig] = {}

    def create_tenant(
        self,
        id: str,
        tier: str,
        config: TenantConfig | None = None,
    ) -> TenantContext:
        """Create a new tenant.

        Args:
            id: Unique tenant identifier.
            tier: Tenant tier (free, pro, enterprise).
            config: Optional custom config. Uses tier default if not provided.

        Returns:
            The created TenantContext.
        """
        tenant = TenantContext(tenant_id=id, tier=tier)
        self._tenants[id] = tenant
        if config is not None:
            self._configs[id] = config
        else:
            self._configs[id] = get_tier_config(TenantTier(tier))
        return tenant

    def get_tenant(self, id: str) -> TenantContext | None:
        """Get a tenant by ID.

        Args:
            id: The tenant identifier.

        Returns:
            The TenantContext or None if not found.
        """
        return self._tenants.get(id)

    def update_tenant(self, id: str, **kwargs: Any) -> TenantContext:
        """Update a tenant's attributes.

        Args:
            id: The tenant identifier.
            **kwargs: Attributes to update.

        Returns:
            The updated TenantContext.

        Raises:
            KeyError: If the tenant does not exist.
        """
        if id not in self._tenants:
            raise KeyError(f"Tenant '{id}' not found")
        tenant = self._tenants[id]
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        return tenant

    def delete_tenant(self, id: str) -> None:
        """Delete a tenant.

        Args:
            id: The tenant identifier.

        Raises:
            KeyError: If the tenant does not exist.
        """
        if id not in self._tenants:
            raise KeyError(f"Tenant '{id}' not found")
        del self._tenants[id]
        if id in self._configs:
            del self._configs[id]

    def list_tenants(self) -> list[TenantContext]:
        """List all tenants.

        Returns:
            List of all TenantContext objects.
        """
        return list(self._tenants.values())

    def get_tenant_config(self, id: str) -> TenantConfig | None:
        """Get the configuration for a tenant.

        Args:
            id: The tenant identifier.

        Returns:
            The TenantConfig or None if not found.
        """
        return self._configs.get(id)

    def set_tenant_config(self, id: str, config: TenantConfig) -> None:
        """Set the configuration for a tenant.

        Args:
            id: The tenant identifier.
            config: The new TenantConfig.

        Raises:
            KeyError: If the tenant does not exist.
        """
        if id not in self._tenants:
            raise KeyError(f"Tenant '{id}' not found")
        self._configs[id] = config
