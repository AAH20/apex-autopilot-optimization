# Multi-Vehicle Runner Extension Specification

**Repository:** apex-autopilot-optimization (AGPL-3.0)
**Surface integrated:** Aerial Autonomy Stack (AAS, github.com/JacopoPan/aerial-autonomy-stack, MIT) — sim/runtime
**Integration path:** MAVLinkBridge + ROS2 topics between AAS sim/runtime and apex optimization/governance layer
**Related kanban card:** t_abeaf306
**Status:** Spec (design) — no implementation changes yet
**Parent component:** `src/apex_autopilot_optimization/simulation/runner.py` (`SimulationRunner`)

---

## 1. Objective and scope

Extend `SimulationRunner` from a single-vehicle connect/arm/plan/control/step/disconnect loop to an N-vehicle swarm orchestrator that:

1. Opens and manages **per-vehicle MAVLink connections** with port namespacing `5760 + i*10` (master) and `5501 + i*10` (SITL).
2. Maintains **distributed state** across N vehicles (one state vector per vehicle, freshness-tracked).
3. Runs a **swarm-level safety filter**: pairwise collision avoidance, geofence, no-fly zones.
4. Generates **formation-driven setpoints** (line / wedge / hexagon) from `swarm/formation.py`.
5. Executes **batch missions across the swarm** with per-vehicle problems and a synchronized step loop.
6. Integrates **Gazebo SITL multi-vehicle**: launch N PX4 SITL instances, connect each via MAVLink.
7. Aggregates **runner statistics**: per-vehicle plus swarm-level rollups.

**In scope:** design of `SwarmRunner` (new orchestration layer) plus the supporting managers/filters, the port/ID scheme, the Gazebo SITL launch procedure, the TDD test plan, and scalability limits. `SimulationRunner` single-vehicle behavior is unchanged (backward compatible).

**Out of scope:** AAS internals, PX4 firmware changes, ROS2 topic implementation details (referenced only), WTA solver replacement, HITL hardware, production deployment.

---

## 2. Grounding artifacts (existing APIs the spec builds on)

| File | Symbol | Role |
|---|---|---|
| `simulation/interface.py` | `SimulationInterface` (ABC) | connect/disconnect/get_state/send_control/arm/set_mode/reset/step; properties `is_connected`, `time_scale`; `SimulationBackend` enum {GAZEBO, AIRSIM, JMASIM, SITL, HITL} |
| `simulation/runner.py` | `SimulationRunner.run_mission(...)`, `.run_batch(...)`, `.get_runner_stats()` | Single-vehicle mission loop: connect → arm → set_mode(GUIDED) → plan/compute_control/safety-filter/send_control/step → disconnect |
| `simulation/config.py` | `SimulationConfig(backend, connection_string, lockstep, time_scale, vehicle_type, model)` | Per-session simulation config |
| `simulation/result.py` | `SimulationResult(success, trajectory, metrics, duration_seconds, message)` | Per-mission result |
| `integration/mavlink.py` | `MAVLinkBridge(VehicleInterface)` | MAVLink connection model: `connection_string` (udp:/tcp:/serial:/udpout:), `system_id`, `component_id`, `simulation` fallback mode, heartbeat-based `is_connected`, telemetry dict |
| `integration/vehicle.py` | `VehicleInterface` (ABC) | Vehicle-side protocol-agnostic contract (separate from the sim ABC) |
| `swarm/formation.py` | `FormationController.compute_formation_positions(leader: StateVector, num_agents: int) -> list[Pose3D]`; `FormationConfig(formation_type="line", spacing=2.0, max_agents=10)` | Formation setpoint generation for line/wedge/hexagon |
| `core/types.py` | `Pose3D.distance_to(other)`, `StateVector`, `Velocity3D`, `ControlInput`, `Waypoint`, `PlanningProblem`, `PlanningResult`, `Trajectory`, `VehicleType` | Core domain types |
| `tests/unit/test_simulation.py` | `TestSimulationRunner` | Existing mocked test style (MagicMock vs `SimulationInterface`, `patch("...runner.SimulationInterface", ...)`) to mirror for swarm tests |

