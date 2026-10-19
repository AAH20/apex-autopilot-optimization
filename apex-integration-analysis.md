# Apex–AAS Integration Boundary Analysis

**Subject:** `apex-autopilot-optimization` (AGPL-3.0) integration boundary with
`Aerial Autonomy Stack` / AAS (github.com/JacopoPan/aerial-autonomy-stack, MIT)
**Repo analyzed:** `/home/aah/Downloads/2000 workflows/projects/apex-autopilot-optimization/`
**Python package:** `src/apex_autopilot_optimization/` (note: the context's top-level
paths such as `swarm/task_allocation.py` do not exist; all target modules live under
`src/apex_autopilot_optimization/<domain>/`)
**Goal:** vendor-agnostic swarm simulation (no V-BAT lock-in), sub-100 ms
end-to-end latency, AGPL-3.0 apex + MIT AAS combination.

---

## 1. Module inventory

The eight requested modules, plus the vehicle-interface and ROS2/DDS bridges they
depend on, and the HITL submodules `integration/hitl.py` imports.

| Module (repo path) | Purpose | Key classes / symbols | Approx. lines |
|---|---|---|---|
| `core/types.py` | Foundational domain types used across the framework | `VehicleType`, `ComplexityClass`, `Pose3D`, `Velocity3D`, `StateVector`, `ControlInput`, `Waypoint`, `Trajectory`, `PlanningProblem`, `PlanningResult`, `OptimizationConstraint`, `OptimizationObjective`, `BottleneckReport` | 212 |
| `swarm/task_allocation.py` | Greedy winner-takes-all task assignment | `TaskAllocationConfig`, `Task`, `Agent`, `TaskAllocator.allocate()` | 104 |
| `swarm/formation.py` | Geometric swarm formation computation | `FormationConfig`, `FormationController.compute_formation_positions()` (line, wedge, hexagon) | 97 |
| `optimization/minimum_snap.py` | Single-vehicle minimum-snap trajectory generation | `MinimumSnapConfig`, `MinimumSnapOptimizer.optimize()` (quintic interpolation, snap cost) | 198 |
| `simulation/interface.py` | Simulation backend abstraction | `SimulationBackend` enum (GAZEBO, AIRSIM, JMASIM, SITL, HITL), `SimulationInterface` ABC (connect/disconnect/get_state/send_control/arm/set_mode/reset/step/is_connected/time_scale) | 121 |
| `simulation/runner.py` | Mission execution loop over a `SimulationInterface` | `SimulationRunner.run_mission()`, `run_batch()`, stats tracking; no-op fallback components | 237 |
| `simulation/config.py` | Simulation session config | `SimulationConfig` (backend, connection_string, lockstep, time_scale, vehicle_type, model) | 26 |
| `simulation/result.py` | Mission result container | `SimulationResult` | 25 |
| `integration/vehicle.py` | Protocol-agnostic vehicle bridge contract | `VehicleInterface` ABC (connect/disconnect/get_state/send_control/arm/set_mode/get_telemetry/is_connected) | 128 |
| `integration/mavlink.py` | MAVLink vehicle bridge (PX4/ArduPilot dialect) | `MAVLinkBridge(VehicleInterface)`, `MAVLINK_MODE_MAP` (28 modes), pymavlink real path + internal simulation fallback | 508 |
| `integration/ros2.py` | ROS2 vehicle bridge | `ROS2Bridge(VehicleInterface)`, QoS presets, cmd_vel/odom/battery/gps topics, arm/mode services | 437 |
| `integration/dds.py` | DDS vehicle bridge (Fast-DDS/CycloneDDS) | `DDSBridge(VehicleInterface)` | 419 |
| `integration/hitl.py` | Human-in-the-loop adapter over MAVLinkBridge | `HITLAdapter(MAVLinkBridge)`, `ACTION_RISK_LEVELS`, `MUST_APPROVE_ACTIONS` | 258 |
| `hitl/{workflow,config,request,status}.py` | Approval workflow engine | `ApprovalWorkflow`, `HITLConfig`, `ApprovalRequest`, `ApprovalStatus` (+ override in `override.py`) | ~280 combined |

