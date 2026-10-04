"""Terraform configuration and HCL generation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TerraformConfig:
    """Terraform infrastructure configuration."""

    provider: str
    region: str
    cluster_name: str
    node_pools: list[dict] = field(default_factory=list)


def generate_main_tf(config: TerraformConfig) -> str:
    """Generate Terraform main.tf content."""
    lines = [
        f'terraform {{',
        f'  required_providers {{',
        f'    {config.provider} = {{',
        f'      source  = "hashicorp/{config.provider}"',
        f'      version = ">= 4.0"',
        f'    }}',
        f'  }}',
        f'}}',
        f'',
        f'provider "{config.provider}" {{',
        f'  region = "{config.region}"',
        f'}}',
        f'',
        f'resource "{config.provider}_eks_cluster" "main" {{',
        f'  name     = "{config.cluster_name}"',
        f'  role_arn = aws_iam_role.cluster.arn',
        f'',
        f'  vpc_config {{',
        f'    subnet_ids = var.subnet_ids',
        f'  }}',
        f'}}',
        f'',
    ]

    for pool in config.node_pools:
        lines.append(
            f'resource "{config.provider}_eks_node_group" "{pool["name"]}" {{'
        )
        lines.append(f'  cluster_name    = {config.provider}_eks_cluster.main.name')
        lines.append(f'  node_group_name = "{pool["name"]}"')
        lines.append(f'  node_role_arn   = aws_iam_role.node.arn')
        lines.append(f'  instance_types  = ["{pool.get("instance_type", "t3.medium")}"]')
        lines.append(f'  scaling_config {{')
        lines.append(f'    desired_size = {pool.get("desired_size", 1)}')
        lines.append(f'    min_size     = {pool.get("min_size", 1)}')
        lines.append(f'    max_size     = {pool.get("max_size", 3)}')
        lines.append(f'  }}')
        lines.append(f'}}')
        lines.append(f'')

    return "\n".join(lines) + "\n"


def generate_variables_tf(config: TerraformConfig) -> str:
    """Generate Terraform variables.tf content."""
    lines = [
        f'variable "provider" {{',
        f'  description = "Cloud provider"',
        f'  type        = string',
        f'  default     = "{config.provider}"',
        f'}}',
        f'',
        f'variable "region" {{',
        f'  description = "Deployment region"',
        f'  type        = string',
        f'  default     = "{config.region}"',
        f'}}',
        f'',
        f'variable "cluster_name" {{',
        f'  description = "EKS cluster name"',
        f'  type        = string',
        f'  default     = "{config.cluster_name}"',
        f'}}',
        f'',
        f'variable "subnet_ids" {{',
        f'  description = "Subnet IDs for the cluster"',
        f'  type        = list(string)',
        f'  default     = []',
        f'}}',
    ]

    return "\n".join(lines) + "\n"


def generate_outputs_tf(config: TerraformConfig) -> str:
    """Generate Terraform outputs.tf content."""
    lines = [
        f'output "cluster_name" {{',
        f'  description = "EKS cluster name"',
        f'  value       = "{config.cluster_name}"',
        f'}}',
        f'',
        f'output "cluster_endpoint" {{',
        f'  description = "EKS cluster endpoint"',
        f'  value       = {config.provider}_eks_cluster.main.endpoint',
        f'}}',
        f'',
        f'output "region" {{',
        f'  description = "Deployment region"',
        f'  value       = "{config.region}"',
        f'}}',
        f'',
        f'output "provider" {{',
        f'  description = "Cloud provider"',
        f'  value       = "{config.provider}"',
        f'}}',
    ]

    return "\n".join(lines) + "\n"
