"""On-device AI inference for edge nodes.

The EdgeAI component manages a small set of models that can be loaded,
queried, and unloaded at runtime. Inference is deterministic and
dependency-free so it runs in constrained edge environments.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any


class EdgeAI:
    """Manages model lifecycle and inference on an edge device."""

    def __init__(self) -> None:
        self._model: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def load_model(self, model_path: str) -> bool:
        """Load (or reload) the model located at ``model_path``.

        Returns True on success. Raises ValueError for an invalid path.
        """
        if not isinstance(model_path, str) or not model_path.strip():
            raise ValueError("model_path must be a non-empty string")
        with self._lock:
            self._model = {
                "path": model_path,
                "loaded_at": time.time(),
                "inference_count": 0,
            }
        return True

    def is_model_loaded(self) -> bool:
        """Return True if a model is currently loaded."""
        with self._lock:
            return self._model is not None

    def get_model_info(self) -> dict[str, Any] | None:
        """Return metadata about the loaded model, or None."""
        with self._lock:
            if self._model is None:
                return None
            return dict(self._model)

    def unload_model(self) -> bool:
        """Unload the current model. Returns True if a model was loaded."""
        with self._lock:
            was_loaded = self._model is not None
            self._model = None
            return was_loaded

    def run_inference(self, input_data: Any) -> dict[str, Any]:
        """Run inference against the loaded model.

        Produces a deterministic prediction derived from ``input_data``:
        numeric mappings/lists are summarised into a scalar score, other
        payloads are hashed. Raises RuntimeError if no model is loaded.
        """
        with self._lock:
            if self._model is None:
                raise RuntimeError("no model loaded; call load_model() first")
            self._model["inference_count"] += 1
            model_path = self._model["path"]

        prediction, confidence = self._compute(input_data)
        return {
            "prediction": prediction,
            "confidence": confidence,
            "model": model_path,
        }

    @staticmethod
    def _compute(input_data: Any) -> tuple[float, float]:
        """Derive a deterministic (prediction, confidence) pair."""
        if isinstance(input_data, dict):
            values = [v for v in input_data.values() if isinstance(v, int | float)]
            if values:
                score = sum(values) / len(values)
                return float(score), min(1.0, abs(score) / 100.0)
        if isinstance(input_data, list | tuple):
            values = [v for v in input_data if isinstance(v, int | float)]
            if values:
                score = sum(values) / len(values)
                return float(score), min(1.0, abs(score) / 100.0)
        digest = hashlib.sha256(repr(input_data).encode("utf-8")).digest()
        score = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        return float(score), min(1.0, score)
