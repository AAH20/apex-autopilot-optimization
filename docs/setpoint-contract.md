# Setpoint Contract: apex-autopilot-optimization → AAS Sim

**Kanban card:** t_732bb3ea (Wave 1 — MAVLink/ROS2 message contract; this doc is the downstream half, `docs/telemetry-contract.md` is the upstream half)
**Status:** Specification
**Direction:** Downstream setpoints/commands from apex-autopilot-optimization (optimization/governance layer) → AAS simulation (PX4/ArduPilot Gazebo SITL)
**Integration path:** MAVLinkBridge / ROS2Bridge → ROS2 actions/services/topics over DDS (uXRCE-DDS or MAVROS) → AAS `autopilot_interface_msgs` → PX4 Offboard / ArduPilot Guided → Gazebo SITL
**Grounding:**
- AAS ROS2 action structure: `autopilot_interface_msgs/action/{Takeoff, Offboard, Orbit, Land}`, `srv/{SetReposition, SetSpeed}`, `msg/OffboardFlag` (verified against `github.com/JacopoPan/aerial-autonomy-stack`, `aircraft/aircraft_ws/src/autopilot_interface_msgs/`)
- AAS topic convention: `/Drone{DRONE_ID}/...`, where `DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID` (AAS README + `state_sharing_node.cpp`)
- Apex core types: `src/apex_autopilot_optimization/core/types.py` (`Pose3D`, `Velocity3D`, `StateVector`, `ControlInput`, `Waypoint`, `Trajectory`, `PlanningProblem`, `PlanningResult`, `VehicleType`, `ComplexityClass`)
- Apex swarm: `src/apex_autopilot_optimization/swarm/{task_allocation.py, formation.py}` (greedy WTA; line/wedge/hexagon formations)
- Bridge implementations: `src/apex_autopilot_optimization/integration/{mavlink.py, ros2.py, dds.py, vehicle.py}`

---

## 1. Purpose

Defines the wire contract for control signals flowing **apex → AAS**: offboard velocity/position setpoints, position targets, formation positions, WTA assignments, mode changes, and safety/governance vetoes. The contract sits at the bridge boundary so AAS depends on a stable schema rather than apex-internal Python dataclasses, and so apex depends on a stable ROS2 schema rather than firmware-versioned `px4_msgs`/`mavros_msgs`.

All downstream topics/actions/services are **per-vehicle namespaced by DRONE_ID**: `/Drone{id}/...`, `{id}` = integer drone id = DRONE_ID = ROS_DOMAIN_ID = MAV_SYS_ID. A fleet-level aggregate topic (`/fleet/...`) allows apex to publish once and demultiplex by `drone_id` inside the message payload.

**Latency budget:** Hivemind benchmark requires <100 ms end-to-end (perception → decision → setpoint → actuator). The 10 Hz offboard heartbeat (§6) and 500 ms watchdog are sized to that budget.

---

## 2. Message Format

**Primary transport:** ROS2 (rclpy/rclcpp over DDS).
- **Reused AAS types (not redefined):** `autopilot_interface_msgs/action/Takeoff`, `Offboard`, `Orbit`, `Land`; `srv/SetReposition`, `SetSpeed`; `msg/OffboardFlag`. These carry maneuvers and ephemeral parameter changes.
- **New apex-side contract types (`.msg`):** live in ROS2 package `apex_control_msgs` (`src/apex_control_msgs/msg/`), consumed by apex's `ROS2Bridge` and AAS-side adapter nodes. `std_msgs/Header` provides `stamp` (ROS2 time; sim time when `use_sim_time:=true`) and `frame_id`.

**MAVLink parity:** §9 maps each contract signal to the equivalent MAVLink command/message for the MAVLinkBridge path (SET_POSITION_TARGET_LOCAL_NED, MAV_CMD_DO_SET_MODE, MAV_CMD_COMPONENT_ARM_DISARM, MAV_CMD_NAV_TAKEOFF/LAND).

