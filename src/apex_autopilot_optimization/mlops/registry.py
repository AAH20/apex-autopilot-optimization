"""Persistent model registry for the MLOps layer.

The :class:`ModelRegistry` stores :class:`ModelVersion` records in a JSON index
on disk so registrations survive process restarts. It provides CRUD operations
over ``(name, version)`` pairs plus lifecycle promotion.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apex_autopilot_optimization.mlops.version import ModelStage, ModelVersion


class ModelRegistry:
    """A file-backed registry of model versions.

    Args:
        root: Directory that holds the registry index. Created on demand.
        index_filename: Name of the JSON index file within ``root``.
    """

    def __init__(self, root: str, index_filename: str = "registry.json") -> None:
        self._root = Path(root)
        self._index_path = self._root / index_filename
        self._models: dict[str, dict[str, ModelVersion]] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        for name, versions in raw.items():
            self._models[name] = {
                ver: ModelVersion(
                    name=record["name"],
                    version=record["version"],
                    path=record["path"],
                    stage=ModelStage(record["stage"]),
                    metadata=dict(record.get("metadata", {})),
                    created_at=record["created_at"],
                )
                for ver, record in versions.items()
            }

    def _save(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        payload: dict[str, dict[str, Any]] = {}
        for name, versions in self._models.items():
            payload[name] = {
                ver: {
                    "name": mv.name,
                    "version": mv.version,
                    "path": mv.path,
                    "stage": mv.stage.value,
                    "metadata": mv.metadata,
                    "created_at": mv.created_at,
                }
                for ver, mv in versions.items()
            }
        self._index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def register_model(
        self,
        name: str,
        version: str,
        path: str,
        metadata: dict[str, Any] | None = None,
    ) -> ModelVersion:
        """Register a new model version.

        Raises:
            ValueError: If ``(name, version)`` is already registered.
        """
        existing = self._models.get(name, {})
        if version in existing:
            raise ValueError(f"Model '{name}' version '{version}' is already registered")
        mv = ModelVersion(
            name=name,
            version=version,
            path=path,
            metadata=dict(metadata or {}),
        )
        self._models.setdefault(name, {})[version] = mv
        self._save()
        return mv

    def get_model(self, name: str, version: str) -> ModelVersion:
        """Return the registered :class:`ModelVersion`.

        Raises:
            KeyError: If the model or version is unknown.
        """
        try:
            return self._models[name][version]
        except KeyError:
            raise KeyError(f"Model '{name}' version '{version}' not found") from None

    def list_models(self) -> list[str]:
        """Return the distinct registered model names."""
        return list(self._models.keys())

    def list_versions(self, name: str) -> list[ModelVersion]:
        """Return all registered versions for ``name`` (empty if unknown)."""
        return list(self._models.get(name, {}).values())

    def delete_model(self, name: str, version: str) -> bool:
        """Delete a model version. Returns ``False`` if it did not exist."""
        versions = self._models.get(name)
        if not versions or version not in versions:
            return False
        del versions[version]
        if not versions:
            del self._models[name]
        self._save()
        return True

    def promote_model(self, name: str, version: str, stage: ModelStage | str) -> ModelVersion:
        """Transition a model version to a new lifecycle ``stage``.

        Raises:
            ValueError: If ``stage`` is not a valid :class:`ModelStage`.
            KeyError: If the model version is unknown.
        """
        try:
            resolved = stage if isinstance(stage, ModelStage) else ModelStage(stage)
        except ValueError:
            raise ValueError(f"Invalid model stage: {stage!r}") from None
        mv = self.get_model(name, version)
        mv.stage = resolved
        self._save()
        return mv

    def get_model_metadata(self, name: str, version: str) -> dict[str, Any]:
        """Return the metadata dict for a model version."""
        return self.get_model(name, version).metadata
