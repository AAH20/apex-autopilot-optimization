# Edge, Fog & Edge AI Computing Gap Report

**Project:** apex-autopilot-optimization  
**Date:** 2025-10-04  
**Classification:** Research Gap Analysis  
**Method:** Cross-reference of EdgeX Foundry, KubeEdge, Azure IoT Edge, NIST SP 500-325, and edge AI patterns against existing 20-module codebase

---

## Executive Summary

The apex-autopilot-optimization project is a **cloud-agnostic, simulation-first Python framework** for UAV/UAS and ground vehicle autopilot optimization. It implements 20 modules spanning planning (A*, RRT, PRM, Hybrid A*), optimization (minimum snap), estimation (EKF), swarm coordination, safety filtering (CBF), and control (MPC). However, the entire codebase assumes a **compute-rich, always-connected execution environment** — a desktop/workstation class machine with NumPy, SciPy, and full Python 3.11+ runtime.

This creates a critical architectural gap: **real autopilot systems operate on resource-constrained edge hardware (ARM CPUs, NPUs, 4-8GB RAM) under intermittent or absent connectivity.** The project has zero edge computing, zero fog computing, zero edge AI, and zero edge-cloud synchronization capabilities.

**Severity: CRITICAL** — Without edge capabilities, the framework cannot be deployed on actual UAV hardware or operate in realistic communication environments.

---

## Current Architecture vs. Edge Reality

| Dimension | Current State | Edge Requirement | Gap |
|---|---|---|---|
| **Compute target** | x86_64 workstation, full NumPy/SciPy | ARM Cortex-A76, Jetson Nano, 4GB RAM | Massive — NumPy alone requires ~150MB; not all ops have ARM NEON equivalents |
| **Connectivity** | Implicitly always-connected | Intermittent 4G/5G, mesh Wi-Fi, complete disconnection | Total — no offline autonomy mechanism |
| **Data processing** | Batch, in-memory lists | Stream, store-and-forward, local buffering | Total — `Trajectory.states: list[StateVector]` assumes all data fits in RAM |
| **Decision latency** | Unbounded (no real-time constraint) | ≤10ms perception-to-actuation for safety-critical maneuvers | Total — no deadline-aware scheduling |
| **Model execution** | None (pure algorithmic) | On-device inference for perception, anomaly detection | Total — no edge AI capability |
| **Fleet coordination** | Centralized `TaskAllocator` (single-node) | Distributed fog-level coordination with hierarchical offloading | Total — no fog node concept |
| **State sync** | None (stateless function calls) | Device twin with desired/reported state, delta sync | Total — no edge-cloud sync |

---

## Gap 1: Edge Computing — Local Autonomy & Store-and-Forward

### What's Missing

1. **Offline Operation Capability**
   - Current: Every planning/estimation call assumes immediate computation. If SciPy is slow or unavailable, the system fails.
   - Edge need: UAVs must continue safe flight during communication loss. PX4/ArduPilot have built-in geofence, RTL (Return-to-Launch), and failsafe behaviors that activate within milliseconds of link loss.
   - Reference: EdgeX Foundry's "store and forward" tenet — "To support disconnected/remote edge systems, to deal with intermittent connectivity" [EdgeX Foundry 3.0 Introduction].

2. **Local Data Buffering & Persistence**
   - Current: `Trajectory` holds `states: list[StateVector]` in memory. A 10-minute flight at 50Hz produces 30,000 state vectors — feasible in RAM but not on a 4GB edge device during concurrent inference.
   - Edge need: Ring-buffer or SQLite-backed local telemetry store with automatic spill-to-disk. Data must survive power cycles.
   - Reference: Azure IoT Edge Hub's `storeAndForwardConfiguration.timeToLiveSecs` — caches messages locally, syncs when reconnected [Azure IoT Edge runtime docs].

3. **Edge-Sensor Ingestion Pipeline**
   - Current: No sensor abstraction. `Pose3D`, `Velocity3D` are plain dataclasses fed directly by the caller.
   - Edge need: MAVLink protocol parser, IMU/GPS/LiDAR stream ingestion, sensor fusion at the edge, quality scoring, and outlier rejection — all before data reaches the planning layer.
   - Reference: EdgeX Foundry Device Services Layer — normalizes sensor data from heterogeneous protocols (Modbus, BACnet, MQTT, CAN bus) into a common event format.

