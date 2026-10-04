# SDK & Client Library Gap Report

**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Version:** 0.1.0  
**Status:** No SDK, no client library, no language bindings

---

## Executive Summary

The apex-autopilot-optimization project is a **pure Python library** with 20 modules implementing 11 autopilot algorithms (A*, RRT, PRM, Hybrid A*, Minimum Snap, EKF, Task Allocation, Formation Control, CBF Safety, MPC, Core Types). It has **zero SDK surface area**: no HTTP/gRPC API server, no OpenAPI/Protobuf specification, no client SDKs, no language bindings, no code generation pipeline.

This report identifies the gaps and provides a concrete roadmap for SDK adoption.

---

## 1. What SDK Is Needed

### Current State

| Aspect | Status |
|---|---|
| Python package | ✅ `pip install apex-autopilot-optimization` |
| CLI entry point | ✅ `apex-autopilot` (typer-based) |
| HTTP/REST API | ❌ None |
| gRPC service | ❌ None |
| OpenAPI spec | ❌ None |
| Protobuf definitions | ❌ None |
| Client SDKs (any language) | ❌ None |
| Language bindings | ❌ None |
| Code generation pipeline | ❌ None |
| Examples directory | ❌ Empty |

### Gap Analysis

The project exposes **11 algorithm classes** with **synchronous, in-process Python APIs** only:

```
AStarPlanner.plan(problem: PlanningProblem) -> PlanningResult
RRTPlanner.plan(problem: PlanningProblem) -> PlanningResult
PRMPlanner.plan(problem: PlanningProblem) -> PlanningResult
HybridAStarPlanner.plan(problem: PlanningProblem) -> PlanningResult
MinimumSnapOptimizer.optimize(problem: PlanningProblem) -> PlanningResult
EKFEstimator.predict(dt: float) / update(measurement)
TaskAllocator.allocate(tasks, agents) -> dict
FormationController.compute_formation_positions(leader, num_agents) -> list[Pose3D]
CBFFilter.filter(state, control, obstacles) -> ControlInput
MPCController.compute_control(state, target) -> ControlInput
```

**What's missing for SDK adoption:**

1. **No network-accessible API** — All algorithms are in-process Python calls. No way to expose them as services.
2. **No serialization contract** — Core types are Python dataclasses with numpy dependencies. No language-neutral schema (no Protobuf, no JSON Schema, no OpenAPI).
3. **No server runtime** — No FastAPI/Flask/uvicorn HTTP server, no gRPC server, no ROS 2 node.
4. **No client abstraction** — Users must `pip install` the full package (with numpy/scipy) to use any algorithm. No lightweight client.
5. **No async support** — All APIs are synchronous. No asyncio interface for concurrent planning.
6. **No streaming** — No way to stream planning progress, trajectory updates, or swarm state.
7. **No authentication/authorization** — The `security.py` module provides HMAC/PBKDF2 primitives but no API auth layer.
8. **No examples** — The `examples/` directory is empty. No runnable SDK usage demos.

### SDK Needed: Three-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Language SDKs (generated)                 │
│  Python, TypeScript, Go, Rust, C++, Java            │
│  Generated from OpenAPI/Protobuf via CI pipeline    │
├─────────────────────────────────────────────────────┤
│  Layer 2: API Server (hand-written)                 │
│  FastAPI (REST) + gRPC (streaming)                  │
│  Auth, rate limiting, request validation            │
├─────────────────────────────────────────────────────┤
│  Layer 1: Core Library (existing)                   │
│  20 modules, 11 algorithms, pure Python             │
│  Exposed via internal Python API                    │
└─────────────────────────────────────────────────────┘
```

---

## 2. How to Generate Client Libraries

### Recommended Approach: OpenAPI-First with gRPC for Streaming

#### Option A: OpenAPI Generator (Recommended for REST)

**Tool:** `@openapitools/openapi-generator-cli` (supports 50+ languages)

**Pipeline:**
```bash
# 1. Define OpenAPI 3.1 spec (hand-written or generated from FastAPI)
# 2. Generate Python client
openapi-generator-cli generate \
  -i spec/openapi.yaml \
  -g python \
  -o sdks/python \
  --additional-properties=packageName=apex_autopilot_sdk,packageVersion=0.1.0

# 3. Generate TypeScript client
openapi-generator-cli generate \
  -i spec/openapi.yaml \
  -g typescript-axios \
  -o sdks/typescript \
  --additional-properties=npmName=@apex/autopilot-sdk,npmVersion=0.1.0

# 4. Generate Go client
openapi-generator-cli generate \
  -i spec/openapi.yaml \
  -g go \
  -o sdks/go \
  --additional-properties=packageName=apexautopilot,packageVersion=0.1.0

