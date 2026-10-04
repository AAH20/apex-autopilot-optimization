# Serialization & Data Interchange Gap Report

**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Scope:** All 20 modules in `src/apex_autopilot_optimization/`

---

## Executive Summary

The project has **zero serialization infrastructure**. All 20 modules operate exclusively on in-memory Python dataclasses with no mechanism to persist, transmit, or interchange data. Three modules (`benchmark.py`, `evaluation.py`, `diagnostics.py`) have ad-hoc `to_dict()` methods that produce Python dicts — but these are not serialization (no bytes, no schema, no versioning, no cross-language support). The project depends on `pydantic`, `pyyaml`, and `structlog` but uses none of them for serialization.

---

## 1. Current State Assessment

### 1.1 Domain Types (core/types.py)

| Type | Fields | Serialization |
|------|--------|---------------|
| `Pose3D` | 6 floats | None |
| `Velocity3D` | 6 floats | None |
| `StateVector` | Pose3D + Velocity3D + timestamp + metadata dict | None |
| `ControlInput` | 4 floats + timestamp | None |
| `Waypoint` | Pose3D + speed + arrival_time + tolerance + hold_time | None |
| `Trajectory` | list[StateVector] + list[ControlInput] + NDArray + VehicleType | None |
| `OptimizationConstraint` | name + type + bounds + params dict | None |
| `OptimizationObjective` | name + weight + minimize + params dict | None |
| `PlanningProblem` | VehicleType + StateVector + Waypoint + lists + floats | None |
| `PlanningResult` | bool + Trajectory + floats + str + metadata dict | None |
| `BottleneckReport` | str + str + str + ComplexityClass + str + str | None |

**Key observation:** All types are `@dataclass(frozen=True, slots=True)` — ideal for serialization but completely lacking it.

### 1.2 Config Types (8 modules)

Each module defines its own `*Config` dataclass with no serialization:

| Module | Config Class | Fields |
|--------|-------------|--------|
| control/mpc.py | `MPCConfig` | horizon, dt, max_iterations, convergence_threshold |
| estimation/ekf.py | `EKFConfig` | state_dim, measurement_dim, process_noise, measurement_noise |
| planning/astar.py | `AStarConfig` | resolution_m, max_iterations, diagonal_movement, heuristic_weight |
| planning/rrt.py | `RRTConfig` | max_iterations, step_size, goal_sample_rate, goal_tolerance |
| planning/prm.py | `PRMConfig` | num_samples, nearest_neighbors, max_iterations |
| planning/hybrid_astar.py | `HybridAStarConfig` | max_iterations, step_size, steering_angle, wheelbase |
| optimization/minimum_snap.py | `MinimumSnapConfig` | degree, waypoint_count, max_iterations, convergence_threshold |
| safety/cbf.py | `CBFConfig` | alpha, beta, safety_margin, max_correction |
| swarm/formation.py | `FormationConfig` | formation_type, spacing, max_agents |
| swarm/task_allocation.py | `TaskAllocationConfig` | algorithm, max_tasks_per_agent, communication_range |

### 1.3 Ad-Hoc Serialization (3 modules only)

| Module | Method | Output | Limitations |
|--------|--------|--------|-------------|
| benchmark.py | `BenchmarkResult.to_dict()` | `Dict[str, Any]` | No bytes, no schema, no versioning |
| evaluation.py | `EvaluationMetric.to_dict()`, `EvaluationResult.to_dict()` | `Dict[str, Any]` | No bytes, no schema, no versioning |
| diagnostics.py | `DiagnosticReport.to_dict()` | `Dict[str, Any]` | No bytes, no schema, no versioning |

### 1.4 Config Serialization (1 module only)

| Module | Method | Output | Limitations |
|--------|--------|--------|-------------|
| onboarding/sizing.py | `generate_config_yaml()` | YAML string | Manual string building, no parsing, no schema |

---

## 2. Gap Analysis

### 2.1 Missing Serialization Formats

