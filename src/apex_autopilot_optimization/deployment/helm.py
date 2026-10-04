"""Helm chart values and Chart.yaml generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apex_autopilot_optimization.deployment.container import ContainerConfig


@dataclass
class HelmValues:
    """Helm chart values configuration."""

    replicaCount: int = 1
    image: dict[str, Any] = field(default_factory=dict)
    service: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    autoscaling: dict[str, Any] = field(default_factory=dict)


def generate_values(config: ContainerConfig) -> dict[str, Any]:
    """Generate Helm values from a ContainerConfig."""
    return {
        "replicaCount": 1,
        "image": {
            "repository": f"{config.registry}/{config.image}",
            "tag": config.tag,
            "pullPolicy": "IfNotPresent",
        },
        "service": {
            "type": "ClusterIP",
            "port": config.ports[0] if config.ports else 8080,
        },
        "resources": {
            "requests": config.resources,
            "limits": config.resources,
        },
        "autoscaling": {
            "enabled": False,
            "minReplicas": 1,
            "maxReplicas": 5,
            "targetCPUUtilizationPercentage": 70,
        },
    }


def generate_chart(config: ContainerConfig) -> dict[str, Any]:
    """Generate a Helm Chart.yaml from a ContainerConfig."""
    return {
        "apiVersion": "v2",
        "name": config.image,
        "version": config.tag,
        "appVersion": config.tag,
        "description": f"Helm chart for {config.image}",
    }
