# Perception Pipeline Spec — YOLO Detections to WTA Target Inputs

**Status:** Spec (implementation pending)  
**Kanban card:** `t_d598d729`  
**Repositories:**  
- Sim/runtime surface: `github.com/JacopoPan/aerial-autonomy-stack` (MIT) — AAS  
- Optimization/governance layer: `github.com/AAH20/apex-autopilot-optimization` (AGPL-3.0) — apex  
**Integration:** MAVLinkBridge + ROS2 topics; port namespacing `5760+i*10` (master), `5501+i*10` (SITL); `DRONE_ID=ROS_DOMAIN_ID=MAV_SYS_ID`  
**Location of implementation code:** `src/apex_autopilot_optimization/perception/` (new package)  
**License:** AGPL-3.0 (apex) interoperating with MIT (AAS)

---

## 1. Purpose and scope

This spec defines how YOLO detections produced by AAS flow into apex-autopilot-optimization as targeting inputs for the WTA (winner-take-all / weighted task-assignment) solver in `swarm/task_allocation.py`. It covers:

1. YOLO detection ingestion from AAS ROS2 topics (`/yolo/detections` via `ros_gz_bridge` from the Gazebo camera)
2. Detection filtering (minimum-detections threshold + EWMA smoothing against jitter)
3. Vendor-agnostic class-to-target mapping (COCO object classes → WTA target types)
4. Confidence thresholds
5. End-to-end latency budget under 100 ms (camera → inference → control)
6. Multi-camera fusion for swarm situational awareness
7. Detection → WTA target input transformation (position, class, confidence, timestamp)
8. TDD test plan

Out of scope: sensor-level camera calibration (handled by AAS `yolo_node.py` intrinsics), WTA solver internals (exists), trajectory planning/minimum snap (exists), PX4/ArduPilot flight-stack tuning.

---

## 2. System context and integration points

### 2.1 AAS side (existing, verified against `aas-repo/.../yolo_py/yolo_node.py`)

AAS runs one `YoloInferenceNode` per camera (`camera_id` CLI arg), namespaced per drone by `DRONE_ID`. The node:

- Subscribes to / acquires camera frames. In simulation the Gazebo camera stream is bridged into ROS2 via `ros_gz_bridge`; the bridged camera topic is the input to perception ingestion.
- Runs YOLO inference (ONNX Runtime, CUDA on x86_64 sim; TensorRT on Jetson Orin HITL; models `yolo26n_320` / `yolo26n_640`, conceptually interchangeable with YOLOv8s/n).
- Publishes detections as `vision_msgs.msg.Detection2DArray` on topic `detections` (node `yolo_inference_node_<camera_id>`). Each `Detection2D` carries:
  - `bbox.center.(x, y)` and `size.(x, y)` in pixel coords of the source frame
  - `results[].hypothesis.class_id` = COCO class name (string), `results[].hypothesis.score` = confidence
  - `results[].pose.pose.position.(x, y, z)` = azimuth deg, elevation deg, angular_width deg (pinhole bearing model computed by AAS from frame intrinsics; `frame_id = camera_frame_<camera_id>`)
  - `header.stamp` = ROS2 time at detection publication; `header.frame_id` = camera optical frame

CONF_THRESH in AAS is currently hardcoded at `0.5`; the apex ingestion layer applies its own thresholds (Section 6) and must not depend on AAS's hardcoded value.

### 2.2 apex side (existing)

- `swarm/task_allocation.py`: greedy WTA. `Task(id, position: Pose3D, priority, ...)`; `Agent(id, position, vehicle_type, ...)`; `TaskAllocator.allocate(agents, tasks) → [(agent_id, task_id)]`. Detections become `Task`s: `position` = estimated target position ENU, `priority` = f(class, confidence).
- `core/types.py`: `Pose3D`, `StateVector`, `VehicleType`, `PlanningProblem`, `PlanningResult`, etc. `StateVector.timestamp` is `float` (epoch seconds).
- `integration/mavlink.py`: `MAVLinkBridge` publishes/sends vehicle state and control; simulation mode works without pymavlink.
- Bottlenecks from context: WTA exact methods intractable beyond 20×20; Gazebo SITL < 10 vehicles; 4 GB RAM per Gazebo instance; end-to-end latency target < 100 ms (Hivemind-class benchmark); vendor-agnostic, no V-BAT lock-in.