| Format | Status | Impact |
|--------|--------|--------|
| **JSON** | ❌ Missing | No human-readable interchange, no web API support, no config files |
| **Protobuf** | ❌ Missing | No compact binary format, no cross-language support, no schema evolution |
| **MessagePack** | ❌ Missing | No fast binary serialization, no efficient network transport |
| **Avro** | ❌ Missing | No schema registry integration, no row-based storage, no Kafka/streaming support |
| **CBOR** | ❌ Missing | No compact binary for IoT/embedded, no RFC 8949 standard |
| **Cap'n Proto** | ❌ Missing | Zero-copy deserialization not available |
| **FlatBuffers** | ❌ Missing | Zero-copy deserialization not available |

### 2.2 Missing Serialization Infrastructure

| Capability | Status | Impact |
|------------|--------|--------|
| Dataclass → bytes | ❌ Missing | Cannot persist or transmit any domain object |
| Bytes → dataclass | ❌ Missing | Cannot load or receive any domain object |
| Schema definition | ❌ Missing | No contract between producer/consumer |
| Schema versioning | ❌ Missing | Cannot evolve types without breaking changes |
| Schema registry | ❌ Missing | No centralized schema management |
| Backward compatibility | ❌ Missing | Cannot read old data after schema changes |
| Forward compatibility | ❌ Missing | Cannot read new data with old code |
| Cross-language support | ❌ Missing | Python-only; cannot interface with PX4 (C++), ArduPilot (C++), ROS 2 (C++) |
| NumPy array serialization | ❌ Missing | Trajectory timestamps (NDArray) cannot be serialized |
| Enum serialization | ❌ Missing | VehicleType, ComplexityClass cannot be serialized |
| Metadata dict serialization | ❌ Missing | `dict[str, Any]` fields have no typed serialization |

### 2.3 Missing Interchange Patterns

| Pattern | Status | Impact |
|---------|--------|--------|
| Request/Response serialization | ❌ Missing | No RPC between modules |
| Event/message serialization | ❌ Missing | No pub/sub for trajectory updates |
| Config file persistence | ❌ Missing | Configs are ephemeral |
| Trajectory file format | ❌ Missing | Cannot save/load trajectories |
| Planning problem file format | ❌ Missing | Cannot share planning problems |
| Result serialization | ❌ Missing | Results exist only in memory |
| Inter-process communication | ❌ Missing | No shared memory or pipe serialization |
| Network protocol | ❌ Missing | No MAVLink/DDS/ROS 2 message support |

---

## 3. Recommended Serialization Formats

### 3.1 Priority 1: JSON (via Pydantic)

**Why:** Human-readable, universal, config files, web APIs, debugging.

**Implementation:** The project already depends on `pydantic>=2.5.0`. Convert dataclasses to Pydantic `BaseModel` or use Pydantic's dataclass support.

```python
from pydantic import BaseModel, Field

class Pose3DModel(BaseModel):
    x: float
    y: float
    z: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

class StateVectorModel(BaseModel):
    pose: Pose3DModel
    velocity: Velocity3DModel
    timestamp: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**Benefits:**
- `model_dump_json()` → JSON string
- `model_validate_json()` → typed object
- `model_dump()` → dict
- Schema generation via `model_json_schema()`
- Already a dependency

### 3.2 Priority 2: MessagePack

**Why:** Fast binary serialization, compact, efficient for network transport and IPC.

**Implementation:** Add `msgpack` dependency. Use with Pydantic for schema validation.

```python
import msgpack
from pydantic import BaseModel

class SerializationManager:
    @staticmethod
    def to_msgpack(model: BaseModel) -> bytes:
        return msgpack.packb(model.model_dump(), use_bin_type=True)
    
    @staticmethod
    def from_msgpack(data: bytes, model_class: type[BaseModel]) -> BaseModel:
        return model_class.model_validate(msgpack.unpackb(data, raw=False))
```

**Benefits:**
- ~2-5x faster than JSON
- ~30-50% smaller than JSON
- Binary-safe (handles NumPy arrays with ext types)
- Ideal for inter-module communication

### 3.3 Priority 3: Protobuf

**Why:** Cross-language (C++ for PX4/ArduPilot/ROS 2), compact, schema evolution, industry standard.

**Implementation:** Define `.proto` files, generate Python classes with `grpcio-tools`.

```protobuf
syntax = "proto3";
package apex_autopilot;

