# Telemetry Contract: AAS Sim → apex-autopilot-optimization

**Kanban card:** t_732bb3ea (Wave 1 — MAVLink/ROS2 message contract)
**Status:** Specification
**Direction:** Upstream telemetry from AAS simulation (PX4/ArduPilot Gazebo SITL) → apex-autopilot-optimization (optimization/governance layer)
**Integration path:** MAVLinkBridge + ROS2 topics over DDS (uXRCE-DDS)
**Grounding:** AAS ROS2 topic structure in `/home/aah/aas-repo/aircraft/aircraft_ws/` (`state_sharing_node.cpp`, `px4_interface.cpp`, `px4_offboard.cpp`, `yolo_node.py`, `dds_topics.yaml`) and apex core types (`src/apex_autopilot_optimization/core/types.py`: `Pose3D`, `Velocity3D`, `StateVector`, `ControlInput`).

---

## 1. Purpose

Defines the wire contract for vehicle telemetry published by the AAS simulation runtime and consumed by apex-autopilot-optimization. The contract sits at the bridge boundary so apex depends on a stable schema rather than directly on firmware-versioned `px4_msgs`. AAS publishes native PX4 topics; an aggregator node (AAS side) republishes them as contract messages; apex consumes via its ROS2 adapter (`VehicleInterface` ABC → `StateVector`).

Topics are **per-vehicle namespaced by DRONE_ID** (`/Drone{id}/...`), where per AAS convention `DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID`. A fleet-level aggregate topic allows apex to subscribe once and demultiplex by `drone_id`.

---

## 2. Message Format

**Primary:** ROS2 `.msg` (rclpy/rclcpp over DDS). AAS already runs ROS2 nodes publishing `px4_msgs` and `vision_msgs`; apex consumes via `rclpy`. Custom aggregated `.msg` types form the stable contract boundary.

**MAVLink parity:** §8 maps each contract field to the equivalent MAVLink message for the MAVLinkBridge path (HEARTBEAT, ATTITUDE, GLOBAL_POSITION_INT, BATTERY_STATUS, GPS_RAW_INT, DETECTION/ODIN-style vision topics).

**Files defined (§3):**
- `VehicleTelemetry.msg` — aggregated per-vehicle telemetry (pose, velocity, battery, GPS, mode, armed)
- `YoloDetection.msg` — single detection
- `YoloDetectionArray.msg` — detection array

**Not redefined here (reference AAS native types):** `px4_msgs::msg::VehicleOdometry`, `VehicleGlobalPosition`, `VehicleLocalPosition`, `VehicleStatus`, `BatteryStatus`, `SensorGps`; `vision_msgs::msg::Detection2DArray`. The contract aggregates a snapshot of these into `VehicleTelemetry`.

---

## 3. .msg File Definitions

Live in a ROS2 package `apex_telemetry_msgs` (e.g. `src/apex_telemetry_msgs/msg/`). `std_msgs/Header` provides `stamp` (ROS2 time; sim time when `use_sim_time:=true`) and `frame_id`.

### 3.1 VehicleTelemetry.msg