4. **Resource-Constrained Execution**
   - Current: `EKFEstimator` uses 12-state EKF with full matrix inversions. `MPCController` solves QPs with NumPy. These assume O(n³) is acceptable.
   - Edge need: Fixed-point arithmetic, sparse matrix ops, approximate solvers, and graceful degradation (skip EKF update if IMU stale, reduce MPC horizon if compute-bound).
   - Reference: KubeEdge's edge node constraint awareness — EdgeCore uses ~70MB RAM and runs on ARM64 with 512MB total system RAM [Giant Swarm KubeEdge analysis].

### Implementation Path

```
src/apex_autopilot_optimization/
├── edge/                          # NEW package
│   ├── __init__.py
│   ├── buffer.py                  # RingBuffer + SQLiteStore (store-and-forward)
│   ├── connectivity.py            # ConnectionMonitor (ONLINE/OFFLINE state machine)
│   ├── failsafe.py               # Geofence, RTL, landing triggers
│   ├── ingestion.py               # MAVLink parser, sensor stream adapter
│   ├── resource.py               # CPU/RAM monitor, adaptive quality governor
│   └── store.py                  # Local telemetry store (msgpack/Arrow)
```

**Key design decisions:**
- `buffer.py` implements a bounded ring buffer (configurable capacity, default 10,000 entries) with automatic spill to SQLite. On reconnect, flushes in priority order (ERROR > WARN > INFO).
- `connectivity.py` uses a lightweight HTTP HEAD to a `/health` endpoint rather than ICMP ping (which is brittle and often blocked). State transitions: `OFFLINE→ONLINE` triggers immediate sync; `ONLINE→OFFLINE` switches to local-only mode.
- `failsafe.py` implements PX4-style geofence breach detection and RTL — currently the project has NO safety net beyond CBF, which is a filter, not an autonomous failsafe.

**Estimated effort:** 2-3 weeks, 6 modules, ~1500 LOC + tests.

---

## Gap 2: Fog Computing — Hierarchical Coordination Layer

### What's Missing

1. **Fog Node Concept**
   - Current: `TaskAllocator` operates on a single node's view. `FormationController` assumes all vehicles are visible to one coordinator.
   - Edge need: Ground station, tethered relay drone, or vehicle-mounted compute serves as a fog node — aggregating telemetry from multiple UAVs, running fleet-level optimization, and distributing commands.
   - Reference: NIST SP 500-325 defines fog nodes as "physical components (gateways, switches, routers, servers) or virtual components" that provide "data management and communication services between network's edge layer and centralized cloud" [NIST SP 500-325 §2.6].

2. **Hierarchical Task Offloading**
   - Current: `swarm/task_allocation.py` uses a greedy priority-first, nearest-vehicle algorithm. No concept of computational offloading.
   - Edge need: Partition tasks into (a) time-critical local execution (collision avoidance), (b) fog-level coordination (formation replanning), and (c) cloud-level analytics (mission-level optimization, weather rerouting).
   - Reference: Adaptive Hierarchical MPC for autonomous vehicle fleets — partitions MPC into cloud-level (high-order trajectory planning) and edge-level (real-time actuator commands), achieving 36% latency reduction [Freederia, 2025].

3. **Mesh Networking & Peer Discovery**
   - Current: Swarm modules assume a star topology (one coordinator). No peer-to-peer communication.
   - Edge need: 802.11s mesh, MAVLink router, or DDS-based discovery for drone-to-drone communication without infrastructure.
   - Reference: KubeEdge EdgeMesh — "handles service discovery across edge nodes without requiring each node to have a public IP" [Giant Swarm KubeEdge analysis].

4. **Fog-Level State Aggregation**
   - Current: No shared state between vehicles beyond `FormationController`'s hardcoded formations.
   - Edge need: Distributed shared state (e.g., CRDTs or operational transforms) for swarm-wide situational awareness — obstacle maps, traffic density, weather cells.

