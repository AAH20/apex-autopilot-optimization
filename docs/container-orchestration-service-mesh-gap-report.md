# Container Orchestration & Service Mesh Gap Report

**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Scope:** Container orchestration, Kubernetes deployment, service mesh, service discovery  
**Status:** No container orchestration, no service mesh, no service discovery

---

## Executive Summary

The apex-autopilot-optimization project is a **pure Python library** (20 modules, 365 tests) implementing autopilot algorithms. It has **zero containerization, zero orchestration, zero service mesh, and zero service discovery** infrastructure. There are no Dockerfiles, no Kubernetes manifests, no Helm charts, no service mesh configurations, and no deployment automation of any kind.

The project's own architecture describes a distributed macro architecture with PX4/ArduPilot adapters, ROS 2 bridges, and DDS bridges — all of which imply multi-process, multi-node deployment that the current library-only distribution cannot support.

This report identifies the gaps across four dimensions and provides a concrete implementation roadmap.

---

## 1. What Orchestration Is Needed

### 1.1 Current State

| Aspect | Current State |
|---|---|
| Distribution | Python library (`pip install`) |
| Architecture | Monolithic single-process |
| Concurrency | None — single-threaded, synchronous |
| Deployment | Library dependency, not a service |
| Scaling | None — no horizontal or vertical scaling |
| Health checks | In-memory `HealthCheck` class (no HTTP endpoint) |
| Configuration | YAML files, no ConfigMap/Secret integration |
| Rolling updates | N/A — no deployment units |
| Resource management | No CPU/memory limits or requests |

### 1.2 Missing Orchestration Capabilities

| Capability | Description | Priority |
|---|---|---|
| **Container packaging** | Docker images for each service | CRITICAL |
| **Multi-service deployment** | Deploy planning, optimization, estimation, control as separate services | CRITICAL |
| **Horizontal scaling** | Scale planning workers based on queue depth | HIGH |
| **Rolling updates** | Zero-downtime deployments | HIGH |
| **Health probing** | Liveness/readiness probes for each service | HIGH |
| **Resource management** | CPU/memory requests and limits per service | HIGH |
| **Configuration management** | Externalized config via ConfigMaps/Secrets | HIGH |
| **Service discovery** | DNS-based or registry-based service location | HIGH |
| **Load balancing** | Distribute requests across service instances | HIGH |
| **Auto-scaling** | HPA based on CPU/memory/custom metrics | MEDIUM |
| **Graceful shutdown** | Drain connections before termination | MEDIUM |
| **Secrets management** | API keys, certificates, credentials | MEDIUM |

### 1.3 Why Orchestration Is Needed

The project's own README describes a **macro architecture** with:
- PX4/ArduPilot adapters (separate processes)
- ROS 2 bridges (separate processes)
- DDS bridges (separate processes)
- Swarm coordination (multi-vehicle, multi-node)
- Real-time control loops (200-500 Hz)

These are inherently distributed workloads. Without orchestration:
- Each module runs in a single process with no fault isolation
- A crash in planning takes down the entire autopilot
- No way to scale CPU-bound workloads (RRT, PRM, minimum snap)
- No way to deploy updates without downtime
- No way to manage configuration across environments

---

## 2. How to Implement Kubernetes

### 2.1 Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Kubernetes Cluster                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                  Ingress / API Gateway               │    │
│  │              (nginx-ingress or Traefik)              │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────┬───────────┼───────────┬──────────┬─────────┐  │
│  │          │           │           │          │         │  │
│  ▼          ▼           ▼           ▼          ▼         ▼  │
│ ┌─────┐ ┌───────┐ ┌─────────┐ ┌──────┐ ┌───────┐ ┌──────┐ │
│ │Plan │ │Optim. │ │Estimat. │ │Safety│ │Control│ │Swarm │ │
│ │Svc  │ │Svc    │ │Svc      │ │Svc  │ │Svc   │ │Svc  │ │
│ │:50051│ │:50052│ │:50053   │ │:50055│ │:50054│ │:50056│ │
│ └─────┘ └───────┘ └─────────┘ └──────┘ └───────┘ └──────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Observability Stack                     │    │
│  │  (Prometheus + Grafana + Jaeger + OTel Collector)    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Service Mesh (Istio/Linkerd)            │    │
│  │         mTLS, traffic management, telemetry          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Dockerfile Strategy