message Pose3D {
    double x = 1;
    double y = 2;
    double z = 3;
    double roll = 4;
    double pitch = 5;
    double yaw = 6;
}

message StateVector {
    Pose3D pose = 1;
    Velocity3D velocity = 2;
    double timestamp = 3;
    map<string, string> metadata = 4;
}

message Trajectory {
    repeated StateVector states = 1;
    repeated ControlInput controls = 2;
    repeated double timestamps = 3;
    VehicleType vehicle_type = 4;
}
```

**Benefits:**
- Cross-language (Python ↔ C++ for PX4/ArduPilot)
- Compact binary format
- Schema evolution via field numbers
- Industry standard for robotics (ROS 2 uses Protobuf)
- Fast deserialization

### 3.4 Priority 4: Avro

**Why:** Schema registry, streaming (Kafka), row-based storage, schema evolution.

**Implementation:** Add `fastavro` or `avro` dependency. Define schemas in JSON.

```python
import fastavro

schema = {
    "type": "record",
    "name": "StateVector",
    "fields": [
        {"name": "pose", "type": Pose3DSchema},
        {"name": "velocity", "type": Velocity3DSchema},
        {"name": "timestamp", "type": "double"},
    ]
}

# Write
with open("states.avro", "wb") as f:
    fastavro.writer(f, schema, records)

# Read
with open("states.avro", "rb") as f:
    for record in fastavro.reader(f):
        process(record)
```

**Benefits:**
- Schema embedded in data
- Schema evolution with compatibility modes
- Ideal for streaming/data lake
- Kafka/Confluent integration

---

## 4. Implementation Strategy

### 4.1 Recommended Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Domain Layer                          │
│  (dataclasses: Pose3D, StateVector, Trajectory, ...)   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Serialization Abstraction                   │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Serializer  │  │  Deserializer│  │ SchemaRegistry│  │
│  │  Protocol    │  │  Protocol    │  │               │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
└─────────┼─────────────────┼──────────────────┼──────────┘
          │                 │                  │
    ┌─────┼─────────────────┼──────────────────┼─────┐
    │     ▼                 ▼                  ▼     │
    │  ┌──────┐  ┌──────────┐  ┌──────────┐  ┌──────┐
    │  │ JSON │  │MessagePack│ │ Protobuf │  │ Avro │
    │  │(Pyd.)│  │ (msgpack) │ │(protobuf)│  │(avro)│
    │  └──────┘  └──────────┘  └──────────┘  └──────┘
    └─────────────────────────────────────────────────┘
```

### 4.2 Proposed Module Structure

```
src/apex_autopilot_optimization/
├── serialization/
│   ├── __init__.py          # Public API
│   ├── base.py              # Serializer/Deserializer protocols
│   ├── json_serializer.py   # Pydantic-based JSON
│   ├── msgpack_serializer.py # MessagePack binary
│   ├── protobuf_serializer.py # Protobuf (generated)
│   ├── avro_serializer.py   # Avro with schema registry
│   ├── schema.py            # Schema definitions & versioning
│   ├── registry.py          # Schema registry client
│   └── compatibility.py     # Backward/forward compat checks
```

### 4.3 Implementation Phases

| Phase | Deliverable | Effort | Dependencies |
|-------|-------------|--------|--------------|
| **1** | Pydantic models for all domain types + JSON serialization | Low | pydantic (already dep) |
| **2** | MessagePack serializer for IPC | Low | msgpack |
| **3** | Protobuf schemas + generated code | Medium | grpcio-tools |
| **4** | Avro schemas + schema registry | Medium | fastavro, schema registry |
| **5** | Schema evolution framework | High | All above |
| **6** | Cross-language tests (Python ↔ C++) | High | Protobuf |

---

## 5. Schema Evolution Patterns

### 5.1 Compatibility Modes

