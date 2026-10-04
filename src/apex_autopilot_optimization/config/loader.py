"""Config file loading and saving.

Supports YAML (.yaml, .yml), JSON (.json), and TOML (.toml) formats,
selected by file extension.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str) -> dict[str, Any]:
    """Load a configuration file based on its extension.

    Args:
        path: Path to the config file (.yaml, .yml, .json, or .toml).

    Returns:
        The parsed configuration as a dict.

    Raises:
        ValueError: If the file extension is not supported.
        FileNotFoundError: If the file does not exist.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in (".yaml", ".yml"):
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data is not None else {}
    elif suffix == ".json":
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    elif suffix == ".toml":
        import tomllib

        with open(p, "rb") as f:
            return tomllib.load(f)
    else:
        raise ValueError(
            f"Unsupported config format: {suffix!r}. "
            "Supported formats: .yaml, .yml, .json, .toml"
        )


def save_config(path: str, config: dict[str, Any]) -> None:
    """Save a configuration dict to a file based on its extension.

    Args:
        path: Destination path (.yaml, .yml, .json, or .toml).
        config: Configuration data to serialize.

    Raises:
        ValueError: If the file extension is not supported.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in (".yaml", ".yml"):
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
    elif suffix == ".json":
        with open(p, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    elif suffix == ".toml":
        import tomli_w

        with open(p, "w", encoding="utf-8") as f:
            f.write(tomli_w.dumps(config))
    else:
        raise ValueError(
            f"Unsupported config format: {suffix!r}. "
            "Supported formats: .yaml, .yml, .json, .toml"
        )