Licensing note: apex is AGPL-3.0; AAS is MIT. Integration via MAVLink/ROS2 topic boundary keeps the two codebases at arm's length; no AAS code is copied into apex.

---

## 3. Design assumptions and constraints

- **Vendor-agnostic:** no V-BAT / Shield AI Hivemind lock-in; PX4 and ArduPilot SITL both supported through the same MAVLink connection model.
- **Latency budget:** end-to-end swarm cycle under 100 ms (Hivemind benchmark reference). Per-step formation + safety + step must fit in `dt = 0.05 s` (existing runner default) with headroom.
- **Gazebo SITL scale:** PX4 Gazebo SITL is limited to **under 10 vehicles** in practice; each Gazebo instance consumes ~4 GB RAM. N > 10 requires distributed AAS simulation (out of scope).
- **WTA scalability:** exact swarm task allocation is NP-complete and intractable beyond ~20×20; batch missions here are pre-assigned per vehicle (task allocation is an input, not solved by the runner).
- **ID/port coupling:** per AAS convention, `DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID == i` for vehicle slot `i`.
- **Failure independence:** one vehicle's connection/step failure must not abort the whole swarm; failures are recorded per vehicle and the swarm continues (best-effort), with an optional abort-on-any-failure flag.
- **No-op fallback path:** when no real backend is available, all vehicle sessions run in `MAVLinkBridge(simulation=True)` mode so the spec is unit-testable without Gazebo/PX4.

---

## 4. Port namespacing scheme

Vehicle slot `i` (0-based index within the swarm) reserves:

| Resource | Formula | Example (i = 0..3) | Notes |
|---|---|---|---|
| MAVLink master port | `5760 + i*10` | 5760, 5770, 5780, 5790 | PX4 SITL MAVLink link; `MAVLinkBridge` connects to `udp:127.0.0.1:<master_port>` |
| SITL/Gazebo sim port | `5501 + i*10` | 5501, 5511, 5521, 5531 | Gazebo↔PX4 sim link (sensor/actuator UDP) |
| MAV_SYS_ID / DRONE_ID / ROS_DOMAIN_ID | `i` | 0, 1, 2, 3 | Passed to PX4 as system ID; set as `ROS_DOMAIN_ID` for ROS2 topic namespacing |
| component_id | `1` | 1 | Fixed MAVLink component ID (autopilot) |
| MAVLink connection string | `udp:127.0.0.1:<5760+i*10>` | `udp:127.0.0.1:5760` | Built by `SwarmConnectionManager`; overrides allowed via `vehicle_overrides[i].connection_string` |

**Validation rules:**
- `i` must be unique per swarm; duplicate slots rejected at swarm construction.
- Ports must be free before launch; the launcher probes `5760+i*10` and `5501+i*10` (bind test) and refuses to start a vehicle whose ports collide with an already-running instance or a reserved system port.
- `MAVLinkBridge.system_id == i`; MAVLink system ID `0` is reserved/broadcast — slot `0` is reserved for the ground station/operator unless the caller explicitly opts in; vehicles should be allocated from `i = 1` upward, or the caller shifts `system_id = i + 1` while keeping ports at `5760 + i*10`.
- Maximum usable `i` is bounded by ephemeral-port exhaustion (see §12).

**Config addition** (`simulation/config.py` — backward compatible, new optional fields):

```python
@dataclass(slots=True)
class SwarmSimulationConfig(SimulationConfig):
    swarm_size: int = 1
    base_master_port: int = 5760      # port stride is fixed at 10 (AAS convention)
    base_sitl_port: int = 5501
    start_slot: int = 0               # first vehicle slot index
    abort_on_any_failure: bool = False
    formation: FormationConfig | None = None
    safety: SwarmSafetyConfig | None = None   # §9
```

