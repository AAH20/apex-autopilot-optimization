"""Experiment tracker module for apex-autopilot-optimization."""

from __future__ import annotations

import statistics
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExperimentRun:
    """A single experiment run."""

    run_id: str
    name: str
    variant: str
    metrics: dict[str, float] = field(default_factory=dict)
    timestamp: float = 0.0


class ExperimentTracker:
    """Track experiment runs and compare results."""

    def __init__(self) -> None:
        self._runs: dict[str, ExperimentRun] = {}

    def start_run(self, name: str, variant: str) -> ExperimentRun:
        """Start a new experiment run."""
        run_id = str(uuid.uuid4())
        run = ExperimentRun(
            run_id=run_id,
            name=name,
            variant=variant,
            timestamp=time.time(),
        )
        self._runs[run_id] = run
        return run

    def end_run(self, run_id: str, metrics: dict[str, float]) -> ExperimentRun:
        """End an experiment run with final metrics. Raises KeyError if not found."""
        if run_id not in self._runs:
            raise KeyError(f"Experiment run '{run_id}' not found")
        self._runs[run_id].metrics = metrics
        return self._runs[run_id]

    def get_run(self, run_id: str) -> ExperimentRun:
        """Get an experiment run by ID. Raises KeyError if not found."""
        if run_id not in self._runs:
            raise KeyError(f"Experiment run '{run_id}' not found")
        return self._runs[run_id]

    def list_runs(self, name: str) -> list[ExperimentRun]:
        """List all runs for a given experiment name."""
        return [r for r in self._runs.values() if r.name == name]

    def compare_runs(self, run_id_a: str, run_id_b: str) -> dict[str, Any]:
        """Compare two experiment runs. Raises KeyError if either not found."""
        if run_id_a not in self._runs:
            raise KeyError(f"Experiment run '{run_id_a}' not found")
        if run_id_b not in self._runs:
            raise KeyError(f"Experiment run '{run_id_b}' not found")
        run_a = self._runs[run_id_a]
        run_b = self._runs[run_id_b]
        all_keys = set(run_a.metrics.keys()) | set(run_b.metrics.keys())
        metrics_diff: dict[str, float] = {}
        for key in all_keys:
            val_a = run_a.metrics.get(key, 0.0)
            val_b = run_b.metrics.get(key, 0.0)
            metrics_diff[key] = val_a - val_b
        return {
            "run_a": run_id_a,
            "run_b": run_id_b,
            "name": run_a.name,
            "variant_a": run_a.variant,
            "variant_b": run_b.variant,
            "metrics_diff": metrics_diff,
        }
