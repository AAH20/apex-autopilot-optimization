"""In-process model server for the MLOps layer.

The :class:`ModelServer` loads artifacts referenced by a :class:`ModelRegistry`,
invokes them through a uniform ``serve`` entry point, and tracks per-model
serving statistics.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from apex_autopilot_optimization.mlops.registry import ModelRegistry


class ModelServer:
    """Load and serve registered model artifacts.

    Args:
        registry: The :class:`ModelRegistry` backing artifact lookups.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry
        self._loaded: dict[str, Any] = {}
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._per_model_requests: dict[str, int] = {}
        self._active_model: str | None = None

    @staticmethod
    def _key(name: str, version: str) -> str:
        return f"{name}:{version}"

    def load_model(self, name: str, version: str) -> Any:
        """Load a model artifact into memory.

        Raises:
            KeyError: If the registry has no such model version.
            FileNotFoundError: If the artifact path does not exist.
        """
        mv = self._registry.get_model(name, version)
        artifact_path = Path(mv.path)
        if not artifact_path.exists():
            raise FileNotFoundError(f"Model artifact not found: {mv.path}")
        with open(artifact_path, "rb") as fh:
            model = pickle.load(fh)
        key = self._key(name, version)
        self._loaded[key] = model
        self._active_model = key
        return model

    def serve(self, input_data: Any) -> Any:
        """Run the most recently loaded model on ``input_data``.

        The model may be any callable, or any object exposing a ``predict``
        method.

        Raises:
            RuntimeError: If no model is currently loaded, or invocation fails.
        """
        if self._active_model is None or self._active_model not in self._loaded:
            raise RuntimeError("No model is currently loaded")
        model = self._loaded[self._active_model]
        self._total_requests += 1
        self._per_model_requests[self._active_model] = (
            self._per_model_requests.get(self._active_model, 0) + 1
        )
        try:
            if callable(model):
                result = model(input_data)
            elif hasattr(model, "predict"):
                result = model.predict(input_data)
            else:
                raise RuntimeError("Loaded object is not callable and has no 'predict' method")
        except Exception as exc:  # noqa: BLE001 - re-raised as serving error
            self._failed_requests += 1
            raise RuntimeError(f"Model inference failed: {exc}") from exc
        self._successful_requests += 1
        return result

    def get_model_info(self, name: str, version: str) -> dict[str, Any]:
        """Return registry metadata plus load state for a model version.

        Raises:
            KeyError: If the registry has no such model version.
        """
        mv = self._registry.get_model(name, version)
        return {
            "name": mv.name,
            "version": mv.version,
            "path": mv.path,
            "stage": mv.stage.value,
            "metadata": dict(mv.metadata),
            "created_at": mv.created_at,
            "loaded": self.is_model_loaded(name, version),
        }

    def unload_model(self, name: str, version: str) -> bool:
        """Unload a model. Returns ``False`` if it was not loaded."""
        key = self._key(name, version)
        if key not in self._loaded:
            return False
        del self._loaded[key]
        if self._active_model == key:
            self._active_model = next(iter(self._loaded), None)
        return True

    def is_model_loaded(self, name: str, version: str) -> bool:
        """Return whether a model version is currently loaded."""
        return self._key(name, version) in self._loaded

    def get_serving_stats(self) -> dict[str, Any]:
        """Return cumulative serving statistics."""
        return {
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "models_loaded": len(self._loaded),
            "active_model": self._active_model,
            "per_model_requests": dict(self._per_model_requests),
        }
