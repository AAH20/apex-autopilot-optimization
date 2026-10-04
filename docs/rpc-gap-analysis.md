# RPC & Service-to-Service Communication Gap Analysis

**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Status:** No RPC, no gRPC, no service-to-service communication  

---

## Executive Summary

The apex-autopilot-optimization project is a **pure Python library** (20 modules, 365 tests) implementing autopilot algorithms (planning, optimization, estimation, control, safety, swarm). It has **zero RPC infrastructure** — no gRPC, no service definitions, no inter-service communication patterns. This report identifies the gaps and provides a concrete implementation roadmap.

---

## 1. What RPC Is Needed

### 1.1 Current State

| Aspect | Current State |
|---|---|
| Architecture | Monolithic Python library |
| Communication | In-process function calls only |
| Service boundaries | None — all modules are importable packages |
| External interfaces | CLI (`apex-autopilot`) + Python API |
| Concurrency | None — single-threaded, synchronous |
| Deployment | Library dependency, not a service |

### 1.2 Missing RPC Capabilities

The project needs RPC for these **concrete use cases**:

| Use Case | Description | Priority |
|---|---|---|
| **Remote planning service** | Offload A*/RRT/PRM/Hybrid A* planning to a dedicated worker | HIGH |
| **Trajectory optimization service** | Minimum-snap optimization is CPU-bound; needs worker pool | HIGH |
| **Swarm coordination** | Multi-vehicle task allocation and formation control across nodes | HIGH |
| **Telemetry ingestion** | Stream EKF state estimates from vehicle telemetry | MEDIUM |
| **Safety filter as a service** | CBF safety filtering as a gatekeeper before actuator commands | MEDIUM |
| **Benchmark/evaluation service** | Run benchmarks and evaluations asynchronously | MEDIUM |
| **Fleet management API** | Expose autopilot capabilities to external fleet orchestrators | MEDIUM |

### 1.3 Why Not Just a Library?

The current design works for single-vehicle, single-process use. But the project's own README describes a **macro architecture** with PX4/ArduPilot adapters, ROS 2 bridges, and DDS bridges — all of which imply distributed, multi-process communication that the library alone cannot provide.

---

## 2. How to Implement gRPC

### 2.1 Recommended Stack

| Component | Recommendation | Rationale |
|---|---|---|
| **Framework** | gRPC (grpcio) | Industry standard, HTTP/2, protobuf, streaming, 7-10x faster than REST/JSON |
| **Proto compiler** | `grpcio-tools` | Python-native code generation |
| **Service discovery** | Kubernetes DNS / Consul | For production deployment |
| **Observability** | OpenTelemetry + grpc-opentelemetry | Tracing, metrics, logging |
| **Health checks** | `grpc-health-probe` | Standard gRPC health checking |
| **API gateway** | grpc-gateway | REST ↔ gRPC translation for external clients |

### 2.2 Why gRPC Over Alternatives

| Alternative | Verdict | Reason |
|---|---|---|
| **nameko** | ❌ Rejected | Dormant since Dec 2021, Python ≤3.9 only, AMQP/RabbitMQ dependency too heavy |
| **PyCats** | ❌ Rejected | Functional programming library, not an RPC framework |
| **RPyC** | ❌ Rejected | Python-only, no contract enforcement, security concerns |
| **rpc.py** | ⚠️ Viable | ASGI-based, but immature (v0.6.0), small community |
| **REST/FastAPI** | ⚠️ Complementary | Good for external APIs, not for internal service-to-service |
| **ZeroMQ/zerorpc** | ⚠️ Viable | Fast but no contract enforcement, no streaming semantics |
| **gRPC** | ✅ **Recommended** | Contract-first, streaming, production-proven, polyglot |

### 2.3 Proto File Structure

```
protos/
├── apex/
│   ├── common/
│   │   ├── types.proto          # Pose3D, StateVector, Trajectory, Waypoint
│   │   └── enums.proto          # VehicleType, ComplexityClass
│   ├── planning/
│   │   ├── planning.proto       # PlanningService (A*, RRT, PRM, Hybrid A*)
│   │   └── planning_messages.proto
│   ├── optimization/
│   │   └── optimization.proto   # OptimizationService (minimum snap)
│   ├── estimation/
│   │   └── estimation.proto     # EstimationService (EKF predict/update)
│   ├── control/
│   │   └── control.proto        # ControlService (MPC track)
│   ├── safety/
│   │   └── safety.proto         # SafetyService (CBF filter)
│   ├── swarm/
│   │   └── swarm.proto          # SwarmService (task allocation, formation)
│   └── benchmark/
│       └── benchmark.proto      # BenchmarkService
```