# 5. Generate Rust client
openapi-generator-cli generate \
  -i spec/openapi.yaml \
  -g rust \
  -o sdks/rust \
  --additional-properties=crateName=apex-autopilot,crateVersion=0.1.0
```

**Pros:** Free, open-source, 50+ languages, mature  
**Cons:** Default templates are unidiomatic; requires custom Mustache templates for quality

#### Option B: Speakeasy (Recommended for managed SDK generation)

**Tool:** Speakeasy CLI (speakeasy-api/speakeasy)

**Pipeline:**
```bash
# 1. Define OpenAPI spec
# 2. Configure Speakeasy
speakeasy generate sdk \
  --schema spec/openapi.yaml \
  --lang python \
  --out sdks/python

speakeasy generate sdk \
  --schema spec/openapi.yaml \
  --lang typescript \
  --out sdks/typescript
```

**Pros:** Idiomatic output, built-in CI/CD, type consolidation, validation (Zod/Pydantic)  
**Cons:** Managed service, requires account

#### Option C: Stainless (Recommended for enterprise-grade SDKs)

**Tool:** Stainless CLI

**Pipeline:**
```bash
# 1. Define OpenAPI spec
# 2. Configure Stainless
stainless generate \
  --openapi spec/openapi.yaml \
  --config stainless.yml
```

**Pros:** Best-in-class TypeScript/Python SDKs, semantic merge for custom code, diagnostics  
**Cons:** Paid service, requires account

#### Option D: gRPC/Protobuf (Recommended for streaming + performance)

**Tool:** `grpcio-tools` (Python), `buf` (modern Protobuf toolchain)

**Pipeline:**
```protobuf
// proto/apex/autopilot/v1/planning.proto
syntax = "proto3";
package apex.autopilot.v1;

service PlanningService {
  rpc Plan(PlanningRequest) returns (PlanningResponse);
  rpc StreamPlan(PlanningRequest) returns (stream PlanningResponse);
}

message PlanningRequest {
  VehicleType vehicle_type = 1;
  Pose3D start = 2;
  Pose3D goal = 3;
  repeated Waypoint waypoints = 4;
  repeated Obstacle obstacles = 5;
  OptimizationConstraint constraints = 6;
}