---

## 3. .msg / .action File Definitions

### 3.1 Reused: AAS `autopilot_interface_msgs` actions (apex → AAS goals)

Topic roots: `/Drone{id}/takeoff_action`, `/Drone{id}/offboard_action`, `/Drone{id}/orbit_action`, `/Drone{id}/land_action` (ROS2 action goal/result/feedback topics live under `<root>/_action/...`).

**`Takeoff.action`** (AAS native):
```
float64 takeoff_altitude 50.0
float64 vtol_transition_heading 90.0
float64 vtol_loiter_north 150.0
float64 vtol_loiter_east 0.0
float64 vtol_loiter_alt 100.0
---
bool success
---
string message
```

**`Offboard.action`** (AAS native): starts/stops the continuous offboard setpoint stream for `max_duration_sec`; `controller_name` selects the AAS controller (`velocity`, `position`, `acceleration`, `rates`/CTBR).
```
string controller_name
float64 max_duration_sec 3.0
---
bool success
---
string message
```

**`Orbit.action`** (AAS native):
```
float64 east
float64 north
float64 altitude
float64 radius
---
bool success
---
string message
```

**`Land.action`** (AAS native):
```
float64 landing_altitude 50.0
float64 vtol_transition_heading 270.0
---
bool success
---
string message
```

### 3.2 Reused: AAS services (apex → AAS, request/response)

**`SetReposition.srv`** on `/Drone{id}/set_reposition` (quads only; NED east/north + altitude):
```
float64 east
float64 north
float64 altitude
---
bool success
string message
```

**`SetSpeed.srv`** on `/Drone{id}/set_speed` (ephemeral; applies from next command):
```
float64 speed
---
bool success
string message
```

### 3.3 New: `apex_control_msgs` messages (apex → AAS)

#### 3.3.1 OffboardSetpoint.msg — continuous 10 Hz setpoint heartbeat

```
# Continuous offboard setpoint stream (apex -> AAS).
# Published >= 10 Hz while OFFBOARD mode is active (PX4 offboard heartbeat).
# Bridge re-publishes the last valid setpoint at 10 Hz until replaced.
std_msgs/Header header          # stamp = ROS2/sim time; frame_id per `frame`
uint8  drone_id                 # DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID

# ---- Setpoint type ----
uint8  setpoint_type            # 0=UNSET, 1=VELOCITY_NED, 2=POSITION_NED, 3=ACCELERATION_NED, 4=BODY_RATES (CTBR)
uint8  frame                    # 0=NED earth-fixed, 1=BODY_FRD

# ---- Velocity setpoint (type=VELOCITY_NED / BODY_RATES) ----
float64 vx                      # m/s
float64 vy                      # m/s
float64 vz                      # m/s (positive up in NED)
float64 yaw_rate                # rad/s (body yaw rate for BODY_RATES)

# ---- Position/acceleration target (type=POSITION_NED / ACCELERATION_NED) ----
float64 x                       # m
float64 y                       # m
float64 z                       # m
float64 ax                      # m/s^2
float64 ay                      # m/s^2
float64 az                      # m/s^2
float64 yaw                     # rad target yaw

# ---- Validity ----
float64 duration_sec            # setpoint validity window; 0 = until replaced
```

Topic: `/Drone{id}/offboard/setpoint`. Direction: apex→AAS.

#### 3.3.2 FormationSetpoint.msg — per-drone formation target

```
# Per-drone formation position target (apex swarm/formation -> AAS).
# Published 10 Hz, locked to the offboard heartbeat cycle.
std_msgs/Header header
uint8  drone_id

uint8  formation_id             # formation session id (ties to the WTA/formation plan)
float64 x                       # m target position (NED / mission frame)
float64 y
float64 z
float64 yaw                     # rad target yaw
float64 spacing_m               # nominal inter-vehicle spacing for this slot
bool  slot_valid                # false = drone has no slot this cycle (hold last safe state)
```