### 2.4 Example Proto Definition

```protobuf
// protos/apex/planning/planning.proto
syntax = "proto3";

package apex.planning;

import "apex/common/types.proto";

service PlanningService {
  // Unary: plan a path from start to goal
  rpc Plan(PlanRequest) returns (PlanResponse);
  
  // Server streaming: stream waypoints as they are computed
  rpc PlanStream(PlanRequest) returns (stream Waypoint);
  
  // Bidirectional streaming: real-time replanning with obstacle updates
  rpc Replan(stream ReplanRequest) returns (stream PlanResponse);
}

message PlanRequest {
  apex.common.StateVector start = 1;
  apex.common.Waypoint goal = 2;
  repeated apex.common.Obstacle obstacles = 3;
  apex.common.VehicleType vehicle_type = 4;
  AlgorithmConfig config = 5;
}

message PlanResponse {
  bool success = 1;
  repeated apex.common.Waypoint waypoints = 2;
  float computation_time_ms = 3;
  int32 iterations = 4;
  float cost = 5;
  string message = 6;
}

message AlgorithmConfig {
  oneof algorithm {
    AStarConfig astar = 1;
    RRTConfig rrt = 2;
    PRMConfig prm = 3;
    HybridAStarConfig hybrid_astar = 4;
  }
}
```

### 2.5 Implementation Pattern

```python
# src/apex_autopilot_optimization/grpc/planning_server.py
from concurrent import futures
import grpc
from apex.planning import planning_pb2_grpc
from apex.planning.planning_pb2 import PlanResponse
from apex_autopilot_optimization.planning.astar import AStarPlanner
from apex_autopilot_optimization.core.types import PlanningProblem

class PlanningServicer(planning_pb2_grpc.PlanningServiceServicer):
    def __init__(self):
        self.planner = AStarPlanner()
    
    def Plan(self, request, context):
        problem = self._to_domain(request)
        result = self.planner.plan(problem)
        return self._to_proto(result)
    
    def PlanStream(self, request, context):
        problem = self._to_domain(request)
        for waypoint in self.planner.plan_iter(problem):
            yield self._to_proto_waypoint(waypoint)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    planning_pb2_grpc.add_PlanningServiceServicer_to_server(
        PlanningServicer(), server
    )
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()
```

---

## 3. Service-to-Service Patterns

### 3.1 Recommended Patterns for This Project

| Pattern | Use Case | Implementation |
|---|---|---|
| **Request-Response (Unary)** | Planning, optimization, safety filter | Standard gRPC unary RPC |
| **Server Streaming** | Telemetry ingestion, trajectory generation | `rpc StreamTrajectory(...) returns (stream StateVector)` |
| **Client Streaming** | Batch benchmark runs, multi-vehicle state upload | `rpc UploadTelemetry(stream TelemetryFrame) returns (Ack)` |
| **Bidirectional Streaming** | Real-time swarm coordination, replanning | `rpc Coordinate(stream SwarmState) returns (stream SwarmCommand)` |
| **Circuit Breaker** | Safety filter calls, actuator commands | `pybreaker` or custom interceptor |
| **Retry with Backoff** | Transient failures in planning/optimization | gRPC built-in retry + `tenacity` |
| **Deadline/Timeout** | Real-time control loops | gRPC context deadline |
| **Service Mesh** | Production traffic management | Istio/Linkerd sidecar |

### 3.2 Service Decomposition

```
┌─────────────────────────────────────────────────────────┐
│                    API Gateway (grpc-gateway)            │
│                   REST ↔ gRPC translation                │
└────────────┬────────────────────────────────────────────┘
             │
    ┌────────┼────────┬────────┬────────┬────────┬────────┐
    │        │        │        │        │        │        │
    ▼        ▼        ▼        ▼        ▼        ▼        ▼
┌───────┐┌───────┐┌───────┐┌───────┐┌───────┐┌───────┐┌───────┐
│Planning││Optim. ││Estim. ││Control││Safety ││ Swarm ││Bench- │
│Service ││Service││Service││Service││Service││Service││mark   │
│:50051  ││:50052 ││:50053 ││:50054 ││:50055 ││:50056 ││:50057 │
└───────┘└───────┘└───────┘└───────┘└───────┘└───────┘└───────┘
    │        │        │        │        │        │        │
    └────────┴────────┴────────┼────────┴────────┴────────┘
                              │
                    ┌─────────┴─────────┐
                    │   Core Types       │
                    │  (shared proto)    │
                    └───────────────────┘
```

