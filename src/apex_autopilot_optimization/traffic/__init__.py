"""Traffic management: rate limiting, load balancing, service discovery."""

from __future__ import annotations

from dataclasses import dataclass

from apex_autopilot_optimization.traffic.load_balancer import (
    LeastConnectionsStrategy,
    LoadBalancer,
    RandomStrategy,
    RoundRobinStrategy,
)
from apex_autopilot_optimization.traffic.rate_limit import (
    RateLimiter,
    RateLimitConfig,
    TokenBucket,
)
from apex_autopilot_optimization.traffic.service_registry import ServiceRegistry


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before transitioning to HALF_OPEN.
        half_open_max_calls: Max calls allowed in HALF_OPEN state.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3


__all__ = [
    "CircuitBreakerConfig",
    "LeastConnectionsStrategy",
    "LoadBalancer",
    "RandomStrategy",
    "RateLimiter",
    "RateLimitConfig",
    "RoundRobinStrategy",
    "ServiceRegistry",
    "TokenBucket",
]