Evidence of test coverage exists for every target module:
`tests/unit/test_core_types.py`, `test_swarm_task_allocation.py`, `test_swarm_formation.py`,
`test_optimization_minimum_snap.py`, `test_simulation.py`, `test_hitl.py`.

---

## 2. Existing capability layers in apex-autopilot-optimization

### 2.1 Vehicle abstraction — EXISTS
`integration/vehicle.py` defines `VehicleInterface`, a protocol-agnostic ABC
(connect/disconnect/get_state/send_control/arm/set_mode/get_telemetry/is_connected).
Three concrete implementations ship:
- `integration/mavlink.py` `MAVLinkBridge` — pymavlink (UDP/TCP/serial), 28-mode
  PX4/ArduPilot mode map, internal simulation mode when pymavlink is absent.
- `integration/ros2.py` `ROS2Bridge` — rclpy, `cmd_vel` publisher, odom/battery/gps
  subscribers, arm/mode service clients, simulation fallback.
- `integration/dds.py` `DDSBridge` — Fast-DDS/CycloneDDS, simulation fallback.

This is the layer AAS's per-vehicle MAVLink/ROS2 connectivity maps onto.

### 2.2 Optimization — PARTIAL (single-vehicle only)
- **WTA / task assignment:** `swarm/task_allocation.py` `TaskAllocator` — greedy,
  highest-priority-first, nearest-agent-within-communication-range, capacity limit
  (`max_tasks_per_agent`). No exact solver, no auction/consensus-based method,
  no time windows, no task dependencies, no re-allocation.
- **Formation:** `swarm/formation.py` `FormationController` — static line, wedge,
  hexagon patterns computed from a leader `StateVector`. Pure geometry: no tracking
  controller, no collision avoidance, no dynamic reconfiguration.
- **Trajectory:** `optimization/minimum_snap.py` `MinimumSnapOptimizer` — quintic
  polynomial interpolation through start → waypoints → goal, snap (4th derivative)
  cost estimate. Single vehicle, no obstacle avoidance, no multi-vehicle
  deconfliction, no real-time budget measurement beyond wall-clock `computation_time_ms`.

### 2.3 Simulation connectivity — PARTIAL (ABCs + bridges, no Gazebo adapter)
- `simulation/interface.py` `SimulationInterface` ABC + `SimulationBackend` enum
  (GAZEBO, AIRSIM, JMASIM, SITL, HITL) — the contract AAS backends must satisfy.
- `simulation/runner.py` `SimulationRunner` — full mission loop: connect → arm →
  set_mode("GUIDED") → [get_state → plan → control → safety filter → send_control → step]
  × max_steps → disconnect. `run_batch()` supports component injection; no-op
  defaults make batch a connectivity smoke test.
- `integration/mavlink.py` / `ros2.py` / `dds.py` — concrete vehicle-side bridges.
- `integration/hitl.py` `HITLAdapter` — gates arm/set_mode/send_control through an
  `ApprovalWorkflow` (pending/approved/rejected/expired/escalated, audit trail,
  human override).

**Missing:** a concrete `SimulationInterface` implementation for Gazebo/AIRSIM/JMASIM
SITL/HITL. The ABC exists but nothing instantiates it for AAS's Gazebo SITL surface.
The runner talks to `SimulationInterface`, not directly to MAVLink/ROS2 bridges, so
an adapter layer is required between AAS and apex's runner.

---

## 3. Capability mapping: AAS → apex-autopilot-optimization

