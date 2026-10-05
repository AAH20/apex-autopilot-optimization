"""Terraform configuration and HCL generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TerraformConfig:
    """Terraform infrastructure configuration."""

    provider: str
    region: str
    cluster_name: str
    node_pools: list[dict[str, Any]] = field(default_factory=list)


def generate_main_tf(config: TerraformConfig) -> str:
    """Generate Terraform main.tf content."""
    lines = [
        "terraform {",
        "  required_providers {",
        f"    {config.provider} = {{",
        f'      source  = "hashicorp/{config.provider}"',
        '      version = ">= 4.0"',
        "    }",
        "  }",
        "}",
        "",
        f'provider "{config.provider}" {{',
        f'  region = "{config.region}"',
        "}",
        "",
        f'resource "{config.provider}_eks_cluster" "main" {{',
        f'  name     = "{config.cluster_name}"',
        "  role_arn = aws_iam_role.cluster.arn",
        "",
        "  vpc_config {",
        "    subnet_ids = var.subnet_ids",
        "  }",
        "}",
        "",
    ]

    for pool in config.node_pools:
        lines.append(f'resource "{config.provider}_eks_node_group" "{pool["name"]}" {{')
        lines.append(f"  cluster_name    = {config.provider}_eks_cluster.main.name")
        lines.append(f'  node_group_name = "{pool["name"]}"')
        lines.append("  node_role_arn   = aws_iam_role.node.arn")
        lines.append(f'  instance_types  = ["{pool.get("instance_type", "t3.medium")}"]')
        lines.append("  scaling_config {")
        lines.append(f"    desired_size = {pool.get('desired_size', 1)}")
        lines.append(f"    min_size     = {pool.get('min_size', 1)}")
        lines.append(f"    max_size     = {pool.get('max_size', 3)}")
        lines.append("  }")
        lines.append("}")
        lines.append("")

    return "\n".join(lines) + "\n"


def generate_variables_tf(config: TerraformConfig) -> str:
    """Generate Terraform variables.tf content."""
    lines = [
        'variable "provider" {',
        '  description = "Cloud provider"',
        "  type        = string",
        f'  default     = "{config.provider}"',
        "}",
        "",
        'variable "region" {',
        '  description = "Deployment region"',
        "  type        = string",
        f'  default     = "{config.region}"',
        "}",
        "",
        'variable "cluster_name" {',
        '  description = "EKS cluster name"',
        "  type        = string",
        f'  default     = "{config.cluster_name}"',
        "}",
        "",
        'variable "subnet_ids" {',
        '  description = "Subnet IDs for the cluster"',
        "  type        = list(string)",
        "  default     = []",
        "}",
    ]

    return "\n".join(lines) + "\n"


def generate_outputs_tf(config: TerraformConfig) -> str:
    """Generate Terraform outputs.tf content."""
    lines = [
        'output "cluster_name" {',
        '  description = "EKS cluster name"',
        f'  value       = "{config.cluster_name}"',
        "}",
        "",
        'output "cluster_endpoint" {',
        '  description = "EKS cluster endpoint"',
        f"  value       = {config.provider}_eks_cluster.main.endpoint",
        "}",
        "",
        'output "region" {',
        '  description = "Deployment region"',
        f'  value       = "{config.region}"',
        "}",
        "",
        'output "provider" {',
        '  description = "Cloud provider"',
        f'  value       = "{config.provider}"',
        "}",
    ]

    return "\n".join(lines) + "\n"