Each service gets its own Dockerfile. A shared base image reduces duplication:

```dockerfile
# Dockerfile.base
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[grpc]"

# Copy source
COPY src/ ./src/

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
```

```dockerfile
# Dockerfile.planning
FROM apex-autopilot-base:latest

EXPOSE 50051 8080

CMD ["python", "-m", "apex_autopilot_optimization.grpc.planning_server"]
```

### 2.3 Kubernetes Manifest Structure

```
k8s/
├── base/
│   ├── namespace.yaml
│   ├── configmap.yaml              # Non-secret configuration
│   ├── secret.yaml                 # API keys, credentials (encrypted)
│   ├── planning/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── pdb.yaml
│   ├── optimization/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── hpa.yaml
│   ├── estimation/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── control/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── safety/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── swarm/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── observability/
│       ├── prometheus/
│       ├── grafana/
│       └── jaeger/
├── overlays/
│   ├── development/
│   │   └── kustomization.yaml
│   ├── staging/
│   │   └── kustomization.yaml
│   └── production/
│       └── kustomization.yaml
└── helm/
    └── apex-autopilot/
        ├── Chart.yaml
        ├── values.yaml
        └── templates/
```

### 2.4 Example Deployment

```yaml
# k8s/base/planning/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: apex-planning
  namespace: apex-autopilot
  labels:
    app: apex-planning
    version: v1
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: apex-planning
  template:
    metadata:
      labels:
        app: apex-planning
        version: v1
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
    spec:
      containers:
        - name: planning
          image: apex-autopilot/planning:latest
          ports:
            - containerPort: 50051
              name: grpc
            - containerPort: 8080
              name: http
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 2Gi
          livenessProbe:
            grpc:
              port: 50051
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          envFrom:
            - configMapRef:
                name: apex-config
            - secretRef:
                name: apex-secrets
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: apex-planning
  namespace: apex-autopilot
spec:
  selector:
    app: apex-planning
  ports:
    - port: 50051
      targetPort: 50051
      name: grpc
    - port: 8080
      targetPort: 8080
      name: http
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: apex-planning-hpa
  namespace: apex-autopilot
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: apex-planning
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 1
          periodSeconds: 120
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: apex-planning-pdb
  namespace: apex-autopilot
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: apex-planning
```

### 2.5 CI/CD Pipeline

```yaml
# .github/workflows/deploy.yaml
name: Build and Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --cov

  build:
    needs: test
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [planning, optimization, estimation, control, safety, swarm]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: Dockerfile.${{ matrix.service }}
          push: true
          tags: |
            ghcr.io/${{ github.repository }}/${{ matrix.service }}:${{ github.sha }}
            ghcr.io/${{ github.repository }}/${{ matrix.service }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-kubectl@v3
      - run: |
          kubectl apply -k k8s/overlays/production/
          kubectl rollout status deployment/apex-planning -n apex-autopilot
```

### 2.6 Dependency Changes

```toml
# pyproject.toml — add to dependencies
dependencies = [
    # ... existing ...
    "grpcio>=1.60.0,<2.0.0",
    "grpcio-tools>=1.60.0,<2.0.0",
    "grpcio-health-checking>=1.60.0,<2.0.0",
    "opentelemetry-sdk>=1.24.0,<2.0.0",
    "opentelemetry-exporter-otlp-proto-grpc>=1.24.0,<2.0.0",
    "prometheus-client>=0.19.0,<1.0.0",
    "kubernetes>=28.1.0,<29.0.0",
]
```

---

## 3. What Service Mesh to Use

### 3.1 Evaluation Matrix

