"""Prometheus metrics exporter for apex-autopilot-optimization.

Provides metric registration, Prometheus text-format export, and
metric introspection for autopilot systems.
"""

from __future__ import annotations

from typing import Any, cast


class PrometheusExporter:
    """Exports metrics in Prometheus text format.

    Supports counter, gauge, and histogram metric types with optional
    labels. Metrics are stored in-memory and can be exported as a
    Prometheus-compatible string.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, dict[str, Any]] = {}

    def register_metric(
        self,
        name: str,
        value: float,
        metric_type: str = "gauge",
        labels: dict[str, str] | None = None,
    ) -> None:
        """Register or update a metric.

        Args:
            name: Metric name (e.g., "requests_total").
            value: Current metric value.
            metric_type: One of "counter", "gauge", or "histogram".
            labels: Optional label key-value pairs.
        """
        self._metrics[name] = {
            "name": name,
            "value": value,
            "type": metric_type,
            "labels": labels or {},
        }

    def get_metrics(self) -> str:
        """Export all registered metrics in Prometheus text format.

        Returns:
            Prometheus exposition format string.
        """
        if not self._metrics:
            return ""

        lines: list[str] = []
        for metric in self._metrics.values():
            name = metric["name"]
            value = metric["value"]
            metric_type = metric["type"]
            labels = metric["labels"]

            # HELP and TYPE lines (only once per metric)
            lines.append(f"# HELP {name} {name} metric")
            lines.append(f"# TYPE {name} {metric_type}")

            # Format the metric line with labels
            if labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"{name}{{{label_str}}} {value}")
            else:
                lines.append(f"{name} {value}")

        return "\n".join(lines) + "\n"

    def get_metric_names(self) -> list[str]:
        """Get all registered metric names.

        Returns:
            List of metric names.
        """
        return list(self._metrics.keys())

    def clear_metrics(self) -> None:
        """Remove all registered metrics."""
        self._metrics.clear()

    def get_metric_value(self, name: str) -> float | None:
        """Get the current value of a metric.

        Args:
            name: Metric name.

        Returns:
            Metric value, or None if not registered.
        """
        metric = self._metrics.get(name)
        if metric is None:
            return None
        return cast(float, metric["value"])
