"""Traffic management configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrafficConfig:
    """Configuration for traffic management.

    Attributes:
        rate_limit_enabled: Whether rate limiting is active.
        load_balancer_enabled: Whether load balancing is active.
        health_check_interval: Seconds between health checks.
        max_retries: Maximum retry attempts for failed requests.
    """

    rate_limit_enabled: bool = True
    load_balancer_enabled: bool = True
    health_check_interval: float = 30.0
    max_retries: int = 3