```
# Aggregated upstream telemetry for ONE vehicle (AAS sim -> apex).
# Topic: /Drone{id}/telemetry/vehicle_telemetry  and  /fleet/telemetry/aggregate
# One message per vehicle per publish cycle; fields are latest-snapshot values.

std_msgs/Header header          # stamp = ROS2/sim time; frame_id = "base_link"/"odom"
uint8  drone_id                 # DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID (AAS convention)

# ---- Pose (from /fmu/out/vehicle_odometry, /fmu/out/vehicle_local_position) ----
float64 x                       # m, position (frame per pose_frame, default NED)
float64 y
float64 z
float64 roll                    # rad
float64 pitch
float64 yaw
uint8  pose_frame               # VehicleOdometry.pose_frame: 1=NED earth-fixed, 2=FRD world-fixed

# ---- Velocity (from /fmu/out/vehicle_odometry) ----
float64 vx                      # m/s
float64 vy
float64 vz
uint8  velocity_frame           # VehicleOdometry.velocity_frame

# ---- Battery (from /fmu/out/battery_status) ----
float32 battery_voltage         # V
float32 battery_current         # A (negative = discharging)
float32 battery_remaining       # 0..1 fraction remaining
uint8  battery_charge_state     # BatteryStatus.BATTERY_CHARGING_STATE_* enum

# ---- GPS / global position (from /fmu/out/vehicle_gps_position, /fmu/out/vehicle_global_position) ----
float64 lat                     # deg WGS84
float64 lon                     # deg WGS84
float32 alt_amsl                # m AMSL
float32 alt_ellipsoid           # m
uint8  gps_fix_type             # GPS fix type (0=no GPS … 5=RTK fixed)
uint8  nsat                     # number of satellites
float32 eph                     # m horizontal error
float32 epv                     # m vertical error
float32 ground_speed            # m/s

# ---- Mode & armed status (from /fmu/out/vehicle_status) ----
uint8  nav_state                # PX4 navigation state (OFFBOARD=14, AUTO_MISSION=15, HOLD=4, …)
uint8  arming_state             # 1=DISARMED, 2=ARMED
uint8  vehicle_type             # 1=ROTARY_WING, 2=FIXED_WING, 3=ROVER
bool   pre_flight_checks_pass
bool   is_vtol
bool   in_transition_mode

# ---- Provenance ----
uint64 timestamp_us             # PX4 timestamp (micros) of the source update
string source                   # originating AAS node (e.g. "px4_interface", "yolo_node")
```

### 3.2 YoloDetection.msg

```
# Single YOLO detection (AAS yolo_node -> apex). Wire-compatible with vision_msgs/Detection2D fields.
std_msgs/Header header
uint8  drone_id
string class_id                 # class label (from COCO names file)
float64 score                   # 0..1 confidence
# Bounding box, normalized image coordinates (0..1)
float64 center_x
float64 center_y
float64 size_x
float64 size_y
# YOLO26 3D direction estimate (px4_offboard reads pose.pose.position.x/y as az/el deg)
float64 azimuth_deg             # deg
float64 elevation_deg           # deg
float64 depth_m                 # m, NaN when depth unavailable
```

### 3.3 YoloDetectionArray.msg

```
# Array of detections for one vehicle; mirrors vision_msgs/Detection2DArray structure.
YoloDetection[] detections
```

**AAS native YOLO topic:** yolo_node publishes `vision_msgs::msg::Detection2DArray` on `/detections` (remappable to `/yolo/detections`), ~15 Hz (`px4_offboard.cpp` comment). The contract topic `/Drone{id}/yolo/detections` carries `YoloDetectionArray`; an adapter converts `Detection2DArray` → `YoloDetectionArray` at the AAS boundary.

---

## 4. Topic Naming & DRONE_ID Namespacing

Pattern: `/Drone{id}/<group>/<topic>`, `{id}` = integer drone id = DRONE_ID = ROS_DOMAIN_ID = MAV_SYS_ID.

| Contract topic | Message | Direction | Notes |
|---|---|---|---|
| `/Drone{id}/fmu/out/vehicle_odometry` | VehicleTelemetry (pose/velocity subset) | AAS→apex | AAS native topic, republished |
| `/Drone{id}/fmu/out/vehicle_global_position` | VehicleTelemetry (GPS subset) | AAS→apex | AAS native |
| `/Drone{id}/fmu/out/vehicle_local_position` | VehicleTelemetry (pose/velocity subset) | AAS→apex | `_v1` suffixed since PX4 1.17 |
| `/Drone{id}/fmu/out/vehicle_status` | VehicleTelemetry (mode/armed subset) | AAS→apex | `_v1` suffixed since PX4 1.16 |
| `/Drone{id}/fmu/out/battery_status` | VehicleTelemetry (battery subset) | AAS→apex | commented in dds_topics.yaml; enable |
| `/Drone{id}/fmu/out/vehicle_gps_position` | VehicleTelemetry (GPS subset) | AAS→apex | commented in dds_topics.yaml; enable |
| `/Drone{id}/telemetry/vehicle_telemetry` | VehicleTelemetry (full aggregate) | AAS→apex | per-vehicle aggregated output |
| `/Drone{id}/yolo/detections` | YoloDetectionArray | AAS→apex | per-camera/drone YOLO output |
| `/fleet/telemetry/aggregate` | VehicleTelemetry | AAS→apex | **multi-vehicle aggregate** (demux by drone_id) |
| `/fleet/telemetry/command` | (downstream, out of scope) | apex→AAS | reserved for ControlInput commands |