| Criterion | Istio | Linkerd | Consul Connect | Cilium |
|---|---|---|---|---|
| **Resource overhead** | High (Envoy sidecar) | Low (Rust proxy) | Medium (Envoy sidecar) | Low (eBPF) |
| **mTLS** | ✅ Automatic | ✅ Automatic | ✅ Automatic | ✅ Automatic |
| **Traffic splitting** | ✅ VirtualService | ✅ TrafficSplit | ✅ ServiceRouter | ✅ Ingress |
| **Observability** | ✅ Excellent | ✅ Good | ✅ Good | ✅ Good |
| **Learning curve** | Steep | Gentle | Moderate | Steep |
| **Production maturity** | ✅ Very high | ✅ High | ✅ High | ⚠️ Growing |
| **gRPC support** | ✅ Excellent | ✅ Good | ✅ Good | ✅ Good |
| **CNCF status** | Graduated | Graduated | N/A | Graduated |
| **Best for** | Large teams, complex routing | Simplicity, low overhead | HashiCorp ecosystem | Kernel-level networking |

### 3.2 Recommendation: Istio (Primary) with Linkerd (Alternative)

**Primary: Istio** — because:
- The project's RPC gap analysis already references Istio
- Best-in-class gRPC traffic management (VirtualService, DestinationRule)
- Automatic mTLS with strong identity (SPIFFE)
- Rich observability (Kiali dashboard, Prometheus integration)
- Most mature ecosystem for microservices
- CNCF graduated project

**Alternative: Linkerd** — because:
- 10x lower resource overhead (Rust proxy vs Envoy)
- Simpler operational model
- Better for resource-constrained edge deployments (Jetson Orin)
- Faster to operate for small teams

### 3.3 Istio Configuration

```yaml
# istio/gateway.yaml
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: apex-gateway
  namespace: apex-autopilot
spec:
  selector:
    istio: ingressgateway
  servers:
    - port:
        number: 80
        name: http
        protocol: HTTP
      hosts:
        - "api.apex-autopilot.example.com"
      tls:
        httpsRedirect: true
    - port:
        number: 443
        name: https
        protocol: HTTPS
      tls:
        mode: SIMPLE
        credentialName: apex-tls-secret
      hosts:
        - "api.apex-autopilot.example.com"
---
# istio/virtualservice.yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: apex-planning
  namespace: apex-autopilot
spec:
  hosts:
    - apex-planning
  http:
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: apex-planning
            subset: v2
          weight: 10
        - destination:
            host: apex-planning
            subset: v1
          weight: 90
    - route:
        - destination:
            host: apex-planning
            subset: v1
          weight: 100
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: gateway-error,connect-failure,refused-stream
      timeout: 10s
      fault:
        delay:
          percentage:
            value: 0.1
          fixedDelay: 5s
---
# istio/destinationrule.yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: apex-planning
  namespace: apex-autopilot
spec:
  host: apex-planning
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
    loadBalancer:
      simple: LEAST_CONN
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
---
# istio/peerauthentication.yaml — enforce mTLS
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: apex-autopilot
spec:
  mtls:
    mode: STRICT
---
# istio/authorizationpolicy.yaml — service-to-service auth
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: planning-policy
  namespace: apex-autopilot
spec:
  selector:
    matchLabels:
      app: apex-planning
  action: ALLOW
  rules:
    - from:
        - source:
            principals: ["cluster.local/ns/apex-autopilot/sa/apex-api-gateway"]
      to:
        - operation:
            methods: ["POST"]
            paths: ["/apex.planning.PlanningService/*"]
```

### 3.4 Linkerd Alternative

```yaml
# linkerd/service-profile.yaml
apiVersion: linkerd.io/v1alpha2
kind: ServiceProfile
metadata:
  name: apex-planning.apex-autopilot.svc.cluster.local
  namespace: apex-autopilot
spec:
  routes:
    - name: POST /apex.planning.PlanningService/Plan
      condition:
        method: POST
        pathRegex: /apex\.planning\.PlanningService/Plan
      timeout: 10s
      isRetryable: true
    - name: POST /apex.planning.PlanningService/PlanStream
      condition:
        method: POST
        pathRegex: /apex\.planning\.PlanningService/PlanStream
      timeout: 30s
      isRetryable: false
  retryBudget:
    retryRatio: 0.2
    minRetriesPerSecond: 10
    ttl: 10s
---
# linkerd/traffic-split.yaml
apiVersion: split.smi-spec.io/v1alpha4
kind: TrafficSplit
metadata:
  name: apex-planning
  namespace: apex-autopilot
spec:
  service: apex-planning
  backends:
    - service: apex-planning-v1
      weight: 900
    - service: apex-planning-v2
      weight: 100
```

