"""Tenant context management for apex-autopilot-optimization."""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

__all__ = [
    "TenantContext",
    "clear_current_tenant",
    "get_current_tenant",
    "require_tenant",
    "set_current_tenant",
]

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class TenantContext:
    """Context information for the current tenant."""

    tenant_id: str
    tier: str
    metadata: dict[str, Any] = field(default_factory=dict)


_thread_local = threading.local()


def get_current_tenant() -> TenantContext | None:
    """Get the current tenant context for this thread.

    Returns:
        The current TenantContext or None if no tenant is set.
    """
    return getattr(_thread_local, "tenant_context", None)


def set_current_tenant(tenant: TenantContext) -> None:
    """Set the current tenant context for this thread.

    Args:
        tenant: The TenantContext to set as current.
    """
    _thread_local.tenant_context = tenant


def clear_current_tenant() -> None:
    """Clear the current tenant context for this thread."""
    if hasattr(_thread_local, "tenant_context"):
        delattr(_thread_local, "tenant_context")


def require_tenant(func: F) -> F:
    """Decorator that requires a tenant context to be set.

    The decorated function will receive the TenantContext as its first
    positional argument. Raises RuntimeError if no tenant context is set.

    Args:
        func: The function to decorate.

    Returns:
        The decorated function.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = get_current_tenant()
        if ctx is None:
            raise RuntimeError("No tenant context set")
        return func(ctx, *args, **kwargs)

    return wrapper  # type: ignore[return-value]