**Example (drone 3):** `/Drone3/fmu/out/vehicle_odometry`, `/Drone3/telemetry/vehicle_telemetry`, `/Drone3/yolo/detections`.

AAS already uses this exact prefix in `state_sharing_node.cpp` (`"/Drone" + std::to_string(drone_id_) + "/fmu/out/..."`) and `imu_publisher_node.cpp`, confirming the convention.

---

## 5. Publish Rates per Topic

Rates grounded in AAS source comments and PX4 defaults. The aggregator publishes `VehicleTelemetry` at a fixed 20 Hz (latest-snapshot conflation), regardless of source topic rates.

| Topic | Message | Publish rate | Basis |
|---|---|---|---|
| `/Drone{id}/fmu/out/vehicle_odometry` | VehicleTelemetry | 100 Hz | `px4_interface.cpp` comment |
| `/Drone{id}/fmu/out/vehicle_local_position` | VehicleTelemetry | 100 Hz | `px4_interface.cpp` comment |
| `/Drone{id}/fmu/out/vehicle_global_position` | VehicleTelemetry | 100 Hz | `px4_interface.cpp` comment |
| `/Drone{id}/fmu/out/vehicle_status` | VehicleTelemetry | 2 Hz | `px4_interface.cpp` comment (2 Hz) |
| `/Drone{id}/fmu/out/battery_status` | VehicleTelemetry | 10 Hz | PX4 default `battery_status` publication |
| `/Drone{id}/fmu/out/vehicle_gps_position` | VehicleTelemetry | 10 Hz | PX4 default GPS publication |
| `/Drone{id}/telemetry/vehicle_telemetry` | VehicleTelemetry | 20 Hz | aggregator latest-snapshot rate |
| `/Drone{id}/yolo/detections` | YoloDetectionArray | 15 Hz | `px4_offboard.cpp` comment ("// 15Hz") |
| `/fleet/telemetry/aggregate` | VehicleTelemetry | 20 Hz | fleet aggregator, one msg/vehicle/cycle |

**Sizing note (from project context):** Hivemind benchmark requires <100 ms end-to-end. With 4 GB RAM per Gazebo instance and PX4 SITL limited to <10 vehicles, per-topic bandwidth is modest; the 20 Hz aggregate keeps the fleet telemetry bus well under the latency budget. If a topic stalls (no msg > 500 ms), the aggregator marks that field stale and sets `source` accordingly rather than dropping the whole message.

---

## 6. QoS Reliability / Durability Settings

Profiles follow `docs/integration-gap-report.md` §3.4 and AAS `state_sharing_node.cpp` / `px4_interface.cpp` (subscribers: `KEEP_LAST` depth 10, `BEST_EFFORT`).

| Profile | Reliability | Durability | History | Depth | Use |
|---|---|---|---|---|---|
| `QOS_SENSOR` | BEST_EFFORT | VOLATILE | KEEP_LAST | 10 | High-rate sensor/pose where drop is OK |
| `QOS_STATUS` | RELIABLE | VOLATILE | KEEP_LAST | 10 | Mode/armed changes that must not be lost |
| `QOS_MODE` | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST | 10 | Late-joiners need last known mode |
| `QOS_AGGREGATE` | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST | 10 | Fleet aggregate; apex late-join gets latest state |