Topic: `/Drone{id}/formation/setpoint`. Direction: apex→AAS.

#### 3.3.3 WTAAssignment.msg — winner-takes-all task assignment

```
# WTA task assignment (apex swarm/task_allocation -> AAS).
# Event-driven on re-allocation; re-published <= 1 Hz while stable.
std_msgs/Header header
uint32 task_id                  # apex task id (from swarm/task_allocation Task.id)
uint8  assigned_drone_id        # drone id winning this task; 0 = unassigned
uint8  previous_drone_id        # drone id previously assigned; 0 if none (handover signal)
float64 priority                # task priority used in allocation
float64 task_x                  # m task position
float64 task_y
float64 task_z
float64 assign_time             # ROS2 time of assignment
uint8  status                   # 0=PROPOSED, 1=ACKED, 2=REJECTED, 3=COMPLETED, 4=EXPIRED
```

Topics: `/Drone{id}/wta/assignment` (per-drone) and `/fleet/wta/assignments` (aggregate; demux key = `assigned_drone_id`). Direction: apex→AAS.

#### 3.3.4 ModeCommand.msg — explicit flight mode change

```
# Flight mode command (apex -> AAS).
# Event-driven; retried at 1 Hz until transition confirmed or timeout_sec elapses.
std_msgs/Header header
uint8  drone_id
uint8  target_mode              # 0=STABILIZE, 1=ACRO, 2=ALT_HOLD, 3=AUTO, 4=GUIDED,
                                # 5=OFFBOARD, 6=LOITER, 7=RTL, 8=LAND, 9=POSHOLD, 10=HOLD
string  mode_source             # "apex/governance", "apex/planner", "operator"
float64 timeout_sec             # bridge aborts transition if not confirmed within this (s)
```

Topic: `/Drone{id}/mode/command`. Direction: apex→AAS. Mode changes are also implicit in action goals (Takeoff/Land/Orbit/Offboard); this topic is for explicit mode transitions outside maneuvers.

#### 3.3.5 Veto.msg — safety/governance veto (latching)

```
# Safety/governance veto from apex layer to AAS (latching, TRANSIENT_LOCAL).
# Republished at 1 Hz while active; drone_id 0 = fleet-wide veto.
std_msgs/Header header
uint8  drone_id                 # 0 = applies to all vehicles in fleet
uint8  veto_type                # 0=CLEAR/RELEASE, 1=SOFT_HOLD, 2=HARD_EMERGENCY
uint8  severity                 # 1=INFO, 2=LOW, 3=MEDIUM, 4=HIGH, 5=CRITICAL
string  reason                  # veto reason (machine/human readable)
string  authority               # issuing authority: "apex/governance", "apex/safety", "apex/planner", "operator"
float64 valid_until             # ROS2 time after which veto auto-expires; 0 = indefinite
bool   require_clear_ack        # true = explicit CLEAR veto required before new setpoints accepted
```

Topic: `/Drone{id}/safety/veto`. Direction: apex→AAS. See §8 for behavior.

---

## 4. Topic / Action / Service Naming & DRONE_ID Namespacing

Pattern: `/Drone{id}/<group>/<topic>`, `{id}` = integer drone id.