| Mode | Definition | Use Case |
|------|------------|----------|
| **Backward** | New schema can read old data | Rolling upgrades (new code, old data) |
| **Forward** | Old schema can read new data | Rolling downgrades (old code, new data) |
| **Full** | Both backward and forward | Zero-downtime deployments |
| **None** | No compatibility guaranteed | Breaking changes |

### 5.2 Recommended Rules for This Project

| Change Type | Backward | Forward | Full | Recommendation |
|-------------|----------|---------|------|----------------|
| Add optional field | ✅ | ✅ | ✅ | **Preferred** — always add optional fields |
| Add required field | ❌ | ✅ | ❌ | **Avoid** — breaks old readers |
| Remove optional field | ✅ | ❌ | ❌ | **Caution** — old writers may still send it |
| Remove required field | ❌ | ❌ | ❌ | **Avoid** — breaks everyone |
| Rename field | ❌ | ❌ | ❌ | **Avoid** — use aliases instead |
| Change field type | ❌ | ❌ | ❌ | **Avoid** — add new field instead |
| Add enum value | ✅ | ❌ | ❌ | **Caution** — old readers may not handle new value |
| Deprecate field | ✅ | ✅ | ✅ | **Preferred** — mark deprecated, remove later |

### 5.3 Schema Versioning Strategy

```python
from pydantic import BaseModel, Field

class StateVectorV1(BaseModel):
    """Original version."""
    pose: Pose3DModel
    velocity: Velocity3DModel
    timestamp: float = 0.0

class StateVectorV2(BaseModel):
    """Added metadata field."""
    pose: Pose3DModel
    velocity: Velocity3DModel
    timestamp: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)  # NEW

class StateVectorV3(BaseModel):
    """Added vehicle_id field."""
    pose: Pose3DModel
    velocity: Velocity3DModel
    timestamp: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    vehicle_id: str = Field(default="")  # NEW
```

### 5.4 Schema Registry Integration

For Avro/Protobuf, integrate with a schema registry (Confluent or custom):

```python
class SchemaRegistry:
    def register(self, subject: str, schema: dict) -> int:
        """Register a new schema version, return version ID."""
        
    def get_schema(self, subject: str, version: int) -> dict:
        """Get schema by version."""
        
    def check_compatibility(self, subject: str, new_schema: dict) -> bool:
        """Check if new schema is compatible with latest."""
        
    def get_latest_schema(self, subject: str) -> dict:
        """Get latest schema version."""
```

---

## 6. Backward Compatibility Strategy

### 6.1 Data Migration Pattern

```python
class DataMigrator:
    """Migrate data from old schema versions to new."""
    
    MIGRATIONS = {
        ("StateVector", 1, 2): lambda d: {**d, "metadata": {}},
        ("StateVector", 2, 3): lambda d: {**d, "vehicle_id": ""},
    }
    
    @classmethod
    def migrate(cls, data: dict, from_version: int, to_version: int, 
                schema_name: str) -> dict:
        """Migrate data between schema versions."""
        key = (schema_name, from_version, to_version)
        if key in cls.MIGRATIONS:
            return cls.MIGRATIONS[key](data)
        raise ValueError(f"No migration path for {key}")
```

### 6.2 Deserialization with Version Detection

```python
class VersionedDeserializer:
    """Deserialize data with automatic version detection."""
    
    @staticmethod
    def deserialize(data: bytes) -> BaseModel:
        # Try to extract version from data
        version = VersionedDeserializer._detect_version(data)
        
        # Get appropriate schema
        schema = SchemaRegistry.get_schema("StateVector", version)
        
        # Deserialize
        model_class = VersionedDeserializer._get_model_class(version)
        obj = model_class.model_validate(data)
        
        # Migrate to latest if needed
        if version < LATEST_VERSION:
            obj = DataMigrator.migrate(obj.model_dump(), version, LATEST_VERSION, 
                                        "StateVector")
            obj = LatestModel.model_validate(obj)
        
        return obj
```

### 6.3 Wire Format with Version Header

