"""Deployment and DevOps for apex-autopilot-optimization.

Provides container, Kubernetes, Helm, and Terraform configuration
generation for deploying the autopilot optimization service.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_autopilot_optimization.deployment.container import (
    ContainerConfig,
    generate_docker_compose,
    generate_dockerfile,
)
from apex_autopilot_optimization.deployment.helm import (
    HelmValues,
    generate_chart,
    generate_values,
)
from apex_autopilot_optimization.deployment.k8s import (
    K8sManifest,
    generate_configmap,
    generate_deployment,
    generate_hpa,
    generate_pdb,
    generate_service,
)
from apex_autopilot_optimization.deployment.terraform import (
    TerraformConfig,
    generate_main_tf,
    generate_outputs_tf,
    generate_variables_tf,
)


@dataclass
class DeploymentConfig:
    """Composite deployment configuration for all targets."""

    name: str
    version: str
    container: ContainerConfig
    k8s: K8sManifest
    helm: HelmValues
    terraform: TerraformConfig


__all__ = [
    "ContainerConfig",
    "DeploymentConfig",
    "HelmValues",
    "K8sManifest",
    "TerraformConfig",
    "generate_chart",
    "generate_configmap",
    "generate_deployment",
    "generate_docker_compose",
    "generate_dockerfile",
    "generate_hpa",
    "generate_main_tf",
    "generate_outputs_tf",
    "generate_pdb",
    "generate_service",
    "generate_values",
    "generate_variables_tf",
]
