"""Checkpoint management for saving and restoring state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CheckpointManager:
    """Manages named checkpoints stored as JSON files."""

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _checkpoint_path(self, name: str) -> Path:
        """Get the file path for a checkpoint."""
        return self._dir / f"{name}.json"

    def save_checkpoint(self, name: str, data: Any) -> None:
        """Save a checkpoint with the given name and data."""
        path = self._checkpoint_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_checkpoint(self, name: str) -> Any | None:
        """Load a checkpoint by name. Returns None if not found."""
        path = self._checkpoint_path(name)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def list_checkpoints(self) -> list[str]:
        """List all checkpoint names."""
        return [p.stem for p in self._dir.glob("*.json")]

    def delete_checkpoint(self, name: str) -> None:
        """Delete a checkpoint by name."""
        path = self._checkpoint_path(name)
        if path.exists():
            path.unlink()

    def get_latest_checkpoint(self) -> tuple[str, Any] | None:
        """Get the most recently modified checkpoint."""
        checkpoints = list(self._dir.glob("*.json"))
        if not checkpoints:
            return None
        latest = max(checkpoints, key=lambda p: p.stat().st_mtime)
        with open(latest, encoding="utf-8") as f:
            data = json.load(f)
        return (latest.stem, data)