message PlanningResponse {
  bool success = 1;
  Trajectory trajectory = 2;
  double computation_time_ms = 3;
  uint32 iterations = 4;
  double cost = 5;
}
```

```bash
# Generate Python gRPC stubs
python -m grpc_tools.protoc \
  -I proto \
  --python_out=sdks/python \
  --pyi_out=sdks/python \
  --grpc_python_out=sdks/python \
  proto/apex/autopilot/v1/*.proto

# Generate TypeScript gRPC stubs
protoc \
  -I proto \
  --ts_out=sdks/typescript \
  --grpc-web_out=sdks/typescript \
  proto/apex/autopilot/v1/*.proto
```

**Pros:** First-class streaming, strongly typed, high performance, official generators  
**Cons:** Requires Protobuf toolchain, less human-readable than REST

### Recommended Hybrid Approach

| Surface | Protocol | Generator | Rationale |
|---|---|---|---|
| REST API | OpenAPI 3.1 | OpenAPI Generator | Broad language support, simple CRUD-like planning |
| Streaming API | gRPC | grpcio-tools | Real-time trajectory streaming, swarm state |
| Internal | Python API | N/A | Direct library usage, no network overhead |

---

## 3. What Language Bindings to Support

### Priority Matrix

| Priority | Language | Use Case | SDK Type | Generator |
|---|---|---|---|---|
| P0 | **Python** | Primary language, data science, ML integration | REST + gRPC | OpenAPI Generator + grpcio-tools |
| P0 | **TypeScript** | Web dashboards, ground control stations, Electron apps | REST + gRPC-Web | OpenAPI Generator |
| P1 | **Go** | High-performance ground control, edge deployment | REST + gRPC | OpenAPI Generator + protoc |
| P1 | **Rust** | Embedded systems, safety-critical, WASM | REST + gRPC | OpenAPI Generator + tonic |
| P2 | **C++** | PX4/ArduPilot integration, ROS 2 nodes | gRPC | protoc + gRPC C++ |
| P2 | **Java** | Android ground control, enterprise | REST + gRPC | OpenAPI Generator + protoc |
| P3 | **C#** | Unity simulation, Windows ground control | REST + gRPC | OpenAPI Generator + protoc |
| P3 | **Swift** | iOS ground control apps | REST | OpenAPI Generator |

### Language-Specific Considerations

**Python (P0):**
- Sync + async clients (httpx + asyncio)
- Pydantic v2 models (project already uses pydantic)
- Type stubs included
- numpy interop for trajectory data

**TypeScript (P0):**
- ESM + CJS bundles
- Axios or fetch-based HTTP client
- AsyncIterable for streaming
- Zod runtime validation

**Go (P1):**
- Context-aware HTTP client
- Struct tags for JSON
- goroutine-based streaming
- gofmt-compliant output

**Rust (P1):**
- async/await (tokio)
- serde serialization
- WASM target for browser
- Strong type safety

**C++ (P2):**
- gRPC C++ client
- ROS 2 node wrapper
- Header-only or shared library
- CMake integration

---

## 4. How to Maintain SDK Versioning

### Versioning Strategy: Semantic Versioning (SemVer)

**Format:** `MAJOR.MINOR.PATCH` (e.g., `0.1.0`)

| Change Type | Version Bump | Example |
|---|---|---|
| Bug fix, no API change | Patch | `0.1.0` → `0.1.1` |
| New feature, backward compatible | Minor | `0.1.0` → `0.2.0` |
| Breaking API change | Major | `0.1.0` → `1.0.0` |

### SDK Versioning Rules

1. **SDK version tracks API version** — SDK `0.2.0` corresponds to API `0.2.0`
2. **Independent patch releases** — SDK can release `0.2.1` for client-side bug fixes without API change
3. **Pre-release tags** — Use `0.2.0-alpha.1`, `0.2.0-beta.1`, `0.2.0-rc.1` for testing
4. **Deprecation policy** — Mark deprecated features in minor releases, remove in next major
5. **Lockstep releases** — All language SDKs release simultaneously with the same version number

### Versioning Pipeline

```
API Change → OpenAPI/Protobuf spec update → CI triggers →
  ├── Generate all language SDKs
  ├── Run SDK test suite (contract tests)
  ├── Bump version (semantic-release)
  ├── Tag release (v0.2.0)
  ├── Publish to package registries
  │   ├── PyPI (Python)
  │   ├── npm (TypeScript)
  │   ├── pkg.go.dev (Go)
  │   ├── crates.io (Rust)
  │   ├── Maven Central (Java)
  │   └── NuGet (C#)
  └── Update documentation
```

### Version Compatibility Matrix

| SDK Version | API Version | Python | TypeScript | Go | Rust |
|---|---|---|---|---|---|
| 0.1.x | 0.1.x | 3.11+ | 18+ | 1.21+ | 1.70+ |
| 0.2.x | 0.2.x | 3.11+ | 18+ | 1.21+ | 1.70+ |
| 1.0.x | 1.0.x | 3.11+ | 20+ | 1.22+ | 1.75+ |

### Automated Version Management

**Tools:**
- `semantic-release` — Automated version bumping from conventional commits
- `changesets` — Version management with changelogs
- `release-please` — Google's release automation

**CI/CD Integration:**
```yaml
# .github/workflows/release-sdk.yml
name: Release SDK
on:
  push:
    branches: [main]
    paths:
      - 'spec/openapi.yaml'
      - 'proto/**/*.proto'

jobs:
  generate-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate SDKs
        run: |
          openapi-generator-cli generate -i spec/openapi.yaml -g python -o sdks/python
          openapi-generator-cli generate -i spec/openapi.yaml -g typescript-axios -o sdks/typescript
          openapi-generator-cli generate -i spec/openapi.yaml -g go -o sdks/go
      - name: Run contract tests
        run: pytest tests/sdk/
      - name: Publish SDKs
        run: |
          # Publish to PyPI, npm, etc.
