"""Environment variable configuration loading."""

from __future__ import annotations

import os
from typing import Any


def env_var_to_config_key(name: str, prefix: str = "APEX_") -> str:
    """Convert an environment variable name to a dotted config key.

    Double underscores (``__``) denote nesting; single underscores are
    preserved as part of the key.

    Args:
        name: Environment variable name (e.g., "APEX_PLANNER__RESOLUTION_M").
        prefix: The prefix to strip (default: "APEX_").

    Returns:
        Dotted config key (e.g., "planner.resolution_m").
    """
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name.lower().replace("__", ".")


def _convert_value(value: str) -> Any:
    """Convert an env var string value to int, float, bool, or string."""
    lowered = value.lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def load_env_config(prefix: str = "APEX_") -> dict[str, Any]:
    """Load configuration from environment variables with the given prefix.

    Variables are converted to nested dicts using '__' as the nesting
    separator. Values are auto-typed (int, float, bool, or string).

    Args:
        prefix: Environment variable prefix to match (default: "APEX_").

    Returns:
        A nested configuration dict.
    """
    result: dict[str, Any] = {}
    for name, value in os.environ.items():
        if not name.startswith(prefix):
            continue
        key = env_var_to_config_key(name, prefix)
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = _convert_value(value)
    return result