| Contract endpoint | Type | Message / Action | Direction | Notes |
|---|---|---|---|---|
| `/Drone{id}/takeoff_action` | Action | `Takeoff` | apex→AAS | mode change implicit: arms + climbs to `takeoff_altitude` |
| `/Drone{id}/offboard_action` | Action | `Offboard` | apex→AAS | starts/stops offboard streaming (`controller_name`, `max_duration_sec`) |
| `/Drone{id}/orbit_action` | Action | `Orbit` | apex→AAS | orbit at east/north/altitude/radius |
| `/Drone{id}/land_action` | Action | `Land` | apex→AAS | descend to `landing_altitude` then land |
| `/Drone{id}/set_reposition` | Service | `SetReposition` | apex→AAS | ephemeral NED reposition |
| `/Drone{id}/set_speed` | Service | `SetSpeed` | apex→AAS | ephemeral speed command |
| `/Drone{id}/offboard/setpoint` | Topic | `OffboardSetpoint` | apex→AAS | **10 Hz heartbeat while OFFBOARD** |
| `/Drone{id}/formation/setpoint` | Topic | `FormationSetpoint` | apex→AAS | 10 Hz formation target |
| `/Drone{id}/wta/assignment` | Topic | `WTAAssignment` | apex→AAS | per-drone assignment |
| `/fleet/wta/assignments` | Topic | `WTAAssignment` | apex→AAS | fleet aggregate (demux by `assigned_drone_id`) |
| `/Drone{id}/mode/command` | Topic | `ModeCommand` | apex→AAS | explicit mode transition |
| `/Drone{id}/safety/veto` | Topic | `Veto` | apex→AAS | latching governance veto (§8) |
| `/Drone{id}/offboard_flag` | Topic | `OffboardFlag` | AAS→apex | `is_active`/`controller_name` status feedback |
| `/Drone{id}/telemetry/vehicle_telemetry` | Topic | `VehicleTelemetry` | AAS→apex | upstream contract (telemetry-contract.md) |

**Example (drone 3):** `/Drone3/offboard_action`, `/Drone3/offboard/setpoint`, `/Drone3/safety/veto`.

ROS2 action wire topics follow standard conventions (`/Drone{id}/offboard_action/_action/goal`, `.../_action/result`, `.../_action/feedback`, cancel via goal ID). Action goal IDs are generated by apex's bridge and logged for correlation with veto cancellations.

---

## 5. Control Rates & Timing

| Endpoint | Message | Rate | Basis / watchdog |
|---|---|---|---|
| `/Drone{id}/offboard/setpoint` | `OffboardSetpoint` | **≥10 Hz** while OFFBOARD active | PX4 OFFBOARD hard failsafe at ~0.5 s without setpoints (2 Hz); contract sets 10 Hz to fit the <100 ms end-to-end budget |
| Offboard setpoint watchdog | — | — | Bridge/AAS safety declares setpoint loss after **500 ms silence** → exit OFFBOARD → HOLD/LOITER; governor may raise veto |
| `/Drone{id}/formation/setpoint` | `FormationSetpoint` | 10 Hz | Locked to offboard heartbeat cycle |
| `/Drone{id}/wta/assignment` | `WTAAssignment` | Event-driven; re-publish ≤1 Hz while stable | Re-allocation on task change (greedy WTA, NP-complete exact methods intractable beyond 20×20 → greedy used) |
| `/Drone{id}/mode/command` | `ModeCommand` | Event-driven; retry 1 Hz until confirmed or `timeout_sec` | Confirmation via AAS `OffboardFlag`/telemetry `nav_state` |
| Takeoff/Land/Orbit/Offboard actions | `autopilot_interface_msgs/*` | Per maneuver | Feedback per action server (~1 Hz), result on completion |
| `/Drone{id}/set_reposition`, `/set_speed` | services | Request/response, fire-and-forget | Ephemeral |
| `/Drone{id}/safety/veto` | `Veto` | Publish on change; re-publish 1 Hz while active | Latching until CLEAR |
| `/Drone{id}/offboard_flag` | `OffboardFlag` | 5 Hz | AAS→apex status feedback |

**Sizing note:** PX4 Gazebo SITL limited to <10 vehicles; 4 GB RAM per Gazebo instance; <100 ms end-to-end budget. Per-topic bandwidth is modest; keep the 10 Hz setpoint + 5 Hz status per vehicle well under budget.

---

## 6. Mode Transition Sequence

Contract-mandated sequence for launching a vehicle into offboard control:

```
1. GUIDED      (ArduPilot) / POSCTL or current safe mode (PX4)
   └─► Vehicle holds position; apex computes plan; telemetry confirms GUIDED + disarmed/armed pre-flight OK
2. OFFBOARD    (PX4) / remain GUIDED (ArduPilot — no OFFBOARD equivalent; OFFBOARD step is PX4-specific)
   └─► PX4 accepts OFFBOARD only if offboard setpoints have been flowing (start ≥10 Hz heartbeat BEFORE or at this step)
3. ARM
   └─► MAV_CMD_COMPONENT_ARM_DISARM (param1=1); requires pre-flight checks pass
4. TAKEOFF
   └─► Takeoff action goal: takeoff_altitude; AAS offboard/takeoff controller manages climb
```

**Failure handling per step:**
- **OFFBOARD rejected:** bridge keeps streaming setpoints in GUIDED, retries mode change at 1 Hz; if PX4 never accepts (e.g., setpoint stream missed the 0.5 s window), governor raises `Veto(SOFT_HOLD)` and planner re-plans.
- **ARM rejected:** pre-flight checks failed (GPS fix, EKF, battery); no veto; planner waits, telemetry contract supplies `pre_flight_checks_pass`.
- **Takeoff fails:** action result `success=false`; governor decides LAND vs. retry.

**PX4 vs ArduPilot notes:**
- PX4: OFFBOARD requires the setpoint stream established before/within the mode switch; use CTBR `VehicleRatesSetpoint` (`setpoint_type=BODY_RATES`) for agile/GNSS-denied flight.
- ArduPilot: GUIDED mode accepts `setpoint_velocity`/`setpoint_accel` references; `OFFBOARD` target_mode is not applicable — skip step 2, remain GUIDED, then ARM + Takeoff.

---

## 7. Sequence Diagram

```mermaid
sequenceDiagram
    autonumbers
    participant APX as apex-autopilot-optimization<br/>planner + governor
    participant BRIDGE as apex ROS2 bridge<br/>(ROS2Bridge / MAVLinkBridge)
    participant DDS as DDS<br/>(uXRCE-DDS / Cyclone / Zenoh)
    participant AAS as AAS sim<br/>autopilot_interface action servers
    participant FW as Autopilot<br/>(PX4 SITL / ArduPilot)
    participant GZ as Gazebo SITL

    note right of APX: WTA assigns task → formation solver<br/>computes per-drone slots

    APX->>BRIDGE: WTAAssignment /drone{wid}/wta/assignment
    APX->>BRIDGE: FormationSetpoint /drone{id}/formation/setpoint
    APX->>BRIDGE: ModeCommand GUIDED /drone{id}/mode/command
    BRIDGE->>DDS: goal: GUIDED (MAV_CMD_DO_SET_MODE parity)
    DDS->>FW: set mode GUIDED
    FW->>GZ: hold position
    FW-->>AAS: OffboardFlag is_active=false
    AAS-->>BRIDGE: telemetry nav_state=GUIDED

    APX->>BRIDGE: Offboard action goal /drone{id}/offboard_action<br/>(controller_name=velocity, max_duration_sec)
    BRIDGE->>DDS: action goal
    DDS->>AAS: accept goal
    APX->>BRIDGE: OffboardSetpoint >= 10 Hz /drone{id}/offboard/setpoint
    loop every 100 ms while OFFBOARD
        BRIDGE->>DDS: setpoint (vx,vy,vz,yaw_rate)
        DDS->>AAS->>FW: SET_POSITION_TARGET_LOCAL_NED / rates
        FW->>GZ: fly setpoint
    end
    BRIDGE->>FW: ARM (MAV_CMD_COMPONENT_ARM_DISARM)
    FW->>GZ: motors armed
    APX->>BRIDGE: Takeoff action goal /drone{id}/takeoff_action<br/>(takeoff_altitude)
    BRIDGE->>DDS: action goal
    DDS->>AAS->>FW: MAV_CMD_NAV_TAKEOFF
    FW->>GZ: climb to altitude
    AAS-->>BRIDGE: result success=true

    note right of APX: Safety / governance veto path
    APX->>BRIDGE: Veto HARD /drone{id}/safety/veto<br/>(reason="geofence breach", authority=apex/governance)
    BRIDGE->>DDS: veto topic (TRANSIENT_LOCAL)
    DDS->>AAS: safety node latches veto
    AAS->>FW: cancel active action goals (ros2 action cancel)
    AAS->>FW: LAND action / MAV_CMD_NAV_LAND
    FW->>GZ: descend & land
    FW-->>AAS: landed + disarmed
    AAS-->>BRIDGE: telemetry armed=false, nav_state=LAND
    APX->>BRIDGE: Veto CLEAR /drone{id}/safety/veto
    DDS->>AAS: safety node releases latch
```