### 2.3 ROS2 topic naming (swarm-scale)

Per-drone ROS2 domain = `DRONE_ID` (= `ROS_DOMAIN_ID` = `MAV_SYS_ID`). All perception topics are namespaced so `N` drones never collide:

| Topic | Direction | Payload | Notes |
|---|---|---|---|
| `/drone{id}/camera/image_raw` | sensor → perception | `sensor_msgs/Image` | Gazebo camera via `ros_gz_bridge`, one per drone |
| `/drone{id}/yolo/detections` | YOLO node → perception | `vision_msgs/Detection2DArray` | AAS `yolo_node.py` output (`detections` in node ns) |
| `/drone{id}/perception/targets` | perception → WTA / swarm | `PerceptionTargetArray` (new apex msg/struct) | Fused, filtered target inputs for WTA |
| `/drone{id}/perception/tracks` | perception → perception | `PerceptionTrackArray` | Internal EWMA-smoothed tracks, camera-provenanced |
| `/swarm/perception/fused_targets` | swarm fusion → all | `PerceptionTargetArray` | Cross-drone deduplicated targets for swarm SA |

QoS: `RELIABLE` + `KEEP_LAST(10)` for detection/target topics; best-effort acceptable for raw image. `Durability: VOLATILE` (detections are ephemeral; late-joining WTA gets the next frame, not history).

---

## 3. YOLO ingestion architecture

```
Gazebo camera (AAS SITL)
        │ ros_gz_bridge (image/raw)
        ▼
/drone{i}/camera/image_raw ─────► [ PerceptionNode: ingest_camera() ]
                                      │
                                      ▼
                            (optional re-inference on apex side:
                             YOLOv8s on Hailo-8L / TensorRT)
                                      │
                                      ▼
/drone{i}/yolo/detections ───► Detection2DArray → IngestionAdapter
                                      │
                                      ▼
                         RawDetection list (per frame, per camera)
                                      │
                                      ▼
                    Filtering (min-detections, conf, EWMA, staleness)
                                      │
                                      ▼
                         Track list (EWMA-smoothed, per camera)
                                      │
                                      ▼
                    Class → WTA target mapping + ENU transform
                                      │
                                      ▼
                    PerceptionTargetArray on /drone{i}/perception/targets
                                      │
                                      ▼
                         WTA solver (swarm/task_allocation.py)
```

### Ingestion adapter contract (`PerceptionIngestion`)

Input: one `Detection2DArray` message + source `camera_id` + source `drone_id`.  
Output: list of `RawDetection`:

```
RawDetection:
  camera_id: int
  drone_id: int
  class_name: str        # COCO class string from AAS
  confidence: float      # [0,1]
  bbox_px: (cx, cy, w, h)# pixels, source frame
  bearing_deg: float     # from Detection2D results[].pose.pose.position.x
  elevation_deg: float   # ... .y
  angular_width_deg: float # ... .z (range proxy)
  stamp: float           # epoch seconds from header.stamp
  frame_id: str          # camera_frame_<camera_id>
```

The adapter validates the message (non-null header, stamp not in the future by more than `CLOCK_TOLERANCE_S = 50ms`, at least one hypothesis per detection), converts ROS time → epoch seconds, and drops malformed detections with a `structlog` warning. No inference happens in the adapter by default; re-inference on apex compute is an optional override (`REINFERENCE_ENABLED=false` default) used only when the AAS node is unavailable (recorded-scenario replay).

### Why `/yolo/detections` and not raw images in apex

Shipping raw images across the swarm DDS domain would blow the latency budget and RAM. AAS already performs inference on the drone/Orin; apex consumes the compact `Detection2DArray` (≈1–2 KB per frame at typical object counts) and adds filtering, fusion, and targeting semantics. This keeps apex vendor-agnostic: any AAS-compatible YOLO publisher (ONNX, TensorRT, Hailo) producing `Detection2DArray` is a drop-in.

