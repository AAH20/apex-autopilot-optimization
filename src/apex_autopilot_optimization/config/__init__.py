"""Configuration management for apex-autopilot-optimization.

Provides layered configuration loading, merging, profiles, and
environment variable integration.
"""

from __future__ import annotations

from apex_autopilot_optimization.config.loader import load_config, save_config
from apex_autopilot_optimization.config.manager import ConfigManager
from apex_autopilot_optimization.config.merger import deep_merge, resolve_config
from apex_autopilot_optimization.config.profiles import (
    ConfigLayer,
    ConfigProfile,
    get_profile,
    list_profiles,
)

__all__ = [
    "ConfigLayer",
    "ConfigManager",
    "ConfigProfile",
    "deep_merge",
    "get_profile",
    "list_profiles",
    "load_config",
    "resolve_config",
    "save_config",
]