---

## 5. Architecture

```
SwarmRunner (orchestrator, extends the SimulationRunner loop pattern to N vehicles)
├── SwarmConnectionManager        # per-vehicle MAVLink connect/disconnect/health
├── SwarmStateStore               # distributed state: slot -> (StateVector, ts, freshness)
├── SwarmSafetyFilter             # collision avoidance, geofence, no-fly zones
├── FormationSetpointGenerator    # wraps swarm/formation.py FormationController
├── SwarmBatchExecutor            # per-vehicle problems, synchronized dt step loop
├── GazeboSITLLauncher            # launch N PX4 SITL instances, health-check, teardown
└── SwarmStatsAggregator          # per-vehicle + swarm-level statistics
```

**Core types added:**

- `VehicleSession(vehicle_id, mavlink: MAVLinkBridge, sim: SimulationInterface | None, state: StateVector | None, status, telemetry, stats)` — one per vehicle slot.
- `SwarmMissionResult(per_vehicle: dict[int, SimulationResult], swarm: SwarmAggregateStats, makespan_seconds, formation_deviation_m, safety_violations, collision_events)` — aggregate result.
- `SwarmSafetyConfig(min_separation_m, geofence: Polygon | None, z_min/z_max, no_fly_zones: list[ExclusionZone], failsafe_mode: str = "RTL")`.
- `ExclusionZone(center: Pose3D, radius_m: float, z_min: float | None, z_max: float | None)`.

**Key invariant:** every public method of `SwarmRunner` accepts and returns plain dataclasses/primitives (no Gazebo/PX4 types leak), so the single-vehicle `SimulationRunner` contract is preserved and the swarm path is testable with mocked `MAVLinkBridge` and `SimulationInterface`.

---

## 6. Connection management

**`SwarmConnectionManager`** owns the lifecycle of N `MAVLinkBridge` instances:

1. `connect_all(swarm_size, start_slot, base ports) -> dict[int, bool]` — for each slot `i`:
   - Build connection string `udp:127.0.0.1:{5760 + i*10}`.
   - Instantiate `MAVLinkBridge(connection_string=..., system_id=i, component_id=1, simulation=<flag>)`.
   - Call `connect(connection_string)` with retry: 3 attempts, exponential backoff 50 ms → 100 ms → 200 ms; timeout per attempt bounded so total connect wall time stays under the 100 ms budget contribution allowance.
   - On success, mark session `CONNECTED`; on failure, mark `CONNECTION_FAILED` and continue with remaining slots (never abort the whole swarm for one bad connection unless `abort_on_any_failure`).
