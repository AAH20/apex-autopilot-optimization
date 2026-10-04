"""Feature flags module for apex-autopilot-optimization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FeatureFlag:
    """A feature flag with rollout control."""

    name: str
    enabled: bool = False
    rollout_percentage: float = 0.0
    description: str = ""


class FeatureFlagStore:
    """In-memory store for feature flags with YAML persistence."""

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}

    def create(self, flag: FeatureFlag) -> FeatureFlag:
        """Create a new feature flag. Raises ValueError if name already exists."""
        if flag.name in self._flags:
            raise ValueError(f"Feature flag '{flag.name}' already exists")
        self._flags[flag.name] = flag
        return flag

    def get(self, name: str) -> FeatureFlag:
        """Get a feature flag by name. Raises KeyError if not found."""
        if name not in self._flags:
            raise KeyError(f"Feature flag '{name}' not found")
        return self._flags[name]

    def is_enabled(self, name: str, context: dict[str, Any] | None = None) -> bool:
        """Check if a feature flag is enabled, optionally with context for rollout."""
        flag = self.get(name)
        if not flag.enabled:
            return False
        if flag.rollout_percentage >= 100.0:
            return True
        if flag.rollout_percentage <= 0.0:
            return False
        # Context-aware rollout: hash user_id to get stable bucket
        if context and "user_id" in context:
            user_id = str(context["user_id"])
            hash_val = int(hashlib.md5(f"{name}:{user_id}".encode()).hexdigest(), 16)
            bucket = (hash_val % 10000) / 100.0  # 0.0 to 99.99
            return bucket < flag.rollout_percentage
        # No user_id in context — use enabled state with rollout check
        # If rollout < 100% and no user context, default to disabled for safety
        return flag.rollout_percentage >= 100.0

    def update(self, name: str, **kwargs: Any) -> FeatureFlag:
        """Update a feature flag's attributes. Raises KeyError if not found."""
        flag = self.get(name)
        for key, value in kwargs.items():
            if hasattr(flag, key):
                setattr(flag, key, value)
            else:
                raise ValueError(f"FeatureFlag has no attribute '{key}'")
        return flag

    def list_flags(self) -> list[FeatureFlag]:
        """List all feature flags."""
        return list(self._flags.values())

    def load_from_yaml(self, path: str | Path) -> None:
        """Load feature flags from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "flags" not in data:
            return
        for item in data["flags"]:
            flag = FeatureFlag(
                name=item["name"],
                enabled=item.get("enabled", False),
                rollout_percentage=item.get("rollout_percentage", 0.0),
                description=item.get("description", ""),
            )
            # Don't raise on duplicates during load — overwrite
            self._flags[flag.name] = flag

    def save_to_yaml(self, path: str | Path) -> None:
        """Save feature flags to a YAML file."""
        data = {
            "flags": [
                {
                    "name": f.name,
                    "enabled": f.enabled,
                    "rollout_percentage": f.rollout_percentage,
                    "description": f.description,
                }
                for f in self._flags.values()
            ]
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
