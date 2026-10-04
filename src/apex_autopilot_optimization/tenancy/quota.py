"""Quota management for apex-autopilot-optimization."""

from __future__ import annotations

__all__ = ["QuotaManager"]


class QuotaManager:
    """Manages resource quotas and usage tracking per tenant."""

    def __init__(self) -> None:
        self._quotas: dict[str, dict[str, int]] = {}
        self._usage: dict[str, dict[str, int]] = {}

    def set_quota(self, tenant_id: str, resource: str, limit: int) -> None:
        """Set a quota limit for a tenant's resource.

        Args:
            tenant_id: The tenant identifier.
            resource: The resource name.
            limit: The maximum allowed usage.
        """
        if tenant_id not in self._quotas:
            self._quotas[tenant_id] = {}
            self._usage[tenant_id] = {}
        self._quotas[tenant_id][resource] = limit
        self._usage[tenant_id][resource] = 0

    def check_quota(self, tenant_id: str, resource: str) -> bool:
        """Check if a tenant's resource usage is within quota.

        Args:
            tenant_id: The tenant identifier.
            resource: The resource name.

        Returns:
            True if usage is within quota, False otherwise.
        """
        if tenant_id not in self._quotas or resource not in self._quotas[tenant_id]:
            return True
        limit = self._quotas[tenant_id][resource]
        usage = self._usage.get(tenant_id, {}).get(resource, 0)
        return usage <= limit

    def increment_usage(self, tenant_id: str, resource: str, amount: int = 1) -> None:
        """Increment usage for a tenant's resource.

        Args:
            tenant_id: The tenant identifier.
            resource: The resource name.
            amount: The amount to increment by (default 1).
        """
        if tenant_id not in self._usage:
            self._usage[tenant_id] = {}
        if resource not in self._usage[tenant_id]:
            self._usage[tenant_id][resource] = 0
        self._usage[tenant_id][resource] += amount

    def get_usage(self, tenant_id: str, resource: str) -> int:
        """Get current usage for a tenant's resource.

        Args:
            tenant_id: The tenant identifier.
            resource: The resource name.

        Returns:
            The current usage amount.
        """
        return self._usage.get(tenant_id, {}).get(resource, 0)

    def reset_usage(self, tenant_id: str, resource: str) -> None:
        """Reset usage for a tenant's resource to zero.

        Args:
            tenant_id: The tenant identifier.
            resource: The resource name.
        """
        if tenant_id in self._usage and resource in self._usage[tenant_id]:
            self._usage[tenant_id][resource] = 0

    def is_quota_exceeded(self, tenant_id: str, resource: str) -> bool:
        """Check if a tenant's resource usage exceeds the quota.

        Args:
            tenant_id: The tenant identifier.
            resource: The resource name.

        Returns:
            True if quota is exceeded, False otherwise.
        """
        if tenant_id not in self._quotas or resource not in self._quotas[tenant_id]:
            return False
        limit = self._quotas[tenant_id][resource]
        usage = self._usage.get(tenant_id, {}).get(resource, 0)
        return usage > limit