| AAS capability (Option B context) | Apex module | Coverage | Notes |
|---|---|---|---|
| Multi-vehicle PX4/ArduPilot Gazebo SITL | `simulation/interface.py` (GAZEBO/SITL backends) + `integration/mavlink.py` | PARTIAL | Backend ABC and MAVLink dialect exist, but no concrete Gazebo SITL adapter, no multi-vehicle orchestration, no per-vehicle port namespacing. |
| Gazebo SITL scaling (<10 vehicles per instance per context bottleneck) | `simulation/runner.py` | GAP | Runner executes a single vehicle mission per call; `run_batch()` is sequential and still one vehicle per mission. No fleet-wide batch or instance pooling. |
| ROS2 action offboard / guided mode | `integration/ros2.py` + `simulation/interface.py` set_mode | PARTIAL | `ROS2Bridge` publishes `cmd_vel` (Twist) and exposes arm/mode *services*; no ROS2 **action clients** (e.g. offboard trajectory setpoints), no guided/offboard mode mapping beyond a string. AAS's "ROS2 action offboard" is not represented. |
| YOLO+ONNX perception | — | GAP | No perception stack anywhere in apex. YOLO/ONNX model loading, inference, and detection output types are absent. |
| LiDAR / KISS-ICP odometry | — | GAP | No point-cloud types, no LiDAR ingestion, no KISS-ICP integration. `StateVector`/`Pose3D` exist but carry no sensor provenance. |
| Port namespacing 5760 + i×10 (master), 5501 + i×10 (SITL) | — | GAP | `MAVLinkBridge` takes a single `connection_string` and a scalar `system_id`. No port arithmetic, no per-vehicle namespace derivation, no automatic `MAV_SYS_ID`/`DRONE_ID`/`ROS_DOMAIN_ID` binding. |
| DRONE_ID = ROS_DOMAIN_ID = MAV_SYS_ID identity | `integration/mavlink.py` (`system_id`) / `ros2.py` (`domain_id`) | PARTIAL | Both accept an ID as a constructor argument but never derive or enforce the identity relationship across MAVLink/ROS2; no central vehicle registry. |
| Swarm task assignment (WTA) | `swarm/task_allocation.py` | PARTIAL | Greedy WTA exists and matches the documented WTA bottleneck (exact methods intractable beyond 20×20). Covered for small swarms; approximation/exact methods missing for larger ones. |
| Swarm formation (line/wedge/hexagon) | `swarm/formation.py` | PARTIAL | All three AAS-relevant patterns exist as static geometry. No collision avoidance or motion tracking — formations are position setpoints only. |
| Trajectory generation (minimum snap) | `optimization/minimum_snap.py` | PARTIAL | Single-vehicle quintic min-snap exists with snap cost. No multi-vehicle coordination, obstacle constraints, or sub-100 ms guarantee. |
| Human-in-the-loop (arm/mode/control gating) | `integration/hitl.py` + `hitl/*` | EXISTS | Full approval workflow with risk levels, audit trail, overrides. Latency contribution to the 100 ms budget unmeasured. |
| Core types (Pose3D, StateVector, Trajectory, PlanningProblem/Result, VehicleType) | `core/types.py` | EXISTS | Complete shared vocabulary; both AAS and apex can build on it. Missing: multi-vehicle/fleet types, sensor types (image/pointcloud), port/namespace config. |

---

## 4. Gap analysis per module

### `core/types.py` — strong foundation, missing swarm/sensor concepts
- Present: all pose/state/control/trajectory/problem/result types plus `VehicleType` (fixed-wing, multirotor, VTOL, ground variants) and `ComplexityClass` for classifying optimization hardness.
- Gaps: no `Swarm`/`Fleet` aggregate, no `VehicleProfile` (capabilities, ports, namespace), no perception types (`CameraImage`, `PointCloud`, `Detection`), no `PortConfig`/`NamespaceConfig` to encode AAS's 5760+i×10 / 5501+i×10 scheme, no `DRONE_ID`/`ROS_DOMAIN_ID`/`MAV_SYS_ID` binding type.
- Impact: AAS's per-vehicle identity and port namespacing cannot be expressed in apex's type system today.