| Topic | QoS profile | Rationale |
|---|---|---|
| `vehicle_odometry` | QOS_SENSOR | 100 Hz pose/velocity, drop OK, latest wins |
| `vehicle_local_position` | QOS_SENSOR | 100 Hz, drop OK |
| `vehicle_global_position` | QOS_SENSOR | 100 Hz GPS/lat-lon, drop OK |
| `vehicle_status` | QOS_STATUS | mode/armed must arrive (RELIABLE), no late-joiner state (VOLATILE) |
| `battery_status` | QOS_SENSOR | 10 Hz, drop OK |
| `vehicle_gps_position` | QOS_SENSOR | 10 Hz, drop OK |
| `yolo/detections` | QOS_SENSOR (depth 5) | 15 Hz vision, drop OK, keep only latest few |
| `vehicle_telemetry` (per-vehicle) | QOS_AGGREGATE | apex must not miss aggregate updates; late-joiner gets latest |
| `fleet/telemetry/aggregate` | QOS_AGGREGATE | single subscription for all vehicles; TRANSIENT_LOCAL for late-joining apex |

RMW selection (per integration-gap-report §3.4): `rmw_fastrtps_cpp` (default), `rmw_cyclonedds_cpp` (embedded), `rmw_zenoh_cpp` (fleet/WAN). `px4_msgs` must match the PX4 firmware version — the #1 cause of silent serialization failures.

---

## 7. Multi-Vehicle Telemetry Aggregation & Demultiplexing

### 7.1 Aggregation (AAS sim side)

One aggregator node (or one per sim container) subscribes to every `/Drone{id}/fmu/out/*` source topic at its native rate and maintains a latest-snapshot per vehicle keyed by `drone_id`. On each 20 Hz tick it publishes:

1. `/Drone{id}/telemetry/vehicle_telemetry` — per-vehicle full `VehicleTelemetry`, and/or
2. `/fleet/telemetry/aggregate` — one `VehicleTelemetry` per vehicle per cycle, each carrying its own `drone_id`.

Logic pseudocode:

```
on odometry/position/gps/status/battery msg for drone d:
    snapshot[d].merge(msg.fields)          # latest-wins per field
    snapshot[d].timestamp_us = msg.timestamp_us
    snapshot[d].source = msg.originating_node

every 50 ms (20 Hz):
    for d in active_drones:
        msg = VehicleTelemetry()
        msg.header.stamp = now()
        msg.drone_id = d
        msg.<fields> = snapshot[d].<fields>
        msg.source = snapshot[d].source
        publish("/Drone{d}/telemetry/vehicle_telemetry", msg)
        publish("/fleet/telemetry/aggregate", msg)   # same msg, demux key = drone_id
    drop drones with no update > 500 ms (mark stale, keep last known)
```

### 7.2 Demultiplexing (apex side)

**Option A — single subscription (recommended):** apex subscribes once to `/fleet/telemetry/aggregate`. On each message it routes to a per-drone state buffer keyed by `msg.drone_id`, converts `VehicleTelemetry` → `StateVector` (§8), and feeds the planner/optimizer. A fleet manager tracks active drone IDs and liveness (TTL 500 ms).

**Option B — per-vehicle subscriptions:** apex subscribes to each `/Drone{id}/telemetry/vehicle_telemetry` directly (one subscription per vehicle). Equivalent semantics; more subscriptions, no demux needed.

**Concurrency:** aggregator and apex adapters use reentrant callback groups (AAS pattern in `px4_interface.cpp`, `state_sharing_node.cpp`) so high-rate odometry callbacks don't block slower status/battery callbacks.

**Time synchronization:** `header.stamp` is ROS2 time (sim time when `use_sim_time:=true`). apex aligns telemetry snapshots to the planner clock by nearest timestamp within a 50 ms sync window before constructing `StateVector`, then passes `StateVector` into `PlanningProblem.start`.

---

## 8. Field Mapping: AAS px4_msgs → Contract → apex StateVector