```python
import struct

def serialize_with_version(model: BaseModel, format: str = "msgpack") -> bytes:
    """Serialize with version header for forward compatibility."""
    version = get_schema_version(type(model))
    payload = msgpack.packb(model.model_dump(), use_bin_type=True)
    
    # Header: [magic(4) | version(4) | format(1) | reserved(3) | payload...]
    header = struct.pack("<4sIB3s", b"APEX", version, format.encode(), b"\x00" * 3)
    return header + payload

def deserialize_with_version(data: bytes) -> BaseModel:
    """Deserialize with version detection."""
    magic, version, format_code, _ = struct.unpack("<4sIB3s", data[:12])
    if magic != b"APEX":
        raise ValueError("Invalid magic bytes")
    
    payload = data[12:]
    format_str = format_code.decode()
    
    if format_str == "msgpack":
        dict_data = msgpack.unpackb(payload, raw=False)
    elif format_str == "json":
        dict_data = json.loads(payload)
    else:
        raise ValueError(f"Unknown format: {format_str}")
    
    # Get model class for version and deserialize
    model_class = get_model_class(version)
    return model_class.model_validate(dict_data)
```

---

## 7. Performance Considerations

### 7.1 Format Comparison

| Format | Size | Serialize | Deserialize | Schema | Cross-lang |
|--------|------|-----------|-------------|--------|------------|
| JSON | 100% (baseline) | Medium | Medium | Optional | Yes |
| MessagePack | ~60% | Fast | Fast | No | Yes |
| Protobuf | ~30% | Fast | Fast | Required | Yes |
| Avro | ~40% | Fast | Fast | Required | Yes |
| CBOR | ~65% | Fast | Fast | No | Yes |

### 7.2 Recommendations by Use Case

| Use Case | Recommended Format | Rationale |
|----------|-------------------|-----------|
| Config files | JSON (Pydantic) | Human-readable, already have Pydantic |
| Inter-module IPC | MessagePack | Fast, compact, low latency |
| Network API | JSON (Pydantic) | Universal, debuggable |
| PX4/ArduPilot bridge | Protobuf | Cross-language (C++), compact |
| Trajectory storage | Protobuf or Avro | Compact, schema evolution |
| Streaming/events | Avro | Schema registry, Kafka integration |
| Debug/logging | JSON | Human-readable |

### 7.3 NumPy Array Handling

```python
import msgpack
import numpy as np
from msgpack import ExtType

def encode_numpy(obj):
    """Encode NumPy arrays for MessagePack."""
    if isinstance(obj, np.ndarray):
        return ExtType(0, obj.tobytes() + b"|" + str(obj.dtype).encode() + b"|" + 
                      str(obj.shape).encode())
    raise TypeError(f"Unknown type: {type(obj)}")

def decode_numpy(code, data):
    """Decode NumPy arrays from MessagePack."""
    if code == 0:
        array_data, dtype_str, shape_str = data.split(b"|")
        dtype = np.dtype(dtype_str.decode())
        shape = eval(shape_str.decode())  # safe for tuple of ints
        return np.frombuffer(array_data, dtype=dtype).reshape(shape)
    return ExtType(code, data)

# Usage
packed = msgpack.packb(trajectory, default=encode_numpy, use_bin_type=True)
unpacked = msgpack.unpackb(packed, ext_hook=decode_numpy, raw=False)
```

---

## 8. Integration with Existing Code

### 8.1 Migration Path

1. **Phase 1:** Add Pydantic models alongside existing dataclasses (no breaking changes)
2. **Phase 2:** Add serialization methods to domain types via mixin or wrapper
3. **Phase 3:** Migrate internal module communication to use serialization
4. **Phase 4:** Add file I/O for trajectories, configs, and results
5. **Phase 5:** Add network serialization for distributed operation

### 8.2 Non-Breaking Integration

```python
# Existing code continues to work
state = StateVector(pose=Pose3D(x=1, y=2, z=3), velocity=Velocity3D(0, 0, 0))

# New serialization capability added via mixin
class SerializableMixin:
    def to_json(self) -> str:
        return TypeAdapter(type(self)).dump_json(self)
    
    def to_msgpack(self) -> bytes:
        return msgpack.packb(TypeAdapter(type(self)).dump_python(self))
    
    @classmethod
    def from_json(cls, data: str):
        return TypeAdapter(cls).validate_json(data)
    
    @classmethod
    def from_msgpack(cls, data: bytes):
        return TypeAdapter(cls).validate_python(msgpack.unpackb(data))

# Apply to existing types
class StateVector(SerializableMixin, StateVector):
    pass
```

