"""Tests for the deployment package: container, K8s, Helm, Terraform."""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.deployment import (
    ContainerConfig,
    DeploymentConfig,
    HelmValues,
    K8sManifest,
    TerraformConfig,
)
from apex_autopilot_optimization.deployment.container import (
    generate_docker_compose,
    generate_dockerfile,
)
from apex_autopilot_optimization.deployment.helm import generate_chart, generate_values
from apex_autopilot_optimization.deployment.k8s import (
    generate_configmap,
    generate_deployment,
    generate_hpa,
    generate_pdb,
    generate_service,
)
from apex_autopilot_optimization.deployment.terraform import (
    generate_main_tf,
    generate_outputs_tf,
    generate_variables_tf,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _container_config() -> ContainerConfig:
    return ContainerConfig(
        image="apex-autopilot",
        tag="1.0.0",
        registry="ghcr.io/example",
        ports=[8080, 9090],
        env_vars={"LOG_LEVEL": "info", "WORKERS": "4"},
        resources={"cpu": "500m", "memory": "512Mi"},
        health_check="/healthz",
    )


def _k8s_manifest() -> K8sManifest:
    return K8sManifest(
        apiVersion="apps/v1",
        kind="Deployment",
        metadata={"name": "apex-autopilot", "namespace": "default"},
        spec={"replicas": 3},
    )


def _helm_values() -> HelmValues:
    return HelmValues(
        replicaCount=3,
        image={"repository": "ghcr.io/example/apex-autopilot", "tag": "1.0.0"},
        service={"type": "ClusterIP", "port": 8080},
        resources={"cpu": "500m", "memory": "512Mi"},
        autoscaling={"enabled": True, "minReplicas": 2, "maxReplicas": 10},
    )


def _terraform_config() -> TerraformConfig:
    return TerraformConfig(
        provider="aws",
        region="us-west-2",
        cluster_name="apex-cluster",
        node_pools=[{"name": "default", "instance_type": "t3.medium", "min_size": 1, "max_size": 5}],
    )


# ---------------------------------------------------------------------------
# DeploymentConfig
# ---------------------------------------------------------------------------


class TestDeploymentConfig:
    def test_create_deployment_config(self):
        cfg = DeploymentConfig(
            name="apex-autopilot",
            version="1.0.0",
            container=_container_config(),
            k8s=_k8s_manifest(),
            helm=_helm_values(),
            terraform=_terraform_config(),
        )
        assert cfg.name == "apex-autopilot"
        assert cfg.version == "1.0.0"
        assert cfg.container.image == "apex-autopilot"
        assert cfg.k8s.kind == "Deployment"
        assert cfg.helm.replicaCount == 3
        assert cfg.terraform.provider == "aws"

    def test_deployment_config_defaults(self):
        cfg = DeploymentConfig(
            name="test",
            version="0.1.0",
            container=_container_config(),
            k8s=_k8s_manifest(),
            helm=_helm_values(),
            terraform=_terraform_config(),
        )
        assert cfg.name == "test"
        assert cfg.version == "0.1.0"


# ---------------------------------------------------------------------------
# ContainerConfig
# ---------------------------------------------------------------------------


class TestContainerConfig:
    def test_create_container_config(self):
        cfg = _container_config()
        assert cfg.image == "apex-autopilot"
        assert cfg.tag == "1.0.0"
        assert cfg.registry == "ghcr.io/example"
        assert cfg.ports == [8080, 9090]
        assert cfg.env_vars == {"LOG_LEVEL": "info", "WORKERS": "4"}
        assert cfg.resources == {"cpu": "500m", "memory": "512Mi"}
        assert cfg.health_check == "/healthz"

    def test_container_config_full_image(self):
        cfg = _container_config()
        full_image = f"{cfg.registry}/{cfg.image}:{cfg.tag}"
        assert full_image == "ghcr.io/example/apex-autopilot:1.0.0"


# ---------------------------------------------------------------------------
# Dockerfile Generation
# ---------------------------------------------------------------------------


class TestDockerfileGeneration:
    def test_generate_dockerfile_contains_base_image(self):
        cfg = _container_config()
        dockerfile = generate_dockerfile(cfg)
        assert "FROM" in dockerfile
        assert "python:3.11-slim" in dockerfile

    def test_generate_dockerfile_contains_ports(self):
        cfg = _container_config()
        dockerfile = generate_dockerfile(cfg)
        assert "8080" in dockerfile
        assert "9090" in dockerfile

    def test_generate_dockerfile_contains_env_vars(self):
        cfg = _container_config()
        dockerfile = generate_dockerfile(cfg)
        assert "LOG_LEVEL" in dockerfile
        assert "info" in dockerfile
        assert "WORKERS" in dockerfile

    def test_generate_dockerfile_contains_healthcheck(self):
        cfg = _container_config()
        dockerfile = generate_dockerfile(cfg)
        assert "HEALTHCHECK" in dockerfile
        assert "/healthz" in dockerfile

    def test_generate_dockerfile_contains_copy(self):
        cfg = _container_config()
        dockerfile = generate_dockerfile(cfg)
        assert "COPY" in dockerfile
        assert "pip install" in dockerfile


# ---------------------------------------------------------------------------
# Docker Compose Generation
# ---------------------------------------------------------------------------


class TestDockerComposeGeneration:
    def test_generate_docker_compose_contains_service(self):
        cfg = _container_config()
        compose = generate_docker_compose(cfg)
        assert "apex-autopilot" in compose

    def test_generate_docker_compose_contains_image(self):
        cfg = _container_config()
        compose = generate_docker_compose(cfg)
        assert "ghcr.io/example/apex-autopilot:1.0.0" in compose

    def test_generate_docker_compose_contains_ports(self):
        cfg = _container_config()
        compose = generate_docker_compose(cfg)
        assert "8080" in compose
        assert "9090" in compose

    def test_generate_docker_compose_contains_env(self):
        cfg = _container_config()
        compose = generate_docker_compose(cfg)
        assert "LOG_LEVEL" in compose

    def test_generate_docker_compose_contains_healthcheck(self):
        cfg = _container_config()
        compose = generate_docker_compose(cfg)
        assert "/healthz" in compose


# ---------------------------------------------------------------------------
# K8s Manifest Generation
# ---------------------------------------------------------------------------


class TestK8sDeployment:
    def test_generate_deployment_structure(self):
        cfg = _container_config()
        dep = generate_deployment(cfg)
        assert dep["apiVersion"] == "apps/v1"
        assert dep["kind"] == "Deployment"
        assert "metadata" in dep
        assert "spec" in dep

    def test_generate_deployment_replicas(self):
        cfg = _container_config()
        dep = generate_deployment(cfg)
        assert dep["spec"]["replicas"] == 1

    def test_generate_deployment_container(self):
        cfg = _container_config()
        dep = generate_deployment(cfg)
        containers = dep["spec"]["template"]["spec"]["containers"]
        assert len(containers) == 1
        assert containers[0]["image"] == "ghcr.io/example/apex-autopilot:1.0.0"


class TestK8sService:
    def test_generate_service_structure(self):
        cfg = _container_config()
        svc = generate_service(cfg)
        assert svc["apiVersion"] == "v1"
        assert svc["kind"] == "Service"
        assert "metadata" in svc
        assert "spec" in svc

    def test_generate_service_ports(self):
        cfg = _container_config()
        svc = generate_service(cfg)
        ports = svc["spec"]["ports"]
        assert len(ports) == 2
        port_numbers = [p["port"] for p in ports]
        assert 8080 in port_numbers
        assert 9090 in port_numbers


class TestK8sConfigMap:
    def test_generate_configmap_structure(self):
        cfg = _container_config()
        cm = generate_configmap(cfg)
        assert cm["apiVersion"] == "v1"
        assert cm["kind"] == "ConfigMap"
        assert "metadata" in cm
        assert "data" in cm

    def test_generate_configmap_data(self):
        cfg = _container_config()
        cm = generate_configmap(cfg)
        assert cm["data"]["LOG_LEVEL"] == "info"
        assert cm["data"]["WORKERS"] == "4"


class TestK8sHPA:
    def test_generate_hpa_structure(self):
        cfg = _container_config()
        hpa = generate_hpa(cfg)
        assert hpa["apiVersion"] == "autoscaling/v2"
        assert hpa["kind"] == "HorizontalPodAutoscaler"
        assert "metadata" in hpa
        assert "spec" in hpa

    def test_generate_hpa_scaling(self):
        cfg = _container_config()
        hpa = generate_hpa(cfg)
        assert hpa["spec"]["minReplicas"] == 1
        assert hpa["spec"]["maxReplicas"] >= 2


class TestK8sPDB:
    def test_generate_pdb_structure(self):
        cfg = _container_config()
        pdb = generate_pdb(cfg)
        assert pdb["apiVersion"] == "policy/v1"
        assert pdb["kind"] == "PodDisruptionBudget"
        assert "metadata" in pdb
        assert "spec" in pdb

    def test_generate_pdb_min_available(self):
        cfg = _container_config()
        pdb = generate_pdb(cfg)
        assert pdb["spec"]["minAvailable"] >= 1


# ---------------------------------------------------------------------------
# Helm Values Generation
# ---------------------------------------------------------------------------


class TestHelmValues:
    def test_generate_values_structure(self):
        cfg = _container_config()
        values = generate_values(cfg)
        assert "replicaCount" in values
        assert "image" in values
        assert "service" in values
        assert "resources" in values
        assert "autoscaling" in values

    def test_generate_values_image(self):
        cfg = _container_config()
        values = generate_values(cfg)
        assert values["image"]["repository"] == "ghcr.io/example/apex-autopilot"
        assert values["image"]["tag"] == "1.0.0"

    def test_generate_values_service(self):
        cfg = _container_config()
        values = generate_values(cfg)
        assert values["service"]["port"] == 8080

    def test_generate_values_replica_count(self):
        cfg = _container_config()
        values = generate_values(cfg)
        assert values["replicaCount"] == 1


# ---------------------------------------------------------------------------
# Helm Chart Generation
# ---------------------------------------------------------------------------


class TestHelmChart:
    def test_generate_chart_structure(self):
        cfg = _container_config()
        chart = generate_chart(cfg)
        assert "apiVersion" in chart
        assert "name" in chart
        assert "version" in chart

    def test_generate_chart_name(self):
        cfg = _container_config()
        chart = generate_chart(cfg)
        assert chart["name"] == "apex-autopilot"

    def test_generate_chart_version(self):
        cfg = _container_config()
        chart = generate_chart(cfg)
        assert chart["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Terraform Config Generation
# ---------------------------------------------------------------------------


class TestTerraformConfig:
    def test_create_terraform_config(self):
        cfg = _terraform_config()
        assert cfg.provider == "aws"
        assert cfg.region == "us-west-2"
        assert cfg.cluster_name == "apex-cluster"
        assert len(cfg.node_pools) == 1
        assert cfg.node_pools[0]["name"] == "default"


# ---------------------------------------------------------------------------
# Terraform main.tf Generation
# ---------------------------------------------------------------------------


class TestTerraformMain:
    def test_generate_main_tf_contains_provider(self):
        cfg = _terraform_config()
        main_tf = generate_main_tf(cfg)
        assert "provider" in main_tf
        assert "aws" in main_tf

    def test_generate_main_tf_contains_region(self):
        cfg = _terraform_config()
        main_tf = generate_main_tf(cfg)
        assert "us-west-2" in main_tf

    def test_generate_main_tf_contains_cluster(self):
        cfg = _terraform_config()
        main_tf = generate_main_tf(cfg)
        assert "apex-cluster" in main_tf

    def test_generate_main_tf_contains_node_pools(self):
        cfg = _terraform_config()
        main_tf = generate_main_tf(cfg)
        assert "default" in main_tf
        assert "t3.medium" in main_tf


# ---------------------------------------------------------------------------
# Terraform variables.tf Generation
# ---------------------------------------------------------------------------


class TestTerraformVariables:
    def test_generate_variables_tf_contains_region(self):
        cfg = _terraform_config()
        variables_tf = generate_variables_tf(cfg)
        assert "region" in variables_tf
        assert "us-west-2" in variables_tf

    def test_generate_variables_tf_contains_cluster_name(self):
        cfg = _terraform_config()
        variables_tf = generate_variables_tf(cfg)
        assert "cluster_name" in variables_tf
        assert "apex-cluster" in variables_tf

    def test_generate_variables_tf_contains_provider(self):
        cfg = _terraform_config()
        variables_tf = generate_variables_tf(cfg)
        assert "provider" in variables_tf
        assert "aws" in variables_tf


# ---------------------------------------------------------------------------
# Terraform outputs.tf Generation
# ---------------------------------------------------------------------------


class TestTerraformOutputs:
    def test_generate_outputs_tf_contains_cluster_name(self):
        cfg = _terraform_config()
        outputs_tf = generate_outputs_tf(cfg)
        assert "cluster_name" in outputs_tf
        assert "apex-cluster" in outputs_tf

    def test_generate_outputs_tf_contains_region(self):
        cfg = _terraform_config()
        outputs_tf = generate_outputs_tf(cfg)
        assert "region" in outputs_tf
        assert "us-west-2" in outputs_tf

    def test_generate_outputs_tf_contains_provider(self):
        cfg = _terraform_config()
        outputs_tf = generate_outputs_tf(cfg)
        assert "provider" in outputs_tf
        assert "aws" in outputs_tf
