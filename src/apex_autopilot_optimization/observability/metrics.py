"""Prometheus text-format metrics registry.

Exports RED metrics (Rate, Errors, Duration) and Four Golden Signals
(latency, traffic, errors, saturation) for swarm operations, WTA solves,
CBF filter decisions, and combat reallocation events. Output is compatible
with Prometheus scrape (text exposition format).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@dataclass(frozen=True, slots=True)
class MetricSample:
    """A single metric sample.

    Attributes:
        name: Metric name.
        type: One of "counter", "gauge", "histogram", "summary".
        value: Numeric value.
        labels: Label key/value pairs.
        timestamp: Unix epoch seconds (optional).
    """

    name: str
    type: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float | None = None


class MetricsRegistry:
    """Thread-safe registry of Prometheus-style metric samples.

    Counters only increase. Gauges can go up and down. Histograms accumulate
    observations for percentile calculation. All public methods are
    thread-safe (a single lock protects the whole registry, which is fine
    for the low-cardinality swarm-observability use case).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._labelled: dict[str, dict[tuple[tuple[str, str], ...], MetricSample]] = {}

    # -- counters -----------------------------------------------------------
    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        """Increment counter ``name`` by ``value`` (default 1)."""
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._labelled.setdefault(name, {}).setdefault(
                key, MetricSample(name, "counter", 0.0, dict(labels))
            )
            sample = self._labelled[name][key]
            # dataclass is frozen; rebuild
            self._labelled[name][key] = MetricSample(
                sample.name, sample.type, sample.value + value, sample.labels, None
            )
            if not labels:
                self._counters[name] = self._counters.get(name, 0.0) + value

    # -- gauges -------------------------------------------------------------
    def gauge(self, name: str, value: float, **labels: str) -> None:
        """Set gauge ``name`` to ``value``."""
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._labelled.setdefault(name, {}).setdefault(
                key, MetricSample(name, "gauge", value, dict(labels))
            )
            self._labelled[name][key] = MetricSample(name, "gauge", value, dict(labels), None)
            if not labels:
                self._gauges[name] = value

    # -- histograms ---------------------------------------------------------
    def observe(self, name: str, value: float, **labels: str) -> None:
        """Observe ``value`` in histogram ``name``."""
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._labelled.setdefault(name, {}).setdefault(
                key, MetricSample(name, "histogram", 0.0, dict(labels))
            )
            self._histograms.setdefault(name, []).append(value)
            if not labels:
                self._histograms.setdefault(name, []).append(value)

    # -- export -------------------------------------------------------------
    def get_samples(self) -> list[MetricSample]:
        """Return all current samples as MetricSample objects."""
        with self._lock:
            samples: list[MetricSample] = []
            for _name, samples_by_labels in self._labelled.items():
                for sample in samples_by_labels.values():
                    samples.append(sample)
            return samples

    def generate_latest(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        lines: list[str] = []
        with self._lock:
            # counters & gauges (labelled)
            for name in sorted(self._labelled):
                for sample in self._labelled[name].values():
                    label_str = ""
                    if sample.labels:
                        label_str = (
                            "{" + ",".join(f'{k}="{v}"' for k, v in sample.labels.items()) + "}"
                        )
                    ts = f" {int(sample.timestamp * 1000)}" if sample.timestamp else ""
                    lines.append(f"{name}{label_str} {sample.value}{ts}")
            # unlabelled counters/gauges
            for name in sorted(self._counters):
                lines.append(f"{name} {self._counters[name]}")
            for name in sorted(self._gauges):
                lines.append(f"{name} {self._gauges[name]}")
            # histograms
            for name in sorted(self._histograms):
                values = sorted(self._histograms[name])
                count = len(values)
                total = sum(values)
                lines.append(f"{name}_count {count}")
                lines.append(f"{name}_sum {total}")
                for q in (0.5, 0.9, 0.95, 0.99):
                    idx = max(0, min(count - 1, int(q * count - 1e-9)))
                    lines.append(f'{name}{{quantile="{q:g}"}} {values[idx]}')
        return "\n".join(lines) + "\n"


#: Module-level default registry (shared across the process).
DEFAULT_REGISTRY = MetricsRegistry()


def generate_latest() -> str:
    """Render the default registry in Prometheus text exposition format."""
    return DEFAULT_REGISTRY.generate_latest()