### 3.3 Inter-Service Communication Flow

```
Vehicle Telemetry → EstimationService (EKF)
                        │
                        ▼
                  PlanningService (A*/RRT)
                        │
                        ▼
               OptimizationService (Min Snap)
                        │
                        ▼
                  SafetyService (CBF filter)
                        │
                        ▼
                  ControlService (MPC)
                        │
                        ▼
                  Actuator Commands
```

### 3.4 Event-Driven Patterns (Complementary)

For asynchronous, decoupled communication:

| Event | Publisher | Subscribers |
|---|---|---|
| `trajectory_computed` | OptimizationService | SafetyService, BenchmarkService |
| `safety_violation` | SafetyService | ControlService, DiagnosticsService |
| `task_allocated` | SwarmService | PlanningService (per vehicle) |
| `vehicle_state_updated` | EstimationService | PlanningService, SwarmService |

**Implementation:** Use a message broker (NATS, RabbitMQ, or Kafka) alongside gRPC for event-driven flows. gRPC for synchronous, broker for asynchronous.

---

## 4. How to Maintain Service Contracts

### 4.1 Contract-First Development

| Practice | Implementation |
|---|---|
| **Proto as source of truth** | All service interfaces defined in `.proto` files before implementation |
| **Versioned packages** | `package apex.planning.v1;` — bump to `v2` for breaking changes |
| **Backward compatibility** | Never remove fields; deprecate with `deprecated = true` |
| **Field numbers are permanent** | Never reuse field numbers; reserve deleted field numbers |
| **Shared types in common package** | `apex/common/types.proto` imported by all services |

### 4.2 Contract Testing

```python
# tests/contract/test_planning_contract.py
"""Contract tests: verify proto ↔ domain type alignment."""
import pytest
from apex.planning import planning_pb2
from apex_autopilot_optimization.core.types import Pose3D, StateVector

def test_pose3d_proto_roundtrip():
    """Proto Pose3D must preserve all domain fields."""
    pose = Pose3D(x=1.0, y=2.0, z=3.0, roll=0.1, pitch=0.2, yaw=0.3)
    proto = to_proto(pose)
    restored = from_proto(proto)
    assert restored == pose

def test_plan_request_has_required_fields():
    """PlanRequest must have start, goal, vehicle_type."""
    req = planning_pb2.PlanRequest()
    assert req.HasField("start") or req.start is not None
    assert req.HasField("goal") or req.goal is not None
```

### 4.3 Contract Maintenance Workflow

```
1. Define .proto files in protos/
2. Generate Python stubs: python -m grpc_tools.protoc ...
3. Implement servicer against domain types
4. Write contract tests (proto ↔ domain roundtrip)
5. Write integration tests (real gRPC calls)
6. CI: verify proto changes don't break existing clients
7. Version bump for breaking changes
```

### 4.4 Breaking Change Policy

| Change Type | Policy |
|---|---|
| Add new field | ✅ Safe — old clients ignore unknown fields |
| Add new RPC method | ✅ Safe — old clients don't call it |
| Remove field | ❌ Breaking — deprecate first, remove in next major version |
| Change field type | ❌ Breaking — add new field, deprecate old |
| Change field number | ❌ Breaking — field numbers are permanent |
| Rename field | ⚠️ Safe if JSON name preserved, but proto name change is breaking for codegen |

### 4.5 Tooling for Contract Maintenance

| Tool | Purpose |
|---|---|
| `buf` | Proto linting, breaking change detection |
| `protoc-gen-validate` | Field validation rules in proto |
| `grpc-gateway` | Auto-generate REST endpoints from proto |
| `grpcurl` | CLI for testing gRPC services |
| `ghz` | gRPC benchmarking and load testing |

---