---

## 4. Detection filtering rules

Filtering runs per `(drone_id, camera_id)` track chain, in order:

### 4.1 Confidence gating (per-class)

| Class tier | Example COCO classes | Min confidence (default) |
|---|---|---|
| WTA-critical (small/ambiguous) | person, bird, traffic light | 0.60 |
| Standard targets | car, truck, bus, motorcycle, bicycle, boat, airplane | 0.45 |
| Detection floor (never below) | any | 0.25 |

Rationale: Ultralytics Hailo guidance shows `conf=0.20` on device ≈ `conf=0.25` in PyTorch (detection-count parity); apex never accepts below 0.25 so the WTA never feeds on noise. Tiers are configurable in `perception.yaml` (Section 11).

### 4.2 Minimum-detections threshold (track promotion)

A detection is **tentative** on first sighting. It is promoted to a confirmed track only when:

- `≥ MIN_DETECTIONS = 3` detections of the same class are associated to the same track within `PROMOTION_WINDOW_S = 500 ms` (20 frames at 25 fps), **and**
- the EWMA-smoothed position change between first and last detection is within `MAX_JITTER_M = 2.0 m` (aligns with the 2 cm sensor-alignment accuracy class; jitter beyond this indicates noise or a different object).

Tentative detections are never published to WTA. A track that drops below the threshold reverts to tentative; `STALE_TTL_S = 200 ms` without any associated detection drops the track entirely.

### 4.3 EWMA smoothing (anti-jitter)

Per-track state `(x̂, ŷ, ẑ, bearinĝ, elev̂)` updated on each associated detection:

```
x̂_t = α · z_t + (1 − α) · x̂_{t−1}      α = EWMA_ALPHA = 0.35 (default)
```

Applied independently to: pixel center `(cx, cy)`, bearing, elevation, angular width. Position in ENU is recomputed from the smoothed bearing + drone EKF state at transform time (Section 8). `α` is tunable: lower = smoother but more lag; the latency budget allocates 4 ms for filtering, so EWMA is O(1) per track with no history buffer beyond the previous state.

### 4.4 Association gate

A new detection associates to an existing track if all hold:

- `|Δbearing| ≤ BEARING_GATE_DEG = 5.0°`
- `|Δelevation| ≤ ELEVATION_GATE_DEG = 5.0°`
- `|Δangular_width| ≤ 30%` of tracked width
- same class name (class changes reset the track — e.g. "bird" → "airplane" is a new object)

Otherwise a new track is spawned (tentative). This prevents jitter from splitting one target into multiple WTA inputs.

---

## 5. Class-to-target mapping (vendor-agnostic)

AAS uses COCO class names (`coco.json`). WTA target types are vendor-agnostic (no V-BAT or Shield AI nomenclature). Mapping table:

| COCO class (AAS) | WTA target type | Size class | Default priority | WTA treatment |
|---|---|---|---|---|
| person | personnel | small | 0.7 | high-value, small cross-section |
| car | ground_vehicle | medium | 0.6 | |
| truck | ground_vehicle | large | 0.7 | |
| bus | ground_vehicle | large | 0.7 | |
| motorcycle | light_ground_vehicle | small | 0.5 | |
| bicycle | light_ground_vehicle | small | 0.4 | |
| boat | maritime_vessel | medium | 0.6 | |
| airplane | fixed_wing_aircraft | large | 0.8 | air-priority |
| bird | aerial_clutter | small | 0.1 | suppressed unless `INCLUDE_CLUTTER=true` |
| traffic light | infrastructure | small | 0.2 | |
| stop sign | infrastructure | small | 0.2 | |
| (any other COCO class) | unclassified_target | medium | 0.3 | |
| low confidence (< tier min) | — | — | — | dropped |

`TargetType` is an enum in apex `perception/targets.py`. Priority feeds `Task.priority` in the greedy WTA (nearest available agent within `communication_range`, per `task_allocation.py`). Class mapping is data-driven (YAML, Section 11) so new sensor classes (e.g., thermal classes) can be added without code changes.