```

---

## 5. Implementation Roadmap

### Phase 1: API Specification (Week 1-2)

- [ ] Define OpenAPI 3.1 spec for all 11 algorithm endpoints
- [ ] Define Protobuf definitions for gRPC streaming service
- [ ] Add FastAPI server with request/response models
- [ ] Add authentication (API key + JWT)

### Phase 2: Server Implementation (Week 3-4)

- [ ] Implement FastAPI REST endpoints wrapping existing algorithms
- [ ] Implement gRPC service with streaming support
- [ ] Add request validation (Pydantic models)
- [ ] Add rate limiting and middleware
- [ ] Add OpenAPI documentation (Swagger UI)

### Phase 3: SDK Generation (Week 5-6)

- [ ] Set up OpenAPI Generator with custom Mustache templates
- [ ] Generate Python SDK (sync + async)
- [ ] Generate TypeScript SDK
- [ ] Generate Go SDK
- [ ] Generate Rust SDK
- [ ] Add contract tests for all SDKs

### Phase 4: CI/CD & Publishing (Week 7-8)

- [ ] Set up GitHub Actions for SDK generation
- [ ] Configure semantic-release
- [ ] Set up package registry publishing (PyPI, npm, crates.io)
- [ ] Add SDK usage examples
- [ ] Write SDK documentation

### Phase 5: Advanced Features (Week 9-12)

- [ ] Add WebSocket support for real-time streaming
- [ ] Add SDK middleware (retry, logging, metrics)
- [ ] Add SDK telemetry (opt-in)
- [ ] Add deprecation warnings
- [ ] Add migration guides

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| API design changes break SDKs | High | High | SemVer + deprecation policy |
| Generated SDKs are unidiomatic | Medium | Medium | Custom Mustache templates |
| Maintenance burden of multi-language SDKs | High | Medium | Start with Python + TypeScript only |
| numpy dependency in client SDKs | Medium | High | Use JSON arrays in API, convert to numpy server-side |
| Protobuf schema evolution | Medium | Medium | Follow Protobuf backward compatibility rules |
| Version skew between SDKs | Medium | Medium | Lockstep releases + compatibility matrix |

---

## 7. Recommendations

1. **Start with Python + TypeScript only** — These cover 90% of use cases (data science + web dashboards). Add Go/Rust later.

2. **Use OpenAPI Generator with custom templates** — Default templates are unidiomatic. Invest in custom Mustache templates for Python (Pydantic models) and TypeScript (Axios + Zod).

3. **Define the API spec first** — Write the OpenAPI spec before implementing the server. This ensures the contract is stable before SDK generation.

4. **Use FastAPI for the server** — FastAPI automatically generates OpenAPI specs from Pydantic models, keeping the spec and implementation in sync.

5. **Add gRPC for streaming only** — Use REST for simple request/response, gRPC for streaming trajectories and swarm state.

6. **Implement contract tests** — Test all SDKs against the API contract in CI. Use Prism or similar for mock server testing.

7. **Version lockstep** — Release all language SDKs simultaneously with the same version number.

8. **Document SDK usage** — Each SDK needs a README with installation, authentication, and usage examples.

---

## 8. Appendix: Current API Surface

### Core Types (14 dataclasses + 2 enums)

| Type | Fields | Module |
|---|---|---|
| `Pose3D` | x, y, z, roll, pitch, yaw | core/types.py |
| `Velocity3D` | vx, vy, vz, vroll, vpitch, vyaw | core/types.py |
| `StateVector` | pose, velocity, timestamp, metadata | core/types.py |
| `ControlInput` | throttle, roll_rate, pitch_rate, yaw_rate, timestamp | core/types.py |
| `Waypoint` | pose, speed, arrival_time, tolerance_m, hold_time_s | core/types.py |
| `Trajectory` | states, controls, timestamps, vehicle_type | core/types.py |
| `OptimizationConstraint` | name, constraint_type, lower_bound, upper_bound, params | core/types.py |
| `OptimizationObjective` | name, weight, minimize, params | core/types.py |
| `PlanningProblem` | vehicle_type, start, goal, waypoints, obstacles, constraints, objectives, time_horizon_s, resolution_m | core/types.py |
| `PlanningResult` | success, trajectory, computation_time_ms, iterations, cost, message, metadata | core/types.py |
| `BottleneckReport` | description, severity, category, complexity, source, url | core/types.py |
| `VehicleType` | UAV_FIXED_WING, UAV_MULTIROTOR, UAV_VTOL, GROUND_VEHICLE_* | core/types.py |
| `ComplexityClass` | P, NP_HARD, NP_COMPLETE, EXPTIME, PSPACE, APPROXIMATION, UNKNOWN | core/types.py |

### Algorithm Classes (11)

| Class | Method | Input | Output |
|---|---|---|---|
| `AStarPlanner` | `plan(problem)` | `PlanningProblem` | `PlanningResult` |
| `RRTPlanner` | `plan(problem)` | `PlanningProblem` | `PlanningResult` |
| `PRMPlanner` | `plan(problem)` | `PlanningProblem` | `PlanningResult` |
| `HybridAStarPlanner` | `plan(problem)` | `PlanningProblem` | `PlanningResult` |
| `MinimumSnapOptimizer` | `optimize(problem)` | `PlanningProblem` | `PlanningResult` |
| `EKFEstimator` | `predict(dt)` / `update(measurement)` | float / NDArray | None / None |
| `TaskAllocator` | `allocate(tasks, agents)` | list[Task] / list[Agent] | dict[int, list[int]] |
| `FormationController` | `compute_formation_positions(leader, num_agents)` | StateVector / int | list[Pose3D] |
| `CBFFilter` | `filter(state, control, obstacles)` | StateVector / ControlInput / list[dict] | ControlInput |
| `MPCController` | `compute_control(state, target)` | StateVector / StateVector | ControlInput |

---

*Report generated by SDK Gap Analysis — apex-autopilot-optimization v0.1.0*