## 5. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Add `grpcio`, `grpcio-tools` to `pyproject.toml`
- [ ] Create `protos/` directory structure
- [ ] Define `common/types.proto` with core domain types
- [ ] Set up `buf` for linting and breaking change detection
- [ ] Generate Python stubs and verify import

### Phase 2: Core Services (Week 3-4)
- [ ] Implement `PlanningService` (A*, RRT, PRM, Hybrid A*)
- [ ] Implement `OptimizationService` (minimum snap)
- [ ] Implement `EstimationService` (EKF)
- [ ] Write contract tests for each service
- [ ] Write integration tests with real gRPC calls

### Phase 3: Advanced Services (Week 5-6)
- [ ] Implement `SafetyService` (CBF)
- [ ] Implement `ControlService` (MPC)
- [ ] Implement `SwarmService` (task allocation, formation)
- [ ] Add streaming RPCs (telemetry, trajectory)
- [ ] Add health checks and interceptors

### Phase 4: Production Hardening (Week 7-8)
- [ ] Add OpenTelemetry tracing
- [ ] Add circuit breakers and retry logic
- [ ] Set up grpc-gateway for REST API
- [ ] Add TLS/mTLS for service-to-service auth
- [ ] Kubernetes deployment manifests
- [ ] Load testing with `ghz`

---

## 6. Dependency Changes

### Current `pyproject.toml` dependencies:
```toml
dependencies = [
    "numpy>=1.26.0,<2.0.0",
    "scipy>=1.12.0,<2.0.0",
    "networkx>=3.2.0,<4.0.0",
    "pydantic>=2.5.0,<3.0.0",
    "structlog>=24.1.0,<25.0.0",
    "typer>=0.12.0,<1.0.0",
    "pyyaml>=6.0.1,<7.0.0",
]
```

### Required additions:
```toml
dependencies = [
    # ... existing ...
    "grpcio>=1.60.0,<2.0.0",
    "grpcio-tools>=1.60.0,<2.0.0",
    "grpcio-health-checking>=1.60.0,<2.0.0",
    "grpcio-opentelemetry>=1.60.0,<2.0.0",
    "opentelemetry-sdk>=1.20.0,<2.0.0",
    "opentelemetry-instrumentation-grpc>=0.41.0,<1.0.0",
    "pybreaker>=1.1.0,<2.0.0",
    "tenacity>=8.2.0,<9.0.0",
]

[project.optional-dependencies]
grpc = [
    "grpcio>=1.60.0,<2.0.0",
    "grpcio-tools>=1.60.0,<2.0.0",
    "grpc-gateway>=1.60.0,<2.0.0",
]
```

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Proto/domain type drift | HIGH | HIGH | Contract tests in CI, shared codegen |
| Breaking proto changes | MEDIUM | HIGH | Versioned packages, buf breaking detection |
| Latency from serialization | MEDIUM | MEDIUM | Benchmark, use streaming for large payloads |
| Operational complexity | MEDIUM | HIGH | Start with single service, add gradually |
| Team gRPC expertise | LOW | MEDIUM | Training, start with unary RPCs |

---

## 8. Summary of Gaps

| # | Gap | Severity | Phase |
|---|---|---|---|
| 1 | No proto files / service contracts | CRITICAL | 1 |
| 2 | No gRPC server implementations | CRITICAL | 2 |
| 3 | No gRPC client stubs | CRITICAL | 2 |
| 4 | No streaming support | HIGH | 3 |
| 5 | No health checks | HIGH | 3 |
| 6 | No interceptors (auth, logging, metrics) | HIGH | 3 |
| 7 | No service mesh integration | MEDIUM | 4 |
| 8 | No contract tests | HIGH | 2 |
| 9 | No API gateway | MEDIUM | 4 |
| 10 | No event-driven patterns | MEDIUM | 3 |
| 11 | No TLS/mTLS | HIGH | 4 |
| 12 | No deployment manifests | MEDIUM | 4 |

---

## References

- [gRPC Python](https://grpc.io/docs/languages/python/)
- [Buf - Protobuf Build Tool](https://buf.build/)
- [grpc-gateway](https://github.com/grpc-ecosystem/grpc-gateway)
- [OpenTelemetry gRPC Instrumentation](https://opentelemetry.io/docs/instrumentation/python/)
- [Nameko](https://github.com/nameko/nameko) — evaluated, rejected (dormant)
- [rpc.py](https://github.com/abersheeran/rpc.py) — evaluated, viable alternative
