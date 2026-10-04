"""ConfigManager - unified configuration management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apex_autopilot_optimization.config.loader import load_config, save_config
from apex_autopilot_optimization.config.merger import deep_merge
from apex_autopilot_optimization.config.profiles import ConfigProfile, get_profile


class ConfigManager:
    """Manages layered configuration with load/save/get/set/validate."""

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def load(self, path: str) -> None:
        """Load a config file and merge it into the current config.

        Args:
            path: Path to the config file.
        """
        loaded = load_config(path)
        self._config = deep_merge(self._config, loaded)

    def save(self, path: str, config: dict[str, Any] | None = None) -> None:
        """Save the current config (or a provided config) to a file.

        Args:
            path: Destination file path.
            config: Config dict to save; uses internal config if None.
        """
        data = config if config is not None else self._config
        save_config(path, data)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dotted key.

        Args:
            key: Dotted key (e.g., "planner.resolution_m").
            default: Default value if key is not found.

        Returns:
            The config value, or default if not found.
        """
        parts = key.split(".")
        current: Any = self._config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def set(self, key: str, value: Any) -> None:
        """Set a config value by dotted key.

        Args:
            key: Dotted key (e.g., "planner.resolution_m").
            value: Value to set.
        """
        parts = key.split(".")
        current = self._config
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def validate(self) -> list[Any]:
        """Validate the current config using ConfigValidator.

        Returns:
            List of ValidationIssue objects.
        """
        from apex_autopilot_optimization.config_validator import validate_config

        return validate_config(self._config)

    def get_profile(self, name: str) -> ConfigProfile:
        """Get a config profile by name.

        Args:
            name: Profile name.

        Returns:
            The ConfigProfile instance.
        """
        return get_profile(name)

    def apply_profile(self, name: str) -> None:
        """Apply a named profile's values to the current config.

        Args:
            name: Profile name to apply.
        """
        profile = get_profile(name)
        self._config = deep_merge(self._config, profile.values)