### `swarm/task_allocation.py` — greedy WTA only
- Present: greedy priority+distance allocation with per-agent capacity and communication-range filter (100 m default).
- Gaps: no exact solver (context notes WTA NP-complete beyond 20×20), no auction / consensus-based decentralized allocation, no task time windows or dependencies, no re-allocation on failure, no benchmark harness for the <100 ms latency budget.
- Impact: adequate for small swarms; will not scale to AAS's intended fleet sizes without an approximate method.

### `swarm/formation.py` — static geometry, no motion layer
- Present: line, wedge, hexagon target positions from a leader state.
- Gaps: no formation tracking controller, no inter-vehicle collision avoidance, no obstacle avoidance, no dynamic reconfiguration (pattern change mid-mission), no integration with `MinimumSnapOptimizer` outputs.
- Impact: formation positions are dead ends — nothing consumes them to generate vehicle commands.

### `optimization/minimum_snap.py` — single-vehicle, no constraints
- Present: quintic polynomial min-snap through start/waypoints/goal, snap-cost estimate, `PlanningResult` with `computation_time_ms`.
- Gaps: single vehicle only; no multi-vehicle trajectory deconfliction; no inequality/equality constraint support despite `OptimizationConstraint` existing in `core/types.py`; no replanning; no hard real-time guarantee (100 ms budget unverified).
- Impact: trajectory layer exists per vehicle but cannot produce coordinated swarm trajectories.

### `simulation/interface.py` — ABC complete, no implementations
- Present: full `SimulationInterface` contract and `SimulationBackend` enum including GAZEBO, AIRSIM, JMASIM, SITL, HITL.
- Gaps: **zero concrete backend adapters**. Nothing connects the ABC to AAS's Gazebo SITL instances or to MAVLink/ROS2 endpoints.
- Impact: `SimulationRunner.run_mission(sim_factory=...)` requires an externally supplied factory; apex ships none for AAS backends.

### `simulation/runner.py` — single-vehicle mission loop
- Present: connect/arm/set_mode/plan/control/safety/step/disconnect loop, `SimulationResult`, cumulative stats, batch mode with injectable components.
- Gaps: one vehicle per mission; sequential batch; default components are no-ops (planner/optimizer/controller/estimator/safety all stub — the runner is a connectivity smoke test unless components are wired); no per-step timing enforcement; no GUIDED/OFFBOARD mode semantics beyond a string.
- Impact: cannot run a multi-vehicle swarm simulation out of the box.

### `integration/mavlink.py` — single vehicle, simulation-capable
- Present: `MAVLinkBridge` with pymavlink real path, 28-mode map, RC-override + position-target-ish control, simulated telemetry/state fallback, heartbeat liveness.
- Gaps: one system_id per bridge instance (no per-vehicle port namespacing); no discovery/heartbeat-based multi-vehicle enumeration; no PX4 offboard position/velocity setpoint messages (`SET_POSITION_TARGET_LOCAL_NED`, `TRAJECTORY_REPRESENTATION`); control is RC-channel override, not offboard setpoints; no AAS port arithmetic (5760+i×10, 5501+i×10).
- Impact: can bridge one PX4/ArduPilot SITL instance; a swarm needs N bridges with N namespaced connections — none of that plumbing exists.

### `integration/ros2.py` — topic/service level, no actions
- Present: `ROS2Bridge`, QoS presets, cmd_vel/odom/battery/gps, arm/mode services, namespace/domain_id params.
- Gaps: no ROS2 action clients (offboard/guided trajectory execution in AAS is action-based); no per-vehicle namespace derivation from DRONE_ID/ROS_DOMAIN_ID; no multi-vehicle node graph management.
- Impact: partial match to AAS's "ROS2 action offboard/guided" — actions are the missing piece.