---

## 4. How to Maintain Service Discovery

### 4.1 Current State

| Aspect | Current State |
|---|---|
| Service discovery | None — hardcoded imports |
| DNS | None |
| Registry | None |
| Health checking | In-memory `HealthCheck` class |
| Load balancing | None |
| Configuration | YAML files, no dynamic config |

### 4.2 Recommended Approach: Kubernetes Native + Consul Hybrid

For a Kubernetes-based deployment, use **Kubernetes DNS** as the primary service discovery mechanism, with **Consul** as an optional multi-cluster service registry.

### 4.3 Kubernetes DNS Service Discovery

Kubernetes provides built-in DNS-based service discovery:

```yaml
# Services are automatically discoverable via DNS
# Format: <service-name>.<namespace>.svc.cluster.local

# Example: planning service discovers optimization service
# DNS name: apex-optimization.apex-autopilot.svc.cluster.local
```

```python
# Python client using Kubernetes DNS
import grpc
import os

def get_service_endpoint(service_name: str, namespace: str = "apex-autopilot", port: int = 50051) -> str:
    """Build service endpoint from Kubernetes DNS."""
    # In-cluster: use DNS name
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return f"{service_name}.{namespace}.svc.cluster.local:{port}"
    # Local development: use port-forward
    return f"localhost:{port}"

# Usage
channel = grpc.insecure_channel(
    get_service_endpoint("apex-planning", port=50051)
)
stub = planning_pb2_grpc.PlanningServiceStub(channel)
```

### 4.4 Consul Service Discovery (Multi-Cluster)

For multi-cluster or hybrid deployments:

```python
# consul/service_discovery.py
import consul
from dataclasses import dataclass
from typing import List, Optional
import random

@dataclass(frozen=True)
class ServiceInstance:
    id: str
    name: str
    address: str
    port: int
    tags: List[str]
    health_status: str

class ConsulServiceDiscovery:
    """Consul-based service discovery for multi-cluster deployments."""
    
    def __init__(self, host: str = "localhost", port: int = 8500):
        self.client = consul.Consul(host=host, port=port)
    
    def register(
        self,
        name: str,
        service_id: str,
        address: str,
        port: int,
        tags: Optional[List[str]] = None,
        health_check_url: Optional[str] = None,
    ) -> None:
        """Register a service instance with Consul."""
        check = None
        if health_check_url:
            check = consul.Check.http(health_check_url, interval="10s", timeout="5s")
        
        self.client.agent.service.register(
            name=name,
            service_id=service_id,
            address=address,
            port=port,
            tags=tags or [],
            check=check,
        )
    
    def discover(self, name: str, healthy_only: bool = True) -> List[ServiceInstance]:
        """Discover healthy service instances."""
        index, services = self.client.health.service(
            name, passing=healthy_only
        )
        return [
            ServiceInstance(
                id=s["Service"]["ID"],
                name=s["Service"]["Service"],
                address=s["Service"]["Address"],
                port=s["Service"]["Port"],
                tags=s["Service"].get("Tags", []),
                health_status=s["Checks"][0]["Status"] if s["Checks"] else "unknown",
            )
            for s in services
        ]
    
    def get_instance(self, name: str) -> Optional[ServiceInstance]:
        """Get a healthy instance using client-side load balancing."""
        instances = self.discover(name, healthy_only=True)
        if not instances:
            return None
        return random.choice(instances)  # Simple round-robin alternative
    
    def deregister(self, service_id: str) -> None:
        """Deregister a service instance."""
        self.client.agent.service.deregister(service_id)
    
    def watch(self, name: str, callback) -> None:
        """Watch for service changes."""
        index = None
        while True:
            index, services = self.client.health.service(name, index=index, wait="10s")
            callback([s["Service"] for s in services])
```