### Implementation Path

```
src/apex_autopilot_optimization/
├── fog/                           # NEW package
│   ├── __init__.py
│   ├── node.py                    # FogNode (gateway/relay role)
│   ├── coordinator.py             # HierarchicalCoordinator (fog-level task dist)
│   ├── offload.py                 # OffloadScheduler (local ↔ fog ↔ cloud decision)
│   ├── mesh.py                    # MeshDiscovery, peer state exchange
│   ├── aggregation.py             # FleetStateAggregator (CRDT-based)
│   └── partition.py              # TaskPartitioner (critical vs. deferrable)
```

**Key design decisions:**
- `node.py` defines a `FogNode` with roles: `GROUND_STATION`, `RELAY_DRONE`, `VEHICLE_MOUNTED`. Each role has different compute/bandwidth/power budgets.
- `offload.py` implements a latency-aware scheduler: estimates local execution time vs. fog RTT + compute time, chooses the lower-latency path. Falls back to local execution if connectivity degrades. Pattern from MEC-D³ (57ms vs. 112ms pure-edge latency) [Freederia MEC-D³, 2025].
- `aggregation.py` uses a lightweight CRDT (LWW-Register per cell) for shared obstacle maps — conflict-free merge when drones reconnect after partition.

**Estimated effort:** 3-4 weeks, 6 modules, ~2000 LOC + tests. Depends on Gap 1 (edge infrastructure).

---

## Gap 3: Edge AI — On-Device Inference

### What's Missing