### `integration/dds.py` — present but not referenced by the 8-module brief
- Present: Fast-DDS/CycloneDDS bridge with simulation fallback.
- Gaps: same as ROS2 — topic-level only, no keyed multi-vehicle participants, no domain_id-per-vehicle automation.
- Note: DDS is not mentioned in the AAS context (MAVLink + ROS2 are), so DDS is a lower-priority integration surface.

### `integration/hitl.py` + `hitl/*` — complete workflow, unmeasured latency
- Present: `HITLAdapter` gates arm (high), takeoff (high), emergency_stop (critical), set_mode/land/rtl (medium), send_control (low, throttle>0.8 or yaw_rate>1.0 escalates); `ApprovalWorkflow` with pending/approved/rejected/expired/escalated, audit trail, human overrides, `HITLConfig` (timeout 60 s, max 10 pending).
- Gaps: per-vehicle approval at swarm scale creates N approval streams — no batch or fleet-level approval mode; worst-case approval latency unmeasured against the 100 ms end-to-end budget; HITL enabled by default means `arm()`/`set_mode()` return `False` pending human action, which breaks an autonomous swarm loop unless `enabled=False` or auto-approve is configured.
- Impact: integration point exists; must be configured (likely disabled or auto-approved low-risk) for autonomous swarm operation within the latency budget.

---

## 5. Integration points (AAS → apex data/control flow)

```
AAS Gazebo SITL (per vehicle i: master 5760+i*10, SITL 5501+i*10)
        │ MAVLink UDP
        ▼
apex integration/mavlink.py  MAVLinkBridge(system_id=i, connection_string="udp:127.0.0.1:5760+i*10")
        │ implements
        ▼
apex integration/vehicle.py  VehicleInterface (protocol-agnostic)
        │ adapter (to be built)
        ▼
apex simulation/interface.py SimulationInterface (GAZEBO/SITL backend)
        │
        ▼
apex simulation/runner.py  SimulationRunner.run_mission(run loop)
        │ consumes plans/controls from:
        ├─ swarm/task_allocation.py  TaskAllocator  (tasks → vehicles)
        ├─ swarm/formation.py        FormationController (leader → target poses)
        └─ optimization/minimum_snap.py MinimumSnapOptimizer (poses → Trajectory)
        │
        └─ integration/hitl.py  HITLAdapter gates arm/set_mode/send_control
```

Concrete wiring required:
1. **Vehicle identity binding:** map AAS `DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID == i` to `MAVLinkBridge(system_id=i)` and `ROS2Bridge(namespace="/vehicle_i", domain_id=i)`, with ports `5760+i×10` (master) / `5501+i×10` (SITL) derived into `connection_string`s. This logic exists nowhere in apex — must be added (new module, e.g. `integration/fleet.py` or `swarm/fleet.py`).
2. **Gazebo adapter:** implement `SimulationInterface` for AAS Gazebo SITL (connect over the namespaced MAVLink/ROS2 ports, `step(dt)` drive, `get_state`/`send_control` via the bridges). Currently absent.
3. **Planner pipeline:** `TaskAllocator.allocate()` → assign tasks to vehicles → `FormationController.compute_formation_positions()` per leader → `MinimumSnapOptimizer.optimize(PlanningProblem)` per vehicle → `Trajectory` → `SimulationRunner` sends controls step-by-step. No orchestrator composes these today.
4. **ROS2 offboard/actions:** AAS's ROS2 action-based offboard/guided needs action-client support in `ROS2Bridge` (or a new action layer); `set_mode("GUIDED")` string in the runner is the only mode mechanism today.
5. **HITL gating:** wrap vehicle bridges with `HITLAdapter` where operator authorization is required; for fully autonomous swarm runs set `HITLConfig(enabled=False)` or `auto_approve_low_risk=True` to avoid blocking the <100 ms loop.

---

## 6. Build-vs-buy assessment