---

## 6. Confidence thresholds

- **Ingestion floor:** `CONF_MIN = 0.25` (detection floor, never bypassed).
- **WTA publication floor:** per-tier table in Section 4.1 (0.45 standard, 0.60 WTA-critical).
- **NMS IoU:** `0.70` (matches Ultralytics/HailoRT default for YOLOv8; AAS YOLO26 is NMS-free, so apex applies class-agnostic NMS at 0.70 IoU if a re-inference path emits overlapping boxes).
- **Hailo-8L note:** on-device `conf=0.20` matches PyTorch `0.25` detection count; if apex re-infers on Hailo, set HailoRT conf to 0.20 and apply apex `CONF_MIN = 0.25` on outputs.
- Hysteresis: a track near threshold uses its EWMA-smoothed mean confidence; publication requires `smoothed_conf ≥ WTA_PUB_MIN` to avoid chattering in/out of the WTA target list.

---

## 7. End-to-end latency budget (< 100 ms)

Budget measured from **camera shutter (Gazebo frame timestamp)** to **control command dispatched via MAVLinkBridge**. Target: p95 < 100 ms, hard ceiling 100 ms. Grounding: Shield AI Hivemind EdgeOS sustains sub-millisecond local messaging at millions of messages/sec class latency; AAS/Hailo field results show YOLO-class models at 25+ fps on Hailo-8L (28.59 fps PCIe Gen2, 55.73 fps PCIe Gen2/Gen3 on RPi CM5; 44.7 fps on RPi 5 @640, <100 ms end-to-end on Pi 5 + Hailo-8), and UAV multi-sensor pipelines achieve ≈2 cm RMS horizontal alignment accuracy (FIG 2022 Sobol et al.) — the accuracy class this spec's jitter gate assumes.

| # | Stage | Budget (ms) | Notes |
|---|---|---|---|
| 1 | Camera capture + Gazebo → ros_gz_bridge transport | 8 | 25 fps frame period = 40 ms; capture-to-topic ≤ 1/5 of period |
| 2 | YOLO inference (YOLOv8s/n-class, Hailo-8L or Orin TensorRT) | 40 | ≈25 fps measured class hardware; dominant term |
| 3 | ROS2 DDS transport + serialization (intra-drone, local domain) | 6 | Reliable, keep-last, localhost |
| 4 | Ingestion adapter (parse, validate, clock sync) | 2 | O(detections), structlog sampled |
| 5 | Filtering: conf gate + min-detections + EWMA + staleness | 4 | O(tracks), no history buffers |
| 6 | Multi-camera association + fusion | 10 | Per-drone + cross-drone dedup (Section 9) |
| 7 | Detection → ENU target transform (bearing + drone EKF + extrinsics) | 4 | Pinhole back-projection, 2 cm alignment class |
| 8 | WTA target list assembly + publish `/perception/targets` | 2 | |
| 9 | WTA greedy solve (≤ 20×20 tractable) | 12 | `task_allocation.py` complexity class NP-complete beyond 20×20; keep N small |
| 10 | Control dispatch via MAVLinkBridge (offboard/guided setpoint) | 8 | Includes MAVLink framing |
| | **Total** | **100** | **p95 target 92 ms; 8 ms margin** |

Measurement: `tests/unit/test_perception_latency.py` instruments each stage with `time.perf_counter()` around the real functions and asserts per-stage and end-to-end p95 over 500 synthetic frames. Any stage exceeding its budget fails the test (no aggregated averaging that hides a single slow stage).

If the budget is exceeded, the first cuts are: reduce inference input to 320 (AAS already selects `yolo26n_320` for ≤320 px streams), skip cross-drone fusion for non-WTA-critical classes, or lower `EWMA_ALPHA` latency is unaffected (EWMA is O(1)) — accuracy trades, not latency trades.

---

## 8. Detection → WTA target transformation

Each confirmed track becomes one `PerceptionTarget`:

```
PerceptionTarget:
  target_id: str               # "drone{camera_id}:track{track_id}"
  source_drone_id: int
  source_camera_ids: list[int]
  pose: Pose3D                 # ENU position (m) + yaw from bearing
  target_type: TargetType      # Section 5
  confidence: float            # smoothed [0,1]
  stamp: float                 # epoch seconds (detection time, not processing time)
  bearing_deg: float
  elevation_deg: float
  angular_width_deg: float     # range proxy
  position_cov_m: list[list[float]]  # 3x3, from extrinsics calibration (2 cm class)
```

### Transform math

AAS `yolo_node.py` already computes azimuth/elevation/angular_width from pixel center and pinhole intrinsics (`fx, fy, cx, cy`; simulated: pinhole assumption; real: IMX219 calibration YAML). The apex transform:

1. Convert `(bearing, elevation)` to a unit bearing vector in the camera frame.
2. Rotate by camera extrinsics (mount roll/pitch/yaw offset, measured at calibration; alignment accuracy class ≈ 2 cm RMS horizontal per FIG 2022).
3. Combine with drone ENU state from `MAVLinkBridge.get_state()` (`StateVector.pose`, timestamp-synced within `MAX_STATE_AGE_S = 100 ms`).
4. Estimate range from `angular_width_deg` and target `size_class` (Section 5 typical size table), or from KISS-ICP LiDAR depth when available (optional fusion input).
5. `pose` = ENU position; timestamp = detection `header.stamp` (end-to-end latency = `now − stamp`, monitored by test 10).

Temporal alignment: detections are associated to the closest drone state by timestamp; if `Δt > MAX_STATE_AGE_S`, the target is dropped (stale state → unsafe targeting).

---

## 9. Multi-camera fusion (swarm situational awareness)

### 9.1 Per-drone fusion (multiple cameras on one vehicle)

- Each camera maintains independent track chains (Section 4).
- Tracks from overlapping FOVs on the same drone are merged when bearing/elevation agree within `BEARING_GATE_DEG` and timestamps within `FUSION_WINDOW_S = 50 ms`; the merged track keeps all `source_camera_ids` and averages position weighted by confidence.
- Non-overlapping cameras: union of tracks, tagged with camera provenance (no false merge).

### 9.2 Swarm fusion (across drones)

Each drone publishes `/drone{i}/perception/targets`. A swarm fusion node (apex, on ground station or elected leader drone, `ROS_DOMAIN_ID` shared) subscribes to all drone target topics and:

1. Deduplicates targets observed by multiple drones: same `target_type`, positions within `DEDUP_RADIUS_M = 5.0 m`, timestamps within `DEDUP_WINDOW_S = 300 ms` → one fused target (highest confidence wins; position covariance-intersected).
2. Publishes `/swarm/perception/fused_targets` — the single target list consumed by the WTA solver and shared with all agents for situational awareness.
3. Emits a `fusion_lag_ms` metric (max `now − stamp` across inputs) for the latency test.

Fault tolerance: if one drone's perception topic stalls (> `STALE_TTL_S`), its targets expire from the fused list; WTA continues with remaining targets (degraded, not failed).

---

## 10. Configuration (`perception.yaml`)

```yaml
perception:
  qos: { reliability: reliable, history: keep_last, depth: 10 }
  conf:
    min: 0.25
    tiers:
      wta_critical: 0.60   # person, bird, traffic_light
      standard: 0.45        # car, truck, bus, motorcycle, bicycle, boat, airplane
  nms_iou: 0.70
  filtering:
    min_detections: 3
    promotion_window_s: 0.5
    max_jitter_m: 2.0
    stale_ttl_s: 0.2
    ewma_alpha: 0.35
    bearing_gate_deg: 5.0
    elevation_gate_deg: 5.0
    angular_width_gate_pct: 0.30
  fusion:
    dedup_radius_m: 5.0
    dedup_window_s: 0.3
    fusion_window_s: 0.05
  transform:
    max_state_age_s: 0.1
    alignment_accuracy_m: 0.02   # 2 cm class (FIG 2022)
  latency_budget_ms:
    camera_to_topic: 8
    inference: 40
    transport: 6
    ingestion: 2
    filtering: 4
    fusion: 10
    transform: 4
    publish: 2
    wta_solve: 12
    control_dispatch: 8
    total: 100
```