---

## 8. Veto Signal Spec (apex → AAS Safety/Governance)

### 8.1 Veto types

| Type | Code | Behavior on AAS side | Cleared by |
|---|---|---|---|
| CLEAR / RELEASE | 0 | Releases an active veto; normal setpoint acceptance resumes after state re-sync via telemetry contract | — |
| SOFT_HOLD | 1 | Reject new setpoints/goals; maintain last safe state (HOLD/LOITER); no disarm; offboard heartbeat may continue but no new targets accepted | CLEAR veto from same or higher authority |
| HARD_EMERGENCY | 2 | **Cancel all active action goals** (ROS2 action goal cancel via DDS), command LAND, disarm after landing confirmation; suppress new setpoints until CLEAR | CLEAR veto from same or higher authority |

### 8.2 Semantics

- **Latching:** `Veto` is published with `QoS RELIABLE + TRANSIENT_LOCAL, depth 10` and re-published at 1 Hz while active, so a late-joining AAS safety node receives the veto even if it starts after the veto was issued.
- **Fleet-wide:** `drone_id == 0` applies the veto to all vehicles (e.g., "all return-to-launch").
- **Authority chain:** `apex/governance` > `apex/safety` > `apex/planner` > `operator`. A veto can only be cleared by the same or a higher authority; `authority` is recorded on every veto. A drone cannot self-clear an apex veto.
- **Expiry:** `valid_until` (ROS2 time; 0 = indefinite). AAS safety node expires the veto automatically at `valid_until` and publishes CLEAR.
- **Ack requirement:** `require_clear_ack=true` means new setpoints stay suppressed until an explicit CLEAR arrives, even after expiry.
- **Precedence:** HARD_EMERGENCY overrides SOFT_HOLD; SOFT_HOLD overrides normal operation. Multiple simultaneous vetoes: highest severity wins.

### 8.3 Integration with offboard heartbeat

If the 10 Hz offboard setpoint stream lapses >500 ms while OFFBOARD is active, the bridge/AAS safety node behaves as if a SOFT_HOLD veto were raised (exit OFFBOARD → HOLD), logs the setpoint loss, and awaits governor decision. This is not a `Veto` message itself but is observable in telemetry (`nav_state` change) per the telemetry contract.

---

## 9. MAVLink Parity Mapping (MAVLinkBridge path)

