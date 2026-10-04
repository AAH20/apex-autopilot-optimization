"""Deep merge and config layer resolution."""

from __future__ import annotations

from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base.

    - Nested dicts are merged key-by-key.
    - Lists and scalars in override replace those in base.
    - Neither input is mutated.

    Args:
        base: The base configuration dict.
        override: The overriding configuration dict.

    Returns:
        A new dict containing the merged result.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_config(layers: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve a precedence chain of config layers.

    Later layers take precedence over earlier ones, merged deeply.

    Args:
        layers: Ordered list of config dicts (lowest to highest precedence).

    Returns:
        The fully merged configuration.
    """
    result: dict[str, Any] = {}
    for layer in layers:
        result = deep_merge(result, layer)
    return result