### 4.5 Kubernetes Service Discovery (Native)

```python
# kubernetes/service_discovery.py
from kubernetes import client, config
from typing import List, Optional
import os

class KubernetesServiceDiscovery:
    """Kubernetes-native service discovery."""
    
    def __init__(self):
        # Load in-cluster config when running in a pod
        if os.getenv("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config()
        else:
            config.load_kube_config()
        self.v1 = client.CoreV1Api()
    
    def get_service_endpoints(
        self, name: str, namespace: str = "apex-autopilot"
    ) -> List[str]:
        """Get endpoint addresses for a service."""
        endpoints = self.v1.read_namespaced_endpoints(name, namespace)
        addresses = []
        for subset in endpoints.subsets or []:
            for address in subset.addresses or []:
                for port in subset.ports or []:
                    addresses.append(f"{address.ip}:{port.port}")
        return addresses
    
    def get_service_pods(
        self, label_selector: str, namespace: str = "apex-autopilot"
    ) -> List[dict]:
        """Get pods matching a label selector."""
        pods = self.v1.list_namespaced_pod(
            namespace, label_selector=label_selector
        )
        return [
            {
                "name": pod.metadata.name,
                "ip": pod.status.pod_ip,
                "status": pod.status.phase,
                "labels": pod.metadata.labels,
            }
            for pod in pods.items
            if pod.status.phase == "Running"
        ]
    
    def watch_services(
        self, namespace: str, callback
    ) -> None:
        """Watch for service changes."""
        watch = client.Watch()
        for event in watch.stream(
            self.v1.list_namespaced_service, namespace
        ):
            callback(event)
```

### 4.6 Service Discovery Abstraction

```python
# discovery/factory.py
from enum import Enum
from typing import Optional

class DiscoveryBackend(Enum):
    KUBERNETES = "kubernetes"
    CONSUL = "consul"
    DNS = "dns"
    STATIC = "static"

def create_discovery(
    backend: DiscoveryBackend,
    **kwargs
) -> ServiceDiscovery:
    """Factory for service discovery backends."""
    if backend == DiscoveryBackend.KUBERNETES:
        from .kubernetes_discovery import KubernetesServiceDiscovery
        return KubernetesServiceDiscovery(**kwargs)
    elif backend == DiscoveryBackend.CONSUL:
        from .consul_discovery import ConsulServiceDiscovery
        return ConsulServiceDiscovery(**kwargs)
    elif backend == DiscoveryBackend.DNS:
        from .dns_discovery import DNSDiscovery
        return DNSDiscovery(**kwargs)
    elif backend == DiscoveryBackend.STATIC:
        from .static_discovery import StaticDiscovery
        return StaticDiscovery(**kwargs)
    raise ValueError(f"Unknown backend: {backend}")
```

### 4.7 Health Check Integration

```python
# health/grpc_health.py
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

class GrpcHealthServicer(health_pb2_grpc.HealthServicer):
    """gRPC health checking for Kubernetes probes."""
    
    def __init__(self):
        self._server = health.HealthServicer()
        self._server.set("", health_pb2.HealthCheckResponse.SERVING)
    
    def Check(self, request, context):
        return self._server.Check(request, context)
    
    def Watch(self, request, context):
        return self._server.Watch(request, context)
    
    def set_serving(self, service: str, serving: bool):
        """Update health status for a service."""
        status = (
            health_pb2.HealthCheckResponse.SERVING
            if serving
            else health_pb2.HealthCheckResponse.NOT_SERVING
        )
        self._server.set(service, status)
```

---

## 5. Implementation Roadmap

### Phase 1: Containerization (Week 1-2)
- [ ] Create `Dockerfile.base` with Python 3.11 + dependencies
- [ ] Create per-service Dockerfiles (planning, optimization, estimation, control, safety, swarm)
- [ ] Add `.dockerignore`
- [ ] Build and test images locally
- [ ] Add health check endpoints to each service
- [ ] Push images to container registry