---

## 11. TDD test plan

All tests live under `tests/unit/` (and `tests/integration/` for ROS2), following repo conventions: pytest, classes per module, `pytest.approx` for floats, `from __future__ import annotations`, numpy, ruff/mypy clean. Cycle per module: **RED** (failing test) → **GREEN** (implementation) → **REFACTOR** (ruff/mypy). Budgets are asserted per-stage, not averaged.

### 11.1 Unit tests

| Test file | What it verifies (RED → GREEN) |
|---|---|
| `test_perception_ingestion.py` | `Detection2DArray` → `RawDetection` list; timestamp conversion; empty array → `[]`; missing hypothesis → drop + log; future-stamp (>50 ms) → drop; pixel→(cx,cy,w,h) conversion; `frame_id` propagation |
| `test_perception_filtering.py` | Confidence tiers drop below-threshold detections; `min_detections=3` promotion within 500 ms window; 2-of-3 detections stays tentative (never reaches WTA); EWMA output matches hand-computed `α·z + (1−α)·x̂` for a known sequence; staleness drops track after 200 ms; association gate merges close detections, splits far ones; class change resets track |
| `test_perception_class_mapping.py` | Full COCO→`TargetType` table (Section 5) incl. `unclassified_target` fallback; priority values; `INCLUDE_CLUTTER=false` suppresses `aerial_clutter`; YAML-driven mapping loads without code changes; unknown class string never crashes |
| `test_perception_transform.py` | Known bearing/elevation + drone ENU pose → expected ENU target position (hand-computed); range from angular width + size class; stale drone state (>100 ms) drops target; output `Pose3D` and `confidence`/`stamp` types correct; 2 cm alignment class reflected in covariance diagonal |
| `test_perception_fusion.py` | Per-drone multi-camera merge within gate; cross-drone dedup within 5 m / 300 ms; fused target keeps highest confidence; stalled drone topic expires targets; `fusion_lag_ms` computed correctly |
| `test_perception_latency.py` | Instrument all 10 budget stages over 500 synthetic frames; assert each stage p95 ≤ budget; assert end-to-end p95 ≤ 92 ms (margin to 100 ms ceiling); fail on any single-stage overrun |

### 11.2 Integration tests

| Test file | What it verifies |
|---|---|
| `test_perception_ros2.py` | If `rclpy` available: synthetic publisher on `/drone{id}/yolo/detections` → `PerceptionNode` → target published on `/drone{id}/perception/targets` with correct fields; end-to-end ROS2 latency < 100 ms; namespaced topics do not collide across two drone domains. Otherwise: mock-rclpy equivalent asserting the same contracts. |

### 11.3 Property-based tests (hypothesis, in dev deps)

- EWMA output always lies between consecutive inputs; smoothing reduces jitter variance vs raw sequence for random walks.
- Confidence threshold function is monotone: lowering threshold never drops an accepted detection.
- Class mapping is total: every non-empty string maps to exactly one `TargetType`.

### 11.4 CI gates

- `pytest tests/unit/test_perception*.py tests/integration/test_perception_ros2.py` must be GREEN (repo standard: 560/560 tests GREEN today; this spec adds ~40–50).
- `ruff check` and `mypy` strict on new `src/apex_autopilot_optimization/perception/` package.
- Latency test runs in CI with mocked hardware (synthetic frames, no GPU required); Hailo/Orin numbers validated separately on device.

---

## 12. Implementation package layout (apex)

New package `src/apex_autopilot_optimization/perception/` (AGPL-3.0, same header style as `integration/mavlink.py`):

