"""Kubernetes manifest generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apex_autopilot_optimization.deployment.container import ContainerConfig


@dataclass
class K8sManifest:
    """Kubernetes manifest metadata."""

    apiVersion: str  # noqa: N815
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)


def generate_deployment(config: ContainerConfig) -> dict[str, Any]:
    """Generate a Kubernetes Deployment manifest."""
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": config.image,
            "labels": {"app": config.image},
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": config.image}},
            "template": {
                "metadata": {"labels": {"app": config.image}},
                "spec": {
                    "containers": [
                        {
                            "name": config.image,
                            "image": config.full_image,
                            "ports": [{"containerPort": p} for p in config.ports],
                            "env": [{"name": k, "value": v} for k, v in config.env_vars.items()],
                            "resources": {
                                "requests": config.resources,
                                "limits": config.resources,
                            },
                            "livenessProbe": {
                                "httpGet": {
                                    "path": config.health_check,
                                    "port": config.ports[0] if config.ports else 8080,
                                },
                                "initialDelaySeconds": 10,
                                "periodSeconds": 30,
                            },
                        }
                    ]
                },
            },
        },
    }


def generate_service(config: ContainerConfig) -> dict[str, Any]:
    """Generate a Kubernetes Service manifest."""
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": config.image,
            "labels": {"app": config.image},
        },
        "spec": {
            "selector": {"app": config.image},
            "ports": [{"port": p, "targetPort": p, "protocol": "TCP"} for p in config.ports],
            "type": "ClusterIP",
        },
    }


def generate_configmap(config: ContainerConfig) -> dict[str, Any]:
    """Generate a Kubernetes ConfigMap manifest."""
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": f"{config.image}-config",
            "labels": {"app": config.image},
        },
        "data": dict(config.env_vars),
    }


def generate_hpa(config: ContainerConfig) -> dict[str, Any]:
    """Generate a Kubernetes HorizontalPodAutoscaler manifest."""
    return {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {
            "name": f"{config.image}-hpa",
            "labels": {"app": config.image},
        },
        "spec": {
            "scaleTargetRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": config.image,
            },
            "minReplicas": 1,
            "maxReplicas": 5,
            "metrics": [
                {
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {"type": "Utilization", "averageUtilization": 70},
                    },
                }
            ],
        },
    }


def generate_pdb(config: ContainerConfig) -> dict[str, Any]:
    """Generate a Kubernetes PodDisruptionBudget manifest."""
    return {
        "apiVersion": "policy/v1",
        "kind": "PodDisruptionBudget",
        "metadata": {
            "name": f"{config.image}-pdb",
            "labels": {"app": config.image},
        },
        "spec": {
            "minAvailable": 1,
            "selector": {"matchLabels": {"app": config.image}},
        },
    }
