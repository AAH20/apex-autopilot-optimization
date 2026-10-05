"""Resource management package: quota-bounded allocation of finite
resource pools (CPU, memory, GPU, network, storage)."""

from apex_autopilot_optimization.resource.allocation import (
    ResourceAllocation,
    ResourceStatus,
    ResourceType,
)
from apex_autopilot_optimization.resource.manager import (
    QuotaExceededError,
    ResourceError,
    ResourceManager,
)
from apex_autopilot_optimization.resource.quota import ResourceQuota

__all__ = [
    "QuotaExceededError",
    "ResourceAllocation",
    "ResourceError",
    "ResourceManager",
    "ResourceQuota",
    "ResourceStatus",
    "ResourceType",
]