```
perception/
  __init__.py
  types.py          # RawDetection, PerceptionTarget, TargetType, PerceptionTargetArray
  config.py         # PerceptionConfig (pydantic), loads perception.yaml
  ingestion.py      # PerceptionIngestion (adapter contract, Section 3)
  filtering.py      # EWMA track chain: min-detections, conf gates, staleness (Section 4)
  mapping.py        # COCO → TargetType table (Section 5)
  transform.py      # bearing/elevation → ENU Pose3D (Section 8)
  fusion.py         # per-drone + cross-drone fusion (Section 9)
  pipeline_node.py  # ROS2 node wiring subscriptions/publications (Section 2.3)
```

`PipelineNode` subscribes to `/drone{DRONE_ID}/yolo/detections`, runs ingestion → filtering → transform → (fusion if swarm mode), publishes `PerceptionTargetArray` on `/drone{DRONE_ID}/perception/targets`. WTA solver consumes that topic (or the swarm fused topic) and converts targets to `Task` objects for `TaskAllocator.allocate`.

---

## 13. Assumptions and open decisions

1. AAS `yolo_node.py` topic `detections` is remapped to `/drone{id}/yolo/detections` at launch via ROS2 remapping rules (`-r detections:=...` or node namespace). Confirm at AAS launch integration.
2. Camera extrinsics (mount offset) and drone-to-camera transform come from AAS calibration; apex stores them in `perception.yaml` per airframe. 2 cm alignment class assumes calibrated extrinsics (FIG 2022 best practice).
3. WTA scale limit (≤ 20×20 tractable) means fused targets must be pruned to WTA-critical classes before solving; non-critical targets populate situational awareness only.
4. Re-inference on apex compute is disabled by default; enable only for replay/recorded scenarios.

---

## 14. References

1. Shield AI, "Hivemind EdgeOS: A Game-Changer for Autonomous Robotics" — sub-millisecond local shared-memory messaging, millions of messages/sec; basis for the < 100 ms end-to-end Hivemind-class benchmark: https://shield.ai/hivemind-edgeos-a-game-changer-for-autonomous-robotics/
2. Hailo Community, "Yolov8s performance results" — YOLOv8s on Hailo-8L: 28.59 fps (PCIe Gen2), 55.73 fps (PCIe Gen3) on RPi CM5 8 GB; YOLOv8s ≈490 fps on Hailo-8: https://community.hailo.ai/t/yolov8s-performance-results/18146
3. Hailo Community, "Open-source AI security camera on Pi 5 + Hailo-8" — 40+ fps YOLOv8s on Pi 5 + Hailo-8L, <100 ms end-to-end, ~40 ms inference: https://community.hailo.ai/t/open-source-ai-security-camera-on-pi-5-hailo-8-two-yolo-models-on-one-device-with-anpr/19385
4. Ultralytics docs, "Hailo Export for Ultralytics YOLO Models" — `conf=0.20` on device ≈ `conf=0.25` PyTorch detection count; YOLOv8/v11 HailoRT NMS defaults conf=0.25, iou=0.7: https://docs.ultralytics.com/integrations/hailo
5. Sobol et al., FIG 2022, "UAV Multi-Sensor Payloads for High Precision Aerial Surveys" — 2 cm RMS horizontal / 4 cm vertical absolute accuracy without GCPs; boresight/lever-arm calibration practice: https://www.fig.net/resources/proceedings/fig_proceedings/fig2022/papers/ts02c/TS02C_mostafa_sobol_et_al_11485.pdf
6. AAS `yolo_node.py` (`aas-repo/aircraft/aircraft_ws/src/yolo_py/yolo_py/yolo_node.py`) — `Detection2DArray` on `detections`, bearing/elevation/angular_width in `ObjectHypothesisWithPose.pose.position` (degrees), COCO classes, CONF_THRESH=0.5, per-camera `camera_id`, `DRONE_ID` namespacing
7. Context constraints — port namespacing `5760+i*10` master / `5501+i*10` SITL, `DRONE_ID=ROS_DOMAIN_ID=MAV_SYS_ID`, WTA intractable beyond 20×20, 4 GB RAM per Gazebo instance (<10 vehicles), AGPL-3.0 apex + MIT AAS, vendor-agnostic (no V-BAT lock-in).