| Contract field | Source AAS topic / field | apex `StateVector` mapping | Notes |
|---|---|---|---|
| x, y, z | `VehicleOdometry.position` | `StateVector.pose.x/y/z` | NED frame by default |
| roll, pitch, yaw | `VehicleOdometry.q` → Euler | `StateVector.pose.roll/pitch/yaw` | quaternion converted at boundary |
| vx, vy, vz | `VehicleOdometry.velocity` | `StateVector.velocity.vx/vy/vz` | |
| battery_voltage/current/remaining | `BatteryStatus.voltage/current/remaining` | `StateVector.metadata["battery"]` | governance/safety use |
| lat, lon, alt_amsl | `VehicleGlobalPosition.lat/lon/alt` | `StateVector.metadata["gps"]` | geofence/home use |
| nav_state | `VehicleStatus.nav_state` | `StateVector.metadata["mode"]` | OFFBOARD=14 etc. |
| arming_state | `VehicleStatus.arming_state` | `StateVector.metadata["armed"]` | 1=disarmed, 2=armed |
| vehicle_type | `VehicleStatus.vehicle_type` | `StateVector.metadata["vehicle_type"]` | maps to `VehicleType` enum |
| timestamp_us / header.stamp | source msg timestamp | `StateVector.timestamp` | sim time aligned |
| detections | `vision_msgs/Detection2DArray` | `StateVector.metadata["detections"]` | perception/targeting |

`ControlInput` (downstream, out of scope for this contract) maps from apex back to AAS via `/fmu/in/trajectory_setpoint` + `/fmu/in/offboard_control_mode` (ROS2) or `SET_ATTITUDE_TARGET` (MAVLink).

---

## 9. MAVLink Parity Mapping (MAVLinkBridge path)

For parity with the ROS2 contract when using MAVLinkBridge:

| Contract field | MAVLink message |
|---|---|
| pose (x,y,z) | `GLOBAL_POSITION_INT` / `POSITION_TARGET_LOCAL_NED` |
| pose (roll,pitch,yaw) | `ATTITUDE` |
| velocity (vx,vy,vz) | `GLOBAL_POSITION_INT` (vx,vy,vz) |
| battery | `BATTERY_STATUS` |
| GPS (lat/lon/alt) | `GPS_RAW_INT` |
| mode | `HEARTBEAT` (custom_mode) / `COMMAND_ACK` |
| armed | `HEARTBEAT` (base_mode safety/armed bits) |
| YOLO detections | vision/detection payload (dialect-dependent) |

Stream rates: `ATTITUDE`/`GLOBAL_POSITION_INT` 100 Hz via `STREAM_DATA_STREAM`; `BATTERY_STATUS`/`GPS_RAW_INT` 10 Hz; `HEARTBEAT` 1 Hz. MAV_SYS_ID = DRONE_ID provides vehicle demux on the MAVLink channel.

---

## 10. Compatibility & Versioning

- Schema version: `telemetry-contract v1` (header-free versioning via topic name; add a `uint8 schema_version` field to `VehicleTelemetry` only when a breaking change is needed).
- `px4_msgs` must match the PX4 firmware version running in AAS SITL (version-matching note in integration-gap-report §3.4).
- Backward-compatible changes: append fields only at message end; never reorder or remove fields.
- `drone_id` is mandatory on every contract message — topics alone are not relied upon for demux, enabling the single-subscription aggregate pattern.

---

## 11. Open Items

- Enable `battery_status` and `vehicle_gps_position` in AAS `dds_topics.yaml` (currently commented out).
- Add `schema_version` field if a breaking revision is required.
- Confirm YOLO topic remap `/detections` → `/yolo/detections` in AAS launch files.
- Implement the aggregator node and apex `ROS2Adapter` demux per §7 (per integration-gap-report Phase 3).
- Load-balance / RMW selection for fleets >10 vehicles given 4 GB RAM per Gazebo instance and <100 ms latency budget.