2. `disconnect_all() -> dict[int, bool]` — tear down every bridge in reverse slot order; exceptions in one bridge do not prevent others from closing (mirrors `runner.py`'s `finally: sim.disconnect()` guarantee, scaled to N).
3. `health_check_all() -> dict[int, bool]` — poll `is_connected()` (heartbeat timeout 5 s in `MAVLinkBridge`) on every bridge; return per-slot health; unhealthy sessions are quarantined and excluded from the step loop.
4. `get_bridge(i) -> MAVLinkBridge` — accessor for the step loop to call `get_state`/`send_control`/`arm`/`set_mode`/`get_telemetry` per vehicle.

**Connection string validation** reuses `MAVLinkBridge._validate_connection_string` (udp:/tcp:/serial:/udpout: prefixes); malformed strings raise `ConnectionError` and are recorded as a per-vehicle failure, not a crash.

**Failure modes documented:** bridge process dead, heartbeat timeout, port already in use, pymavlink missing (falls back to simulation mode — logged at WARNING), Gazebo instance not yet up (retry covers startup race).

---

## 7. Distributed state tracking

**`SwarmStateStore`** holds the single source of truth for swarm state:

- `update(vehicle_id, state: StateVector)` — atomic per-slot write with `time.time()` timestamp.
- `snapshot() -> dict[int, StateVector]` — returns a copy of the latest state per connected vehicle (used by safety filter and formation generator so all consumers see a consistent instant).
- `get(vehicle_id) -> StateVector | None` — latest state for one vehicle.
- `is_fresh(vehicle_id, max_age_s) -> bool` — staleness check against `state.timestamp`.
- `stale_slots(max_age_s) -> list[int]` — slots whose state is older than `max_age_s`; the step loop skips control for stale vehicles and logs a safety event.

**Distribution contract:** the step loop reads once from the store (snapshot), computes per-vehicle controls, and writes back each vehicle's new state after the step. No vehicle acts on another vehicle's stale state older than one cycle. This bounds cross-vehicle coupling to one `dt` and keeps the cycle deterministic.

---

## 8. Swarm-level safety filter

**`SwarmSafetyFilter.filter(state_store, per_vehicle_controls: dict[int, ControlInput]) -> dict[int, ControlInput]`** runs after each vehicle's controller and before `send_control`. Layers, in order:

1. **Collision avoidance (pairwise):** for every pair `(a, b)` of connected vehicles with fresh states, if `Pose3D.distance_to(a_pose, b_pose) < min_separation_m`, scale both vehicles' control inputs toward zero (hover/hold) and record a violation. O(N²) pairwise check; for N above a threshold (default 20) switch to a spatial-hash broad phase (noted as future optimization).
   - Grounded in existing `Pose3D.distance_to` (`core/types.py`).
2. **Geofence:** reject/clamps setpoints outside the configured 2D polygon or outside `[z_min, z_max]`; violating vehicle's control is replaced with a hold command and a violation is recorded.
3. **No-fly zones:** list of `ExclusionZone` (sphere + optional height band); any vehicle whose predicted next state enters a zone gets a hold/RTL failsafe control and a violation.
4. **Failsafe:** on any safety violation for vehicle `i`, command `failsafe_mode` (default `"RTL"` via `set_mode`) and mark session `SAFETY_HOLD`; vehicle remains connected but under safety control until cleared.

Outputs per-vehicle filtered controls plus a `SafetyReport(violations: list[SafetyViolation], collision_events: list[(i, j)])`. The report feeds `SwarmStatsAggregator`.

**Latency note:** pairwise safety is the dominant O(N²) cost; measured per-cycle time must stay under the ~50 ms control-safety budget of the 100 ms end-to-end target.

---

## 9. Formation-driven setpoint generation

**`FormationSetpointGenerator`** wraps `swarm/formation.py`:

- Holds `FormationConfig(formation_type, spacing, max_agents)`; supported `formation_type` values: `"line"`, `"wedge"`, `"hexagon"` (existing implementation; unknown values fall back to line).
- `compute_setpoints(leader_state: StateVector, num_agents: int) -> list[Pose3D]` — delegates to `FormationController.compute_formation_positions`.
- `slot_setpoint(slot_index, leader_state, num_agents) -> Pose3D` — returns the formation slot assigned to vehicle `i` (slot `i` ↔ position `i` in the returned list).
- Leader selection: vehicle slot `0` (or `start_slot`) is default leader; configurable `leader_slot`. The leader follows its own mission waypoint; followers track formation offsets relative to the leader's latest state from `SwarmStateStore`.

Integration point in the step loop: for each vehicle `i`, `planner.plan(problem_i, state_i)` produces a trajectory; the formation generator overlays the slot offset on the leader's trajectory to produce the setpoint sent to `controller.compute_control`. Pure formation missions (no planner) use the slot pose directly as the setpoint.

`FormationConfig.max_agents` default 10 matches the Gazebo SITL practical limit; swarms larger than `max_agents` require a config change and explicit acceptance of the scalability limits in §12.

---

## 10. Batch mission execution

**`SwarmRunner.run_swarm_mission(...)`** — the swarm analogue of `run_mission`:

```
Inputs:
  problems: dict[int, PlanningProblem]  # one problem per participating vehicle slot
  config: SwarmSimulationConfig
  components per vehicle (planner/optimizer/safety/controller/estimator) or no-op defaults
  formation: FormationConfig | None
  safety: SwarmSafetyConfig | None
  dt: float = 0.05, max_steps: int = 1000  # same defaults as run_mission
```

**Lifecycle:**
1. `connect_all`; if zero vehicles connect → return failure `SwarmMissionResult` immediately.
2. `arm` + `set_mode("GUIDED")` per vehicle (per-vehicle failure recorded, not fatal).
3. Synchronized step loop for `max_steps`:
   - Snapshot state store.
   - Per vehicle `i` with fresh state: `plan` → `compute_control` → formation overlay → `SwarmSafetyFilter.filter` → `send_control`; failures recorded per vehicle, loop continues.
   - `sim.step(dt)` per vehicle (Gazebo backends step their own instance; the runner drives each instance sequentially within the cycle — wall time must fit the latency budget).
   - Update state store from `get_state` per vehicle.
   - Terminate early when all vehicles report mission complete (planner returned terminal / waypoint reached) or all are failed.
4. `disconnect_all` in `finally` (guaranteed teardown, mirrors single-vehicle `runner.py`).
5. Return `SwarmMissionResult` with per-vehicle `SimulationResult`s plus swarm aggregates.

**`run_swarm_batch(problems_per_vehicle: list[dict[int, PlanningProblem]], config, ...)`** — repeated swarm missions (batch of batches); stats accumulate across all.

Per-vehicle partial failure semantics: one vehicle failing to arm/step does not cancel others unless `abort_on_any_failure=True`; each vehicle's outcome is captured in its own `SimulationResult`.

---

## 11. Gazebo SITL launch procedure (multi-vehicle)

**`GazeboSITLLauncher`** (thin orchestrator over PX4/Gazebo CLI; no PX4 source changes):

For each vehicle slot `i` in `0..N-1`:

1. **Reserve ports:** bind-test `5760 + i*10` and `5501 + i*10`; fail fast if occupied.
2. **Environment:** `PX4_SYS_AUTOSTART` for iris quadrotor, `PX4_SIM_MODEL=iris`, `PX4_GZ_MODEL_POSE` per-vehicle offset (optional formation anchor), `ROS_DOMAIN_ID=i`, `MAV_SYS_ID=i`, `HEADLESS=1` (no GUI — saves RAM and is required for dense swarms).
3. **Launch:** start the PX4 SITL instance (`px4` / `make px4_sitl_default gazebo` per AAS integration) bound to:
   - MAVLink UDP master: `127.0.0.1:{5760 + i*10}`
   - Sim/Gazebo link UDP: `127.0.0.1:{5501 + i*10}`
   - Record the OS process PID per slot in `LauncherManifest(slot, pid, ports, log_path)`.
4. **Health check:** `SwarmConnectionManager.connect_all` with retry (covers the PX4/Gazebo startup race); treat heartbeat as ready signal.
5. **Logs:** redirect stdout/stderr of each instance to `logs/sitl/vehicle_{i}.log`; on launch failure, attach the tail of the log to the per-vehicle error.
6. **Teardown:** on `disconnect_all` or swarm shutdown, send SIGTERM then SIGKILL (with grace period) to each recorded PID; verify port release; report any orphaned Gazebo/PX4 processes.

**Concurrency model:** instances are launched sequentially to avoid Gazebo server port/lock contention at startup, then run in parallel during the mission. The runner's step loop drives them sequentially within each `dt` cycle (single-threaded, deterministic); parallel stepping is a noted future optimization.

---

## 12. Runner statistics aggregation

**`SwarmStatsAggregator`** maintains two levels:

**Per-vehicle stats (per slot `i`):**
- missions_run, missions_success, missions_fail
- total_duration_seconds, mean_step_latency_ms, p95_step_latency_ms
- connection_failures, safety_violations, collision_involved (with which slots)
- min_observed_separation_m, distance_flown_m, last_state_timestamp

**Swarm-level rollup:**
- total_missions (sum across vehicles), successful/failed counts, overall success rate
- swarm_makespan_seconds (max per-vehicle mission duration — the swarm is only done when the last vehicle finishes)
- total_safety_violations, total_collision_events
- mean_formation_deviation_m (mean distance of each vehicle from its assigned formation slot; max formation deviation for worst case)
- steps_total, mean/p95 cycle latency vs the 100 ms end-to-end budget (pass/fail flag)
- connected_vehicles / N ratio at mission start and end

**API:**
- `record_mission(vehicle_id, result: SimulationResult, cycle_latency_ms, separation_m, formation_deviation_m)`
- `get_vehicle_stats(vehicle_id) -> dict`
- `get_swarm_stats() -> dict` — the rollup above
- `get_runner_stats()` — kept for backward compatibility with `SimulationRunner.get_runner_stats()` shape (total/successful/failed missions + duration), aggregated across the swarm.

Stats are thread-friendly (single-threaded step loop; locks only if a future async step mode is added).

---

## 13. TDD test plan

Test file: `tests/unit/test_multi_vehicle_runner.py` (mirrors `tests/unit/test_simulation.py` style: pytest, `MagicMock(spec=...)`, `patch("...runner.SimulationInterface", ...)` and `patch("...integration.mavlink.MAVLinkBridge", ...)`).

**Phase RED (tests first, all fail):**

Unit (mocked backend):
1. `test_port_namespacing_formulas` — `master_port(i) == 5760 + i*10`, `sitl_port(i) == 5501 + i*10`.
2. `test_connect_all_creates_one_bridge_per_slot` — N mocked bridges, each `connect` called with `udp:127.0.0.1:<port>`, `system_id == i`.
3. `test_connect_all_partial_failure_continues` — one bridge `connect` returns False; others still connected; result maps per slot.
4. `test_disconnect_all_closes_even_on_failure` — one bridge `disconnect` raises; rest still closed; no exception propagates.
5. `test_state_store_snapshot_and_staleness` — update two slots, snapshot returns both; stale slot detected after max_age_s.
6. `test_formation_integration_produces_slot_poses` — line/wedge/hexagon via `FormationController`; slot `i` gets position `i`.
7. `test_safety_filter_collision_avoidance` — two vehicles closer than `min_separation_m` → both controls zeroed/hold, violation recorded.
8. `test_safety_filter_geofence_and_no_fly` — out-of-geofence and inside exclusion zone → hold + violation.
9. `test_run_swarm_mission_success_mocked` — N=3, all mocked OK → per-vehicle success + swarm rollup non-empty.
10. `test_run_swarm_mission_one_vehicle_fails_others_continue` — vehicle 1 step fails; vehicles 0 and 2 complete.
11. `test_abort_on_any_failure_stops_swarm` — flag set → first failure ends loop, others marked aborted.
12. `test_get_swarm_stats_rollup` — makespan, success rate, safety violation counts correct.
13. `test_backward_compatible_single_vehicle` — existing `SimulationRunner.run_mission` untouched (reuses existing tests in test_simulation.py).

Integration (Gazebo SITL, gated on `GZ_SITL_AVAILABLE` env):
14. `test_launch_two_sitl_instances` — N=2, ports 5760/5770 and 5501/5511 free, both connect, heartbeat OK, teardown releases ports.
15. `test_port_collision_refused` — second launcher for occupied port raises before starting PX4.
16. `test_swarm_mission_sitl_n3` — N=3 formation mission end-to-end under Gazebo; all disconnect after.

Scalability (mocked, timing):
17. `test_cycle_latency_under_budget` — N up to 10, measure per-cycle wall time; assert < 50 ms control+safety portion (proxy for the 100 ms end-to-end target).
18. `test_port_exhaustion_bound` — compute max slots before `5760 + i*10` collides with common services / ephemeral start; document bound, no crash at boundary.
19. `test_ram_estimate_vs_available` — `4 GB * N` vs `psutil.virtual_memory().available`; assert recommendation matches §12 limits.

**Phase GREEN:** implement `SwarmRunner` + managers until all tests pass; then `ruff` + `mypy strict` clean.

**Phase REFACTOR:** extract `SwarmSafetyFilter` spatial broad phase if N > 20 timing shows O(N²) dominance; keep public API stable.

Coverage gate: 100% line/branch coverage on new `simulation/swarm_runner.py` module (mirrors repo pytest config).

---

## 14. Scalability limits and failure modes

| Limit | Bound | Basis |
|---|---|---|
| Gazebo SITL vehicles | N < 10 (recommended) | Context bottleneck: PX4 Gazebo SITL limited to under 10 vehicles |
| RAM per instance | ~4 GB | Context bottleneck; host RAM must satisfy `4 GB * N + OS headroom`; e.g. 16 GB host ⇒ N ≤ 3–4 with GUI, slightly more headless |
| Port range per swarm | `5760 + i*10` and `5501 + i*10` for i in `0..N-1` | Stride 10 (AAS convention); N vehicles span 10*N ports each family |
| MAV_SYS_ID range | i ∈ [1, 254] for vehicles | MAVLink system ID 0 reserved/broadcast, 255 ground station; slot 0 reserved unless opted in |
| Port exhaustion | Practical ceiling well below 65535: with base 5760/5501 and stride 10, N must keep `5760 + 10*(N-1)` and `5501 + 10*(N-1)` below ephemeral-port start and clear of well-known services | Compute at launcher init via bind-test; no hardcoded N cap beyond the above |
| End-to-end latency | < 100 ms per cycle | Hivemind benchmark reference; pairwise safety O(N²) dominates — spatial broad phase required beyond ~20 vehicles |
| WTA scale | > 20×20 intractable (exact) | Context bottleneck; batch missions are pre-assigned, not solver-driven |

**Failure modes:**
- Gazebo instance fails to start → launcher reports per-slot error; swarm continues with remaining vehicles.
- MAVLink heartbeat lost mid-mission → session quarantined, vehicle excluded from step loop, safety violation logged, reconnect attempted on next mission.
- One vehicle step failure → recorded per-vehicle; swarm continues unless `abort_on_any_failure`.
- Port collision at launch → fail fast before any PX4 process starts for that slot; clean teardown of already-launched slots.

---

## 15. Open questions / out of scope

- ROS2 topic namespacing details (`DRONE_ID == ROS_DOMAIN_ID`) — referenced from AAS convention; topic mapping lives in the AAS integration layer, not this spec.
- Asynchronous / multi-threaded step loop — v2; single-threaded deterministic cycle first.
- Dynamic swarm (vehicles joining mid-mission) — v2; fixed N per mission here.
- HITL hardware connections — `MAVLinkBridge` serial path supports it, but not exercised by this spec.

---

## 16. Deliverable mapping to implementation

New file: `src/apex_autopilot_optimization/simulation/swarm_runner.py` containing `SwarmRunner`, `SwarmConnectionManager`, `SwarmStateStore`, `SwarmSafetyFilter`, `FormationSetpointGenerator`, `GazeboSITLLauncher`, `SwarmStatsAggregator`, and the result/session dataclasses. `SimulationRunner` and `SimulationInterface` remain unchanged; `SimulationConfig` gains optional swarm fields (backward compatible). Tests under `tests/unit/test_multi_vehicle_runner.py` per §13.