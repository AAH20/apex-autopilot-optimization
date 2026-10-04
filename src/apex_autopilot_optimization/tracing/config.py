"""Tracing configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TracingConfig:
    """Configuration for distributed tracing.

    Attributes:
        enabled: Whether tracing is active.
        sample_rate: Fraction of traces to sample (0.0 to 1.0).
        exporter: Exporter type (e.g. "console", "otlp").
        endpoint: Exporter endpoint URL.
        service_name: Name of the service being traced.
    """

    enabled: bool = False
    sample_rate: float = 1.0
    exporter: str = "console"
    endpoint: str = ""
    service_name: str = "apex-autopilot"