| Capability | Verdict | Rationale |
|---|---|---|
| Vehicle abstraction (`VehicleInterface`) | **BUILD (exists)** | Ships in apex; extend with fleet/identity config. No external dependency needed. |
| MAVLink / ROS2 / DDS bridges | **BUILD (exists)** | All three ship with simulation fallbacks. Add port-namespacing and multi-vehicle management on top. |
| Gazebo SITL `SimulationInterface` adapter | **BUILD (thin)** | AAS already supplies the Gazebo SITL surface (MIT). Apex needs only a thin concrete adapter (~1-2 modules) translating `SimulationInterface` calls to namespaced MAVLink/ROS2. "Buy" = reuse AAS surface as-is; no third-party purchase. |
| Swarm WTA for ≤20×20 | **BUILD (exists)** | Greedy allocator is sufficient and AGPL-compatible internally. |
| Swarm WTA beyond 20×20 | **BUILD wrapper + adopt approximate solver** | Context: exact WTA NP-complete beyond 20×20. Add an auction or greedy-randomized adapter around `TaskAllocator` rather than buying a proprietary solver. |
| Formation control | **BUILD (extend existing)** | Geometry exists; add collision avoidance + tracking controller. No market equivalent worth buying for a research swarm stack. |
| Trajectory optimization (min-snap, multi-vehicle) | **BUILD (extend existing)** | `MinimumSnapOptimizer` is a solid base; add multi-vehicle constraints and a <100 ms verification harness. Buying a proprietary trajectory optimizer conflicts with vendor-agnostic/AGPL goals. |
| Perception (YOLO+ONNX, LiDAR/KISS-ICP) | **INTEGRATE (buy/adopt components)** | Complete gap in apex. Integrate ONNX Runtime (YOLO) and KISS-ICP as a separate perception layer feeding `StateVector`; not core apex optimization. MIT-compatible components preferred to avoid contaminating AGPL. |
| HITL approval workflow | **BUILD (exists)** | Fully implemented; tune `HITLConfig` timeouts/auto-approve for the latency budget. |
| Fleet identity & port namespacing | **BUILD (new)** | Nothing exists; small new module mapping `i` → ports/IDs/namespaces. |

### Licensing note
apex-autopilot-optimization is AGPL-3.0 (strong copyleft, network-use triggering); AAS is MIT. Combining them is permissible (MIT code can be incorporated into an AGPL work), but the combined distributed work inherits AGPL obligations: source must be made available to users interacting with it over a network. Both stacks are vendor-agnostic (no V-BAT lock-in), satisfying the constraint. Keep perception components (YOLO weights, KISS-ICP) in a separate MIT-licensed integration layer to avoid license mixing where possible.

### Latency note
The <100 ms end-to-end benchmark (Hivemind reference) is not currently measured anywhere in apex. `MinimumSnapOptimizer` records `computation_time_ms`; `SimulationRunner` records wall-clock mission duration. A per-step timing harness (plan → control → send_control cycle) must be added before the integration can claim compliance.

---

## 7. Recommended next steps

1. Add `integration/fleet.py` (or `swarm/fleet.py`): `DRONE_ID/ROS_DOMAIN_ID/MAV_SYS_ID == i` binding, port derivation `5760+i×10` / `5501+i×10`, per-vehicle bridge factory producing namespaced `MAVLinkBridge`/`ROS2Bridge`.
2. Implement a concrete `SimulationInterface` for AAS Gazebo SITL (GAZEBO/SITL backend) and wire it into `SimulationRunner` via `sim_factory`.
3. Compose the planner pipeline: allocator → formation → minimum_snap → runner controls, per vehicle.
4. Extend `MinimumSnapOptimizer` with multi-vehicle deconfliction and add a <100 ms cycle-time harness; extend `TaskAllocator` with an approximate method for >20×20.
5. Add ROS2 action-client support to `ROS2Bridge` for AAS offboard/guided trajectories.
6. Configure `HITLAdapter` (enabled=False or auto-approve low-risk) for autonomous swarm runs; measure HITL latency contribution.
7. Extend `core/types.py` with fleet/perception/port-config types as the integration modules mature.
