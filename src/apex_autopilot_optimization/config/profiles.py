"""Configuration profiles and layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConfigLayer(StrEnum):
    """Configuration layer precedence (lowest to highest)."""

    DEFAULTS = "defaults"
    USER = "user"
    PROJECT = "project"
    ENV = "env"
    CLI = "cli"


@dataclass
class ConfigProfile:
    """A named configuration profile with optional inheritance."""

    name: str
    inherits: str | None = None
    values: dict[str, Any] = field(default_factory=dict)


# ── Built-in Profiles ────────────────────────────────────────────────────────

_BUILTIN_PROFILES: dict[str, ConfigProfile] = {
    "startup": ConfigProfile(
        name="startup",
        inherits=None,
        values={
            "scale": "startup",
            "planner": "astar",
            "optimizer": "minimum_snap",
            "estimator": "ekf",
            "max_iterations": 10000,
            "log_level": "INFO",
            "safety": {"enabled": False},
            "swarm": {"enabled": False},
        },
    ),
    "smb": ConfigProfile(
        name="smb",
        inherits="startup",
        values={
            "scale": "smb",
            "planner": "astar",
            "max_iterations": 20000,
            "safety": {"enabled": True, "safety_margin": 1.0},
        },
    ),
    "mid_market": ConfigProfile(
        name="mid_market",
        inherits="smb",
        values={
            "scale": "mid_market",
            "planner": "rrt",
            "max_iterations": 30000,
            "controller": "mpc",
        },
    ),
    "enterprise": ConfigProfile(
        name="enterprise",
        inherits="mid_market",
        values={
            "scale": "enterprise",
            "planner": "hybrid_astar",
            "max_iterations": 50000,
            "log_level": "INFO",
            "metrics_enabled": True,
            "safety": {"enabled": True, "safety_margin": 2.0, "alpha": 1.0},
            "swarm": {"enabled": True, "max_agents": 100, "formation_type": "hexagon"},
            "security": {"encryption": True, "authentication": True, "audit_log": True},
        },
    ),
    "large": ConfigProfile(
        name="large",
        inherits="enterprise",
        values={
            "scale": "large",
            "max_iterations": 100000,
            "swarm": {"max_agents": 500},
        },
    ),
}


def get_profile(name: str) -> ConfigProfile:
    """Get a configuration profile by name.

    Args:
        name: Profile name (e.g., "startup", "enterprise").

    Returns:
        The ConfigProfile instance.

    Raises:
        KeyError: If the profile name is not found.
    """
    if name not in _BUILTIN_PROFILES:
        raise KeyError(f"Unknown config profile: {name!r}")
    return _BUILTIN_PROFILES[name]


def list_profiles() -> list[str]:
    """List all available profile names.

    Returns:
        Sorted list of profile names.
    """
    return sorted(_BUILTIN_PROFILES.keys())