### Phase 2: Kubernetes Foundation (Week 3-4)
- [ ] Create `k8s/base/` directory structure
- [ ] Write Deployment + Service manifests for each service
- [ ] Create ConfigMap and Secret templates
- [ ] Set up Kustomize overlays (dev/staging/prod)
- [ ] Deploy to local cluster (kind/minikube)
- [ ] Verify service-to-service communication
- [ ] Add resource requests/limits
- [ ] Add liveness/readiness probes

### Phase 3: Service Mesh (Week 5-6)
- [ ] Install Istio (or Linkerd) in cluster
- [ ] Configure mTLS (STRICT mode)
- [ ] Create Gateway and VirtualService for external traffic
- [ ] Configure traffic splitting for canary deployments
- [ ] Add AuthorizationPolicy for service-to-service auth
- [ ] Verify observability (Kiali/Grafana dashboards)
- [ ] Load test with mesh enabled

### Phase 4: Service Discovery & Operations (Week 7-8)
- [ ] Implement service discovery abstraction layer
- [ ] Add Consul integration for multi-cluster (optional)
- [ ] Set up Prometheus + Grafana monitoring
- [ ] Set up Jaeger distributed tracing
- [ ] Configure HPA for auto-scaling
- [ ] Add PodDisruptionBudgets
- [ ] Document operational runbooks

### Phase 5: Production Hardening (Week 9-10)
- [ ] Add network policies
- [ ] Configure backup/restore
- [ ] Set up disaster recovery
- [ ] Add CI/CD pipeline
- [ ] Load test production configuration
- [ ] Security audit
- [ ] Documentation

---

## 6. Gap Summary

| # | Gap | Severity | Phase |
|---|---|---|---|
| 1 | No container packaging (Dockerfiles) | CRITICAL | 1 |
| 2 | No Kubernetes manifests | CRITICAL | 2 |
| 3 | No service mesh (Istio/Linkerd) | HIGH | 3 |
| 4 | No service discovery mechanism | HIGH | 4 |
| 5 | No health check endpoints | HIGH | 1 |
| 6 | No resource management (requests/limits) | HIGH | 2 |
| 7 | No auto-scaling (HPA) | MEDIUM | 4 |
| 8 | No rolling update strategy | HIGH | 2 |
| 9 | No secrets management | HIGH | 2 |
| 10 | No network policies | MEDIUM | 5 |
| 11 | No CI/CD pipeline | MEDIUM | 5 |
| 12 | No multi-cluster support | LOW | 4 |
| 13 | No PodDisruptionBudgets | MEDIUM | 4 |
| 14 | No canary deployment support | MEDIUM | 3 |
| 15 | No mTLS | HIGH | 3 |

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Resource overhead from sidecars | HIGH | MEDIUM | Use Linkerd for edge, Istio for core |
| Complexity of Istio | MEDIUM | HIGH | Start with Linkerd, migrate later |
| Cold start latency | MEDIUM | MEDIUM | Use pre-stop hooks, warm pools |
| gRPC + mesh compatibility | LOW | HIGH | Test thoroughly, use native gRPC load balancing |
| Team K8s expertise | MEDIUM | HIGH | Training, start with managed K8s (EKS/GKE) |
| Real-time constraints violated | LOW | HIGH | Dedicated node pool, priority classes, no mesh on real-time path |

---

## 8. References

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Istio Documentation](https://istio.io/docs/)
- [Linkerd Documentation](https://linkerd.io/docs/)
- [Consul Service Discovery](https://www.consul.io/docs/discovery)
- [gRPC Kubernetes Deployment](https://grpc.io/docs/languages/python/)
- [Kustomize](https://kustomize.io/)
- [Kubernetes HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Istio mTLS](https://istio.io/latest/docs/tasks/security/authentication/authn-policy/)
- [Linkerd Service Profiles](https://linkerd.io/2.12/features/service-profiles/)
