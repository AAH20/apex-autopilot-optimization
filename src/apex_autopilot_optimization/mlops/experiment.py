"""Experiment tracking for the MLOps layer.

:class:`ExperimentTracker` records the lifecycle of experiment runs: a config
captured at start, a time series of logged metrics, and a final result.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Experiment:
    """A single tracked experiment.

    Attributes:
        experiment_id: Unique identifier assigned at start.
        name: Human-readable experiment name.
        config: Hyperparameters / configuration captured at start.
        status: ``"running"`` until ended, then ``"completed"``.
        metrics: Logged metric values keyed by metric name.
        result: Final result dict supplied to :meth:`ExperimentTracker.end_experiment`.
        started_at: POSIX timestamp of start.
        ended_at: POSIX timestamp of end (``0.0`` while running).
    """

    experiment_id: str
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    status: str = "running"
    metrics: dict[str, list[float]] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0


class ExperimentTracker:
    """Track experiment runs, their metrics, and comparisons."""

    def __init__(self) -> None:
        self._experiments: dict[str, Experiment] = {}

    def start_experiment(self, name: str, config: dict[str, Any]) -> str:
        """Start a new experiment and return its identifier."""
        experiment_id = str(uuid.uuid4())
        self._experiments[experiment_id] = Experiment(
            experiment_id=experiment_id,
            name=name,
            config=dict(config),
        )
        return experiment_id

    def log_metric(self, experiment_id: str, metric: str, value: float) -> None:
        """Append ``value`` to the ``metric`` series of an experiment.

        Raises:
            KeyError: If the experiment is unknown.
            RuntimeError: If the experiment has already ended.
        """
        exp = self._get(experiment_id)
        if exp.status != "running":
            raise RuntimeError(f"Experiment '{experiment_id}' has already ended")
        exp.metrics.setdefault(metric, []).append(value)

    def end_experiment(self, experiment_id: str, result: dict[str, Any]) -> Experiment:
        """Finalize an experiment with a result dict.

        Raises:
            KeyError: If the experiment is unknown.
            RuntimeError: If the experiment has already ended.
        """
        exp = self._get(experiment_id)
        if exp.status != "running":
            raise RuntimeError(f"Experiment '{experiment_id}' has already ended")
        exp.result = dict(result)
        exp.status = "completed"
        exp.ended_at = time.time()
        return exp

    def get_experiment(self, experiment_id: str) -> Experiment:
        """Return an experiment by id.

        Raises:
            KeyError: If the experiment is unknown.
        """
        return self._get(experiment_id)

    def list_experiments(self) -> list[Experiment]:
        """Return all tracked experiments."""
        return list(self._experiments.values())

    def compare_experiments(self, id_a: str, id_b: str) -> dict[str, Any]:
        """Compare two experiments by their final metric values.

        The diff for each metric is ``value_b - value_a``. A metric's value is
        its entry in the experiment ``result`` when present, otherwise the last
        value logged via :meth:`log_metric`.

        Raises:
            KeyError: If either experiment is unknown.
        """
        exp_a = self._get(id_a)
        exp_b = self._get(id_b)

        def _final_value(exp: Experiment, metric: str) -> float:
            if metric in exp.result:
                return float(exp.result[metric])
            series = exp.metrics.get(metric, [])
            return float(series[-1]) if series else 0.0

        all_metrics = (
            set(exp_a.metrics) | set(exp_b.metrics) | set(exp_a.result) | set(exp_b.result)
        )
        metrics_diff = {
            metric: _final_value(exp_b, metric) - _final_value(exp_a, metric)
            for metric in all_metrics
        }
        return {
            "experiment_a": id_a,
            "experiment_b": id_b,
            "name_a": exp_a.name,
            "name_b": exp_b.name,
            "metrics_diff": metrics_diff,
        }

    def _get(self, experiment_id: str) -> Experiment:
        try:
            return self._experiments[experiment_id]
        except KeyError:
            raise KeyError(f"Experiment '{experiment_id}' not found") from None