1. **No ML/AI Inference Anywhere**
   - Current: The project is 100% algorithmic — A*, RRT, EKF, CBF, MPC. Zero neural network inference, zero learned models, zero perception capability.
   - Edge need: Real autopilots use ML for: obstacle detection (YOLO/MobileNet), terrain classification, wind prediction, anomaly detection, vision-based navigation, and learned trajectory priors.
   - Reference: Sedna (KubeEdge's AI extension) supports four paradigms: joint inference (edge filters easy cases, cloud handles hard cases), incremental learning, federated learning, and lifelong learning [DeepWiki Sedna].

2. **No Model Format/Optimization Pipeline**
   - Current: No model registry, no quantization, no ONNX/TFLite export.
   - Edge need: Quantized INT8 models (MobileNetV2 at 3.7MB), ONNX Runtime for cross-platform inference, TensorRT for NVIDIA hardware, TFLite Micro for microcontrollers.

3. **No Perception-to-Control Pipeline**
   - Current: Planning takes `PlanningProblem` with `obstacles: list[dict]` — assumes perfect obstacle knowledge.
   - Edge need: Camera → object detection → depth estimation → occupancy grid → planner. The entire perception stack is missing.

4. **No Anomaly/Failure Detection**
   - Current: `diagnostics.py` checks Python version, NumPy installation, and module availability. No runtime anomaly detection.
   - Edge need: On-device ML model for vibration analysis, motor current signatures, GPS drift detection, and sensor health classification.

### Implementation Path

```
src/apex_autopilot_optimization/
├── edge_ai/                       # NEW package
│   ├── __init__.py
│   ├── inference.py               # ONNX Runtime wrapper, model registry
│   ├── quantize.py               # INT8 quantization, model optimization
│   ├── perception.py             # Object detection → occupancy grid
│   ├── anomaly.py                # Vibration/GPS anomaly classifier
│   ├── joint.py                  # JointInference (edge cloud split)
│   ├── model_registry.py         # Versioned model store, OTA updates
│   └── early_exit.py             # Early-exit classifier for adaptive compute
```

**Key design decisions:**
- `inference.py` wraps ONNX Runtime with a fallback to TFLite. Models are loaded from a versioned registry (local disk, synced via fog/cloud). Supports GPU delegate on Jetson, NPU delegate on Qualcomm, CPU fallback everywhere.
- `joint.py` implements the Sedna pattern: lightweight edge model (MobileNetV2-distilled) processes 45% of frames and exits early; ambiguous frames are sent to a larger cloud model. This matches the "cloud-edge joint inference" paradigm where "inference with shallow model on edge, and if confidence is met, directly return; otherwise send to cloud" [KubeCon India 2024].
- `perception.py` takes a camera frame, runs quantized obstacle detection, projects to 3D occupancy grid (using known camera calibration), and feeds the existing `PlanningProblem` pipeline. This closes the loop from sensor to planner.
- `early_exit.py` adds auxiliary classifiers at intermediate layers — clear-sky frames exit after layer 3, saving ~2ms per frame [Martinuke, 2026].

**Estimated effort:** 4-6 weeks, 8 modules, ~2500 LOC + tests. Recommended to start with a single use case (e.g., obstacle detection → planning) and expand.

---

## Gap 4: Edge-Cloud Synchronization

### What's Missing

1. **No Device Twin Concept**
   - Current: `StateVector` is a transient in-memory snapshot. No persistent device state, no desired vs. reported property separation.
   - Edge need: Device twin with `desired` (cloud → device: new mission, geofence update, model version) and `reported` (device → cloud: health, telemetry summary, anomaly events). This is the canonical IoT pattern.
   - Reference: Azure IoT Hub device twin — "A JSON document that stores device state information including metadata, configurations, and conditions... synchronized automatically between cloud and device" [Azure IoT Hub docs].

2. **No Delta Sync / Conflict Resolution**
   - Current: No synchronization exists. Functions are stateless.
   - Edge need: When a UAV reconnects after 30 minutes offline, only changes (deltas) should sync — not the full state history. Conflicts (e.g., cloud updated geofence while UAV was offline flying a mission) need automatic resolution.
   - Reference: KubeEdge MetaManager — "caches pod state, ConfigMap contents, and other Kubernetes metadata in a local SQLite database. When connection is restored, it syncs the delta" [Giant Swarm KubeEdge analysis].

3. **No OTA Update Mechanism**
   - Current: Code updates require `pip install -e .` on the device — impractical for fielded UAVs.
   - Edge need: Model updates (new obstacle detection weights), algorithm parameter tuning, and security patches pushed from cloud with canary rollout and rollback.

4. **No Telemetry Sync with Prioritization**
   - Current: `observability.py` has a `MetricCollector` but it's in-memory only, no persistence or transmission.
   - Edge need: Telemetry buffered locally (Gap 1), synced with priority tiers — ERROR events immediately, WARNING within 30s, INFO/DEBUG batched and compressed.

### Implementation Path

```
src/apex_autopilot_optimization/
├── sync/                          # NEW package
│   ├── __init__.py
│   ├── twin.py                    # DeviceTwin (desired/reported state)
│   ├── delta.py                   # DeltaSyncEngine (change detection, compression)
│   ├── conflict.py               # ConflictResolver (LWW, mission-aware merge)
│   ├── ota.py                    # OTAUpdateManager (canary, rollback)
│   ├── telemetry.py              # TelemetrySync (priority-tiered batching)
│   └── protocol.py              # MQTT/AMQP transport, QoS levels
```

**Key design decisions:**
- `twin.py` defines `DeviceTwin` with `desired: dict` (cloud-authored) and `reported: dict` (device-authored). Uses MQTT topics: `devices/{id}/twin/desired` and `devices/{id}/twin/reported`.
- `delta.py` implements vector-clock-based delta sync. Each state change is tagged with `(device_id, logical_clock)`. On reconnect, exchanges missing operations. Uses msgpack for compact serialization (~70% smaller than JSON).
- `conflict.py` uses Last-Writer-Wins for configuration (geofence, speed limits) but mission-aware merge for trajectories — if the cloud sends a new mission while the UAV is executing one, the new mission queues as "pending" rather than overriding in-flight execution.
- `ota.py` supports canary rollout (10% of fleet → 50% → 100%) with automatic rollback if error rate exceeds threshold.
- `telemetry.py` implements the three-tier priority system: ERROR → immediate MQTT QoS 2; WARNING → QoS 1 within 30s; INFO/DEBUG → batched every 5min, gzip compressed.

**Estimated effort:** 3-4 weeks, 7 modules, ~2000 LOC + tests. Depends on Gap 1 (buffer infrastructure).

---

## Cross-Cutting Concerns

### Latency Budget Analysis

For a swarm of autonomous drones performing collaborative search-and-rescue, the end-to-end latency budget is:

| Stage | Target Latency | Current Support | Gap |
|---|---|---|---|
| Sensor capture → preprocessing | ≤5ms | None | Full gap |
| Object detection (edge AI) | ≤10ms | None | Full gap |
| Local planning (A*/RRT) | ≤20ms | Algorithm exists, no deadline enforcement | Needs real-time wrapper |
| MPC control cycle | ≤10ms | Algorithm exists, no real-time wrapper | Needs RT wrapper |
| Fog-level replanning | ≤50ms | None | Full gap |
| Cloud-level mission optimization | ≤500ms | None | Full gap |

**Total budget: ≤100ms for safety-critical maneuvers.** The existing algorithms (A*, MPC) are capable of meeting these targets on edge hardware, but they lack:
- Deadline-aware scheduling (must return best-effort solution by deadline)
- Approximate/graceful degradation (return suboptimal but safe path if optimal solver times out)
- Warm-starting from previous solution (critical for MPC on edge)

### Hardware Compatibility Matrix

| Target Platform | Current Compatibility | Required Adaptation |
|---|---|---|
| Raspberry Pi 4 (ARM, 4GB) | NumPy/SciPy work but slowly | Need ARM-optimized BLAS (OpenBLAS), reduced EKF state |
| NVIDIA Jetson Nano (ARM+GPU) | No GPU utilization | CUDA/TensorRT delegate for edge AI |
| Qualcomm Dragonwing (NPU) | No NPU support | QNN delegate for TFLite |
| STM32H7 (microcontroller, 2MB flash) | Incompatible (requires Python) | Would need C++ port or MicroPython subset |
| Intel NUC (x86, 16GB) | Full compatibility | Reference deployment target |

### Dependency Impact

Adding edge/fog/AI capabilities will increase the dependency footprint:

| New Dependency | Size | Purpose | Alternative |
|---|---|---|---|
| `onnxruntime` | ~50MB | Edge AI inference | `tflite-runtime` (~5MB, ARM only) |
| `paho-mqtt` | ~200KB | MQTT transport | Raw asyncio + `websockets` |
| `msgpack` | ~100KB | Compact serialization | `protobuf` (larger but schema-evolvable) |
| `cbor2` | ~50KB | IoT-optimized binary format | — |
| `aiosqlite` | stdlib | Async SQLite for buffer | — |

**Total new dependency overhead: ~55MB** — significant for edge devices but acceptable on any Linux-class target (Raspberry Pi+). For microcontroller targets, a C++ port is required.

---

## Implementation Roadmap

### Phase 1: Edge Foundation (Weeks 1-3)
- [ ] `edge/buffer.py` — RingBuffer + SQLite spill-to-disk
- [ ] `edge/connectivity.py` — ConnectionMonitor state machine
- [ ] `edge/failsafe.py` — Geofence + RTL + emergency landing
- [ ] `edge/ingestion.py` — MAVLink parser stub
- [ ] `edge/store.py` — Local telemetry persistence
- [ ] `edge/resource.py` — CPU/RAM monitor + adaptive governor
- [ ] Integration test: 30-min simulated flight with 5-min disconnection window

### Phase 2: Edge Cloud Sync (Weeks 4-6)
- [ ] `sync/twin.py` — DeviceTwin with desired/reported state
- [ ] `sync/delta.py` — Vector-clock delta sync engine
- [ ] `sync/telemetry.py` — Priority-tiered telemetry sync
- [ ] `sync/conflict.py` — LWW + mission-aware conflict resolution
- [ ] `sync/protocol.py` — MQTT transport with QoS levels
- [ ] Integration test: Fleet of 5 UAVs, 1 cloud, intermittent connectivity, verify convergence

### Phase 3: Edge AI (Weeks 7-10)
- [ ] `edge_ai/inference.py` — ONNX Runtime wrapper + model registry
- [ ] `edge_ai/quantize.py` — INT8 quantization pipeline
- [ ] `edge_ai/perception.py` — Obstacle detection → occupancy grid
- [ ] `edge_ai/early_exit.py` — Adaptive compute classifier
- [ ] `edge_ai/joint.py` — Edge-cloud joint inference (Sedna pattern)
- [ ] `edge_ai/anomaly.py` — Vibration/GPS anomaly classifier
- [ ] Integration test: Camera stream → detection → planner → control loop ≤ 50ms

### Phase 4: Fog Computing (Weeks 11-14)
- [ ] `fog/node.py` — FogNode with role-based resource profiles
- [ ] `fog/coordinator.py` — Hierarchical task distribution
- [ ] `fog/offload.py` — Latency-aware offload scheduler
- [ ] `fog/mesh.py` — Peer discovery + state exchange
- [ ] `fog/aggregation.py` — CRDT-based fleet state
- [ ] Integration test: 12-UAV swarm with ground-station fog node, hierarchical MPC

### Phase 5: Hardening (Weeks 15-16)
- [ ] OTA update manager with canary rollout
- [ ] Security: mutual TLS, signed model updates, secure boot integration
- [ ] Hardware-in-the-loop: Jetson Nano + PX4 SITL
- [ ] Performance benchmarking across target platforms
- [ ] Documentation: deployment guide for each hardware target

---

## References

1. EdgeX Foundry — "Introduction" (v3.0, v4.0). https://docs.edgexfoundry.org/
2. KubeEdge — CNCF Incubating project. Cloud-edge coordination, device twin, EdgeMesh. https://kubeedge.io/
3. Azure IoT Edge — "Runtime and architecture explained." https://learn.microsoft.com/en-us/azure/iot-edge/iot-edge-runtime
4. NIST SP 500-325 — "Fog Computing Conceptual Model." https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.500-325.pdf
5. Sedna — KubeEdge edge-cloud synergy AI. https://github.com/kubeedge/sedna
6. Giant Swarm — "Kubernetes at the Edge: how KubeEdge brings cloud-native orchestration." https://giantswarm.io/blog/kubernetes-at-the-edge-how-kubeedge-brings-cloud-native-orchestration-to-iot-and-beyond
7. Freederia — "Adaptive Hierarchical Control Through Cloud-Edge Offloading for Autonomous Vehicle Fleets." https://freederia.com/adaptive-hierarchical-control-through-cloud-edge-offloading-for-autonomous-vehicle-fleets
8. Freederia — "Dynamic Energy-Low-Latency Offloading for Autonomous Drone Swarms (MEC-D³)." https://freederia.com/dynamic-energy-low-latency-offloading-for-autonomous-drone-swarms-in-multi-access-edge-computing
9. Martinuke — "Latency-Sensitive Inference Optimization for Multi-Agent Systems in Decentralized Edge Environments." https://martinuke0.github.io/posts/2026-03-19-latencysensitive-inference-optimization-for-multiagent-systems-in-decentralized-edge-environments
10. KubeCon India 2024 — "Cloud-Edge Joint Inference" (Sedna pattern). https://static.sched.com/hosted_files/kccncind2024/5b/KubeEdge%20PPT.pdf
11. softwarepatternslexicon.com — "Python IoT Systems with Design Patterns." https://softwarepatternslexicon.com/python/case-studies/applying-patterns-in-iot-systems
12. sdcourse.substack.com — "Day 177: Edge Log Collection for Limited Connectivity." https://sdcourse.substack.com/p/day-177-edge-log-collection-for-limited
13. TensorFlow Lite — "Using TensorFlow Lite with Python." https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/g3doc/guide/python.md
14. Bala et al. — "The OODA Loop of Cloudlet-Based Autonomous Drones." https://cmu.edu/scs/edgecomputing/documents/bala2024.pdf

---

*Report generated through cross-referencing three major edge computing OSS projects (EdgeX Foundry, KubeEdge, Azure IoT Edge), NIST fog computing standards, and current edge AI research against the apex-autopilot-optimization codebase. All implementation estimates are based on TDD methodology with the project's existing test patterns.*