### 8.3 Config Integration

```python
# Current: manual YAML generation
yaml_str = generate_config_yaml(OrganizationScale.STARTUP)

# New: Pydantic-based config with serialization
class AutopilotConfig(BaseModel):
    scale: OrganizationScale
    planner: str = "astar"
    optimizer: str = "minimum_snap"
    estimator: str = "ekf"
    safety_filter: str | None = None
    controller: str | None = None
    max_iterations: int = 10_000
    log_level: str = "INFO"
    
    def to_yaml(self) -> str:
        return yaml.dump(self.model_dump(), default_flow_style=False)
    
    @classmethod
    def from_yaml(cls, data: str) -> "AutopilotConfig":
        return cls.model_validate(yaml.safe_load(data))
    
    def to_json(self) -> str:
        return self.model_dump_json()
    
    @classmethod
    def from_json(cls, data: str) -> "AutopilotConfig":
        return cls.model_validate_json(data)
```

---

## 9. Dependencies to Add

| Package | Version | Purpose | Priority |
|---------|---------|---------|----------|
| `msgpack` | >=1.0 | Binary serialization | P1 |
| `protobuf` | >=4.0 | Cross-language serialization | P2 |
| `grpcio-tools` | >=1.60 | Protobuf code generation | P2 |
| `fastavro` | >=1.9 | Avro serialization | P3 |
| `cbor2` | >=5.6 | CBOR serialization (IoT) | P3 |
| `jsonschema` | >=4.0 | JSON Schema validation | P3 |

**Already present:** `pydantic>=2.5.0`, `pyyaml>=6.0.1`

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing API | High | Use mixin pattern, don't change existing classes |
| Performance regression | Medium | Benchmark before/after; use MessagePack for hot paths |
| Schema evolution complexity | Medium | Start with backward-only compatibility, add registry later |
| Cross-language bugs | Medium | Property-based testing with Hypothesis (already a dep) |
| Dependency bloat | Low | Make new deps optional extras in pyproject.toml |
| Learning curve | Low | Pydantic is already familiar to most Python devs |

---

## 11. Summary of Gaps

| # | Gap | Severity | Effort to Fix |
|---|-----|----------|---------------|
| 1 | No JSON serialization | **Critical** | Low (Pydantic already dep) |
| 2 | No binary serialization | **Critical** | Low (add msgpack) |
| 3 | No cross-language support | **High** | Medium (Protobuf) |
| 4 | No schema definitions | **High** | Medium |
| 5 | No schema versioning | **High** | Medium |
| 6 | No schema registry | **Medium** | High |
| 7 | No backward compatibility | **High** | Medium |
| 8 | No forward compatibility | **Medium** | Medium |
| 9 | No NumPy array serialization | **High** | Low |
| 10 | No config file persistence | **High** | Low |
| 11 | No trajectory file format | **Medium** | Medium |
| 12 | No IPC serialization | **Medium** | Low |
| 13 | No network protocol | **Medium** | High |
| 14 | No streaming support | **Low** | High |
| 15 | No data migration tools | **Medium** | Medium |

---

## 12. Recommended Immediate Actions

1. **Add Pydantic models** for all 11 core types in `core/types.py` (1-2 days)
2. **Add MessagePack serializer** for inter-module communication (1 day)
3. **Add JSON config serialization** for all 10 config types (1 day)
4. **Add NumPy array serialization** support (1 day)
5. **Define Protobuf schemas** for PX4/ArduPilot bridge (2-3 days)
6. **Add schema versioning** to all serialized types (2 days)
7. **Write property-based tests** for serialization round-trips (2 days)

**Total estimated effort:** ~10-12 days for Phases 1-3 (JSON + MessagePack + basic Protobuf).