| Contract signal | ROS2 endpoint | MAVLink message / command |
|---|---|---|
| OffboardSetpoint VELOCITY_NED | `/Drone{id}/offboard/setpoint` | `SET_POSITION_TARGET_LOCAL_NED` (type_mask: velocity-only) or MAVROS `setpoint_velocity` |
| OffboardSetpoint POSITION_NED | `/Drone{id}/offboard/setpoint` | `SET_POSITION_TARGET_LOCAL_NED` position |
| OffboardSetpoint BODY_RATES (CTBR) | `/Drone{id}/offboard/setpoint` | `SET_ATTITUDE_TARGET` rates / PX4 `VehicleRatesSetpoint` via `/fmu/in/vehicle_rates_setpoint` |
| ModeCommand (OFFBOARD/GUIDED/…) | `/Drone{id}/mode/command` | `MAV_CMD_DO_SET_MODE` custom_mode |
| ARM | `/Drone{id}/mode/command` + Takeoff action | `MAV_CMD_COMPONENT_ARM_DISARM` param1=1 |
| TAKEOFF | `/Drone{id}/takeoff_action` | `MAV_CMD_NAV_TAKEOFF` (pitch + takeoff_altitude) |
| LAND | `/Drone{id}/land_action` | `MAV_CMD_NAV_LAND` |
| HARD_EMERGENCY veto | `/Drone{id}/safety/veto` | action goal cancel (DDS) + `MAV_CMD_NAV_LAND`, then `MAV_CMD_COMPONENT_ARM_DISARM` param1=0 after landing |
| SetReposition | `/Drone{id}/set_reposition` | `MAV_CMD_DO_REPOSITION` |
| OffboardFlag status (AAS→apex) | `/Drone{id}/offboard_flag` | `HEARTBEAT` custom_mode + `COMMAND_ACK` |

MAV_SYS_ID = DRONE_ID provides vehicle demux on the MAVLink channel, matching the ROS2 topic namespace.

---

## 10. QoS Profiles

Mirroring `docs/telemetry-contract.md` §6:

| Profile | Reliability | Durability | History | Depth | Used for |
|---|---|---|---|---|---|
| QOS_COMMAND | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST | 10 | Mode commands, veto, action goals (must not be lost; late-joiner gets last command/veto) |
| QOS_SETPOINT | BEST_EFFORT | VOLATILE | KEEP_LAST | 10 | OffboardSetpoint, FormationSetpoint (10 Hz; drop OK, latest wins) |
| QOS_WTA | RELIABLE | VOLATILE | KEEP_LAST | 10 | WTA assignments (allocation must arrive) |
| QOS_SERVICE | RELIABLE | VOLATILE | KEEP_LAST | 10 | SetReposition / SetSpeed service clients |

RMW selection: `rmw_fastrtps_cpp` (default), `rmw_cyclonedds_cpp` (embedded), `rmw_zenoh_cpp` (fleet/WAN inter-vehicle bridge per AAS).

---

## 11. Compatibility & Versioning

- Schema version: `setpoint-contract v1`. Versioning via topic name; `drone_id` mandatory on every contract message (topics alone are not relied upon for demux, enabling single-publisher fleet patterns).
- Backward-compatible changes: append fields only at message end; never reorder or remove fields.
- AAS `autopilot_interface_msgs` action fields use defaults (e.g., `max_duration_sec 3.0`); apex must not rely on defaults changing.
- `px4_msgs` must match the PX4 firmware version running in AAS SITL (per integration-gap-report §3.4) when MAVLinkBridge parity path is used.

---

## 12. Open Items (from kanban card t_732bb3ea)

- Implement apex ROS2 adapter (`ROS2Bridge` send side) for `OffboardSetpoint`, `FormationSetpoint`, `WTAAssignment`, `ModeCommand`, `Veto` publishers and action clients (Takeoff/Offboard/Orbit/Land).
- Implement AAS-side adapter node consuming `/Drone{id}/offboard/setpoint` at 10 Hz and feeding PX4 `/fmu/in/*` or MAVROS setpoints.
- Wire the 500 ms setpoint-loss watchdog → OFFBOARD exit → HOLD, observable via telemetry contract.
- Implement veto latch node on AAS side (TRANSIENT_LOCAL veto store, cancel-action integration, CLEAR arbitration by authority).
- Confirm action namespaces in AAS launch: `/Drone{DRONE_ID}/takeoff_action|offboard_action|orbit_action|land_action` and services `/set_reposition|/set_speed`.
- Load-balance / RMW selection for fleets >10 vehicles given 4 GB RAM per Gazebo instance and <100 ms latency budget.