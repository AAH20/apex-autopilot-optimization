# Data Pipeline Gap Report — apex-autopilot-optimization

**Date:** 2026-10-04
**Status:** Gap Analysis
**Scope:** Data ingestion, processing, storage, versioning

---

## Executive Summary

The project implements 20 algorithm modules (planning, optimization, estimation, control, safety, swarm) with 365 passing tests but has **zero data pipeline infrastructure**. Every algorithm operates on in-memory dataclasses (`StateVector`, `Trajectory`, `Pose3D`) with no way to ingest real flight logs, persist results, or reproduce experiments. This is the single largest architectural gap: the framework cannot connect to real-world sensor data, cannot validate algorithms against recorded flights, and cannot track performance across data versions.

---

## 1. Current State Audit

| Layer | Present? | What exists | What's missing |
|-------|----------|-------------|----------------|
| **Core Types** | ✅ | `Pose3D`, `StateVector`, `Trajectory`, `ControlInput`, `Waypoint`, `PlanningProblem`, `PlanningResult` | No serialization, no schema registry, no conversion from sensor formats |
| **Observability** | ✅ | `StructuredLogger`, `MetricCollector`, `HealthCheck` | Logs are in-memory dicts; no persistence, no time-series store |
| **Benchmark** | ✅ | `BenchmarkRunner`, `EvolutionTracker` | Results are in-memory; no historical tracking, no dataset binding |
| **Evaluation** | ✅ | `EvaluationRunner`, `MetricAggregator` | No dataset input, no reproducibility |
| **Data Ingestion** | ❌ | — | No MCAP/ULog/MAVLink/ROS bag readers |
| **Data Processing** | ❌ | — | No sync, cleaning, filtering, transformation |
| **Data Storage** | ❌ | — | No Parquet/Delta/Zarr/DB persistence |
| **Data Versioning** | ❌ | — | No dataset versioning, no provenance, no manifests |
| **Flight Log Import** | ❌ | — | No `.ulg`, `.bin`, `.mcap`, `.bag` support |
| **Sensor Data Pipeline** | ❌ | — | No IMU/GPS/barometer/compass ingestion |

---

## 2. What Data Pipeline Is Needed

### 2.1 Required Pipeline Stages

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   INGEST    │───▶│   PROCESS    │───▶│   STORE      │───▶│   VERSION    │───▶│   SERVE      │
│             │    │              │    │              │    │              │    │              │
│ • ULog      │    │ • Sync       │    │ • Parquet    │    │ • Delta Lake │    │ • Train      │
│ • MCAP      │    │ • Clean      │    │ • Delta Lake │    │ • DVC        │    │ • Evaluate   │
│ • MAVLink   │    │ • Transform  │    │ • Zarr       │    │ • Manifests  │    │ • Benchmark  │
│ • ROS bags  │    │ • Validate   │    │ • DuckDB     │    │ • Provenance │    │ • Visualize  │
│ • CSV/JSON  │    │ • Enrich     │    │ • Object Sto │    │ • Lineage    │    │ • Export     │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

### 2.2 Data Sources to Support

| Format | Source | Priority | Notes |
|--------|--------|----------|-------|
| **ULog** (`.ulg`) | PX4 flight logs | P0 | Native PX4 format; pyulog parser available |
| **MAVLink** (`.bin`, `.tlog`) | ArduPilot, PX4 | P0 | pymavlink/dronekit can decode |
| **MCAP** (`.mcap`) | ROS 2, Foxglove | P1 | Modern standard; mcap Python lib |
| **ROS 2 bags** (`.db3`) | ROS 2 native | P1 | Convertible to MCAP |
| **CSV/JSON** | Generic telemetry | P2 | Simple tabular import |
| **Parquet** | Pre-processed | P2 | For interop with existing pipelines |

### 2.3 Data Types to Handle

| Sensor/Stream | Fields | Rate | Volume/flight |
|---------------|--------|------|---------------|
| IMU | accel(x,y,z), gyro(x,y,z), temp | 200-1000 Hz | ~50 MB |
| GPS/GNSS | lat, lon, alt, hdop, vdop, fix_type | 1-10 Hz | ~5 MB |
| Barometer | pressure, altitude, temperature | 10-50 Hz | ~2 MB |
| Magnetometer | mag(x,y,z) | 10-50 Hz | ~2 MB |
| Battery | voltage, current, remaining | 1-10 Hz | ~1 MB |
| Attitude | quaternion/roll/pitch/yaw | 100-500 Hz | ~20 MB |
| RC Inputs | channel values | 50-100 Hz | ~5 MB |
| Actuator Outputs | motor/servo commands | 100-500 Hz | ~20 MB |
| EKF State | full state vector, covariance | 100-500 Hz | ~30 MB |
| Waypoints | lat, lon, alt, command | 0.1-1 Hz | <1 MB |
| Images | RGB/depth frames | 15-30 Hz | ~500 MB-2 GB |

---

## 3. Gap Analysis by Stage

### 3.1 Data Ingestion (CRITICAL — completely missing)

**What exists:** Nothing. Algorithms take `StateVector` dataclasses constructed in code.

**What's needed:**

1. **ULog reader** — Parse PX4 `.ulg` files using `pyulog` or `pyulog2csv`
   - Extract: `vehicle_attitude`, `vehicle_local_position`, `sensor_combined`, `battery_status`, `vehicle_status`, `actuator_outputs`
   - Convert to `StateVector` with timestamps
   - Handle multi-topic sync by timestamp

2. **MAVLink log reader** — Parse ArduPilot `.bin` / PX4 `.tlog`
   - Use `pymavlink` mavutil or `mavlogdump`
   - Extract: `ATTITUDE`, `GLOBAL_POSITION_INT`, `RAW_IMU`, `SCALED_PRESSURE`, `SERVO_OUTPUT_RAW`, `STATUSTEXT`
   - Map MAVLink message types to internal types

3. **MCAP reader** — Parse ROS 2 / Foxglove `.mcap` files
   - Use `mcap` Python library
   - Extract: `/imu/data`, `/gps/fix`, `/odometry`, `/tf`, `/joint_states`
   - Support topic filtering and time-window slicing

4. **ROS 2 bag reader** — Parse legacy `.db3` SQLite bags
   - Use `rosbags` Python library (pure Python, no ROS install)
   - Auto-convert to MCAP or read directly

5. **CSV/JSON importer** — Generic tabular data
   - Map columns to `StateVector` fields
   - Support timestamp alignment

**Reference implementations:**
- `pyulog` — PX4 ULog parser
- `pymavlink` — MAVLink protocol library
- `mcap` — MCAP file format library
- `rosbags` — Pure Python ROS bag reader
- `rosbag-resurrector` — Pandas-like bag analysis with health checks

### 3.2 Data Processing (CRITICAL — completely missing)

**What exists:** Nothing. No data transformation layer.

**What's needed:**

1. **Multi-stream synchronization** — Align IMU, GPS, barometer, attitude by timestamp
   - Nearest-neighbor matching with configurable tolerance
   - Interpolation for missing samples
   - Sample-and-hold for low-rate streams

2. **Data cleaning** — Handle real-world sensor noise and gaps
   - Outlier detection (z-score, IQR)
   - Gap detection and interpolation
   - Duplicate timestamp removal
   - Unit conversion (deg→rad, m→ft, etc.)

3. **Coordinate transforms** — Convert between frames
   - NED ↔ ENU ↔ ECEF
   - Body frame ↔ World frame
   - Quaternion ↔ Euler ↔ Rotation matrix

4. **Feature extraction** — Derive useful signals
   - Velocity from position differentiation
   - Acceleration from IMU + gravity compensation
   - Heading from magnetometer + GPS course
   - Energy consumption from battery data

5. **Segmentation** — Split flights into phases
   - Takeoff, cruise, landing detection
   - Waypoint-to-waypoint segmentation
   - Anomaly/event detection

6. **Validation** — Data quality gates
   - Schema validation (required fields, types, ranges)
   - Rate validation (expected vs actual frequency)
   - Completeness check (missing topics, time gaps)
   - Health score (0-100 quality metric)

**Reference implementations:**
- `rosbag-resurrector` — Health checks, multi-stream sync, transforms
- `mcap-lancedb` — Schema-aware ingestion with typed structs
- `HFlow` — Quality gate + enrichment pipeline

### 3.3 Data Storage (CRITICAL — completely missing)

**What exists:** Nothing. All data is in-memory Python objects.

**What's needed:**

1. **Columnar storage** — Apache Parquet for tabular sensor data
   - Partitioned by flight_id, date, vehicle_type
   - Compressed (Snappy or Zstd)
   - Schema evolution support

2. **Lakehouse storage** — Delta Lake for versioned, ACID tables
   - Time travel (query data as of version N)
   - Schema enforcement and evolution
   - Upserts for incremental updates
   - Merge for deduplication

3. **Array storage** — Zarr for large numerical arrays
   - Chunked, compressed N-D arrays
   - Cloud-native (S3, GCS)
   - Ideal for trajectories, point clouds, images

4. **Metadata store** — DuckDB for flight/session metadata
   - Flight ID, vehicle type, date, duration, tags
   - Sensor configuration, firmware version
   - Quality scores, annotations

5. **Object storage** — S3/GCS for raw files and large binaries
   - Raw ULog/MCAP files
   - Images, point clouds
   - Model checkpoints

**Recommended storage layout:**

```
data/
├── raw/                          # Immutable raw files
│   ├── ulogs/
│   │   └── 2026-10-04_flight001.ulg
│   ├── mcaps/
│   │   └── 2026-10-04_flight001.mcap
│   └── mavlink/
│       └── 2026-10-04_flight001.bin
├── processed/                    # Cleaned, synced data
│   ├── parquet/
│   │   ├── flights/
│   │   │   └── flight_id=xxx/
│   │   │       ├── imu.parquet
│   │   │       ├── gps.parquet
│   │   │       └── attitude.parquet
│   │   └── trajectories/
│   │       └── flight_id=xxx/
│   │           └── trajectory.parquet
│   └── zarr/
│       └── flight_id=xxx/
│           └── images.zarr
├── curated/                      # Human-annotated, quality-gated
│   └── delta/
│       └── flights_delta/        # Delta Lake table
├── metadata/                     # DuckDB metadata
│   └── flights.duckdb
└── manifests/                    # Dataset manifests
    └── dataset_v1/
        ├── manifest.json
        └── README.md
```

**Reference implementations:**
- `Delta Lake` — ACID transactions, time travel, schema evolution
- `Deeplake` — Tensor-native, object-storage-backed, GPU-streamable
- `Zarr` — Chunked N-D array storage
- `DuckDB` — In-process analytical DB for metadata

### 3.4 Data Versioning (CRITICAL — completely missing)

**What exists:** Nothing. No concept of data versions or experiment reproducibility.

**What's needed:**

1. **Dataset versioning** — Named, versioned dataset collections
   - `create_dataset(name, description)`
   - `add_version(name, version, sources, config)`
   - `export_version(name, version, output_dir)`
   - SHA256 manifests for reproducibility

2. **Delta Lake time travel** — Query data at any point in time
   - `SELECT * FROM flights VERSION AS OF 5`
   - `SELECT * FROM flights TIMESTAMP AS OF '2026-10-04'`
   - Rollback to previous versions

3. **Experiment provenance** — Track which data produced which result
   - Algorithm version + config hash
   - Input data version + manifest hash
   - Output metrics + artifact hash
   - Full lineage graph

4. **Schema versioning** — Handle evolving data formats
   - Schema registry with compatibility checks
   - Migration scripts for breaking changes
   - Coexistence of old and new formats

5. **DVC-style pipeline versioning** — Track data pipeline stages
   - Each stage: code version + input hash → output hash
   - Selective recomputation (only re-run changed stages)
   - Pipeline DAG with dependency tracking

**Reference implementations:**
- `Delta Lake` — Built-in time travel and versioning
- `DVC` — Data version control for ML pipelines
- `rosbag-resurrector` — Versioned dataset collections with manifests
- `HFlow` — Dataset versioning with provenance tracking
- `Bagzel` — Artifact-based build system for ROS bags

---

## 4. Industry Pattern Analysis

### 4.1 Robotics Data Pipeline Patterns (from OSS research)

| Pattern | Projects | Key Idea | Fit for apex |
|---------|----------|----------|--------------|
| **Bag-as-DataFrame** | rosbag-resurrector | Treat MCAP/ROS bags like pandas DataFrames | ✅ High — familiar API |
| **MCAP→Lakehouse** | mcap-lancedb | Ingest MCAP directly into LanceDB | ✅ High — modern format |
| **Artifact-based builds** | Bagzel | Bazel-style dependency tracking for datasets | ✅ Medium — reproducibility |
| **4-stage lifecycle** | HFlow | Collect→Ingest→Quality gate→Curate | ✅ High — proven pattern |
| **Tensor-native storage** | Deeplake | Object-storage + GPU streaming | ✅ Medium — for ML training |
| **Lakehouse (Delta/Iceberg)** | Delta Lake, Iceberg | ACID + time travel on Parquet | ✅ High — industry standard |
| **Data platform (Rust)** | Mosaico | High-performance robotics data platform | ❌ Low — different stack |

### 4.2 Recommended Architecture for apex-autopilot-optimization

```
                    ┌─────────────────────────────────────────────┐
                    │           apex-autopilot-optimization        │
                    │                                             │
  ┌──────────┐     │  ┌─────────┐  ┌──────────┐  ┌───────────┐  │     ┌──────────┐
  │ PX4 ULog │────▶│  │ ingest/ │─▶│ process/ │─▶│  store/   │──┼────▶│  Delta   │
  └──────────┘     │  │         │  │          │  │           │  │     │  Lake    │
  ┌──────────┐     │  │ • ulog  │  │ • sync   │  │ • parquet │  │     └──────────┘
  │ MAVLink  │────▶│  │ • mcap  │  │ • clean  │  │ • delta   │  │
  └──────────┘     │  │ • mavlink│  │ • transform│ │ • zarr   │  │     ┌──────────┐
  ┌──────────┐     │  │ • csv   │  │ • validate│  │ • duckdb  │──┼────▶│  DuckDB  │
  │ ROS 2    │────▶│  │         │  │ • enrich │  │           │  │     │ metadata │
  └──────────┘     │  └─────────┘  └──────────┘  └───────────┘  │     └──────────┘
                    │         │              │           │      │     ┌──────────┐
                    │         ▼              ▼           ▼      │     │  DVC /   │
                    │  ┌─────────────────────────────────┐    │────▶│  Delta   │
                    │  │         version/                 │    │     │  time    │
                    │  │  • dataset versioning            │    │     │  travel  │
                    │  │  • experiment provenance         │    │     └──────────┘
                    │  │  • schema registry               │    │
                    │  │  • pipeline DAG (DVC-style)      │    │
                    │  └─────────────────────────────────┘    │
                    │         │                                │
                    │         ▼                                │
                    │  ┌──────────┐  ┌──────────┐  ┌───────┐ │
                    │  │  serve/  │─▶│  train/  │─▶│ eval/ │ │
                    │  │          │  │          │  │       │ │
                    │  │ • query  │  │ • PyTorch│  │ • bench│ │
                    │  │ • export │  │ • JAX    │  │ • compare│
                    │  │ • visualize│ │ • TF     │  │ • report│ │
                    │  └──────────┘  └──────────┘  └───────┘ │
                    └─────────────────────────────────────────────┘
```

---

## 5. Proposed Module Structure

```
src/apex_autopilot_optimization/
├── data/                          # NEW package
│   ├── __init__.py
│   ├── ingest/                    # Stage 1: Data ingestion
│   │   ├── __init__.py
│   │   ├── base.py                # DataSource ABC, IngestConfig
│   │   ├── ulog_reader.py         # PX4 ULog → StateVector
│   │   ├── mavlink_reader.py      # MAVLink .bin/.tlog → StateVector
│   │   ├── mcap_reader.py         # MCAP → StateVector
│   │   ├── ros_bag_reader.py      # ROS 2 .db3 → StateVector
│   │   └── csv_importer.py        # CSV/JSON → StateVector
│   ├── process/                   # Stage 2: Data processing
│   │   ├── __init__.py
│   │   ├── sync.py                # Multi-stream synchronization
│   │   ├── clean.py               # Outlier removal, gap filling
│   │   ├── transform.py           # Coordinate transforms, unit conversion
│   │   ├── validate.py            # Schema validation, health scores
│   │   ├── segment.py             # Flight phase segmentation
│   │   └── features.py            # Feature extraction
│   ├── store/                     # Stage 3: Data storage
│   │   ├── __init__.py
│   │   ├── base.py                # DataStore ABC, StoreConfig
│   │   ├── parquet_store.py       # Parquet writer/reader
│   │   ├── delta_store.py         # Delta Lake writer/reader
│   │   ├── zarr_store.py          # Zarr array store
│   │   ├── duckdb_store.py        # Metadata store
│   │   └── object_store.py        # S3/GCS raw file store
│   ├── version/                   # Stage 4: Data versioning
│   │   ├── __init__.py
│   │   ├── dataset.py             # DatasetManager, versioned collections
│   │   ├── manifest.py            # SHA256 manifests, provenance
│   │   ├── schema_registry.py     # Schema versioning, migrations
│   │   └── pipeline.py            # DVC-style pipeline DAG
│   ├── serve/                     # Stage 5: Data serving
│   │   ├── __init__.py
│   │   ├── query.py               # Query API (time range, filters)
│   │   ├── export.py              # Export to training formats
│   │   └── visualize.py           # Flight visualization
│   └── types.py                   # Data pipeline types
│       ├── FlightLog.py            # Raw flight log container
│       ├── SensorStream.py        # Single sensor time series
│       ├── SyncConfig.py          # Sync configuration
│       ├── DatasetRef.py          # Dataset reference
│       └── Provenance.py          # Experiment provenance
```

---

## 6. Dependency Recommendations

| Package | Purpose | Priority | License |
|---------|---------|----------|---------|
| `pyulog` | PX4 ULog parsing | P0 | MIT |
| `pymavlink` | MAVLink protocol | P0 | LGPLv3 |
| `mcap` | MCAP file format | P0 | Apache 2.0 |
| `mcap-ros2-support` | ROS 2 MCAP support | P1 | Apache 2.0 |
| `rosbags` | Pure Python ROS bag reader | P1 | MIT |
| `pyarrow` | Parquet/Arrow | P0 | Apache 2.0 |
| `deltalake` | Delta Lake storage | P0 | Apache 2.0 |
| `zarr` | Chunked array storage | P1 | MIT |
| `duckdb` | Analytical metadata DB | P1 | MIT |
| `pydantic` | Schema validation | P0 | Already dep |
| `pandas` | Data manipulation | P0 | BSD |
| `polars` | Fast DataFrame ops | P1 | MIT |
| `dvc` | Data version control | P1 | Apache 2.0 |
| `s3fs` / `gcsfs` | Object storage | P2 | BSD |

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Create `data/` package structure
- [ ] Define `DataSource` ABC, `DataStore` ABC
- [ ] Implement `ULogReader` (PX4 flight logs)
- [ [ ] Implement `MAVLinkReader` (ArduPilot logs)
- [ ] Implement `ParquetStore` (basic read/write)
- [ ] Unit tests with synthetic ULog/MAVLink data

### Phase 2: Processing (Weeks 3-4)
- [ ] Implement `sync.py` (multi-stream alignment)
- [ ] Implement `clean.py` (outlier removal, gap filling)
- [ ] Implement `transform.py` (coordinate frames, units)
- [ ] Implement `validate.py` (schema + health checks)
- [ ] Integration tests with real flight logs

### Phase 3: Storage & Versioning (Weeks 5-6)
- [ ] Implement `DeltaStore` (ACID + time travel)
- [ ] Implement `DuckDBStore` (metadata)
- [ ] Implement `DatasetManager` (versioned collections)
- [ ] Implement `Manifest` (SHA256 provenance)
- [ ] Implement `SchemaRegistry` (versioning + migrations)

### Phase 4: Serving & Integration (Weeks 7-8)
- [ ] Implement `query.py` (time-range, filtered queries)
- [ ] Implement `export.py` (training format export)
- [ ] Integrate with existing `benchmark.py` (dataset-bound benchmarks)
- [ ] Integrate with `evaluation.py` (dataset-bound evaluation)
- [ ] End-to-end test: ULog → process → store → version → serve → benchmark

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ULog format changes across PX4 versions | Medium | High | Schema registry + versioned parsers |
| Large file memory usage | High | Medium | Chunked/streaming ingestion (Polars lazy) |
| MAVLink dialect differences | Medium | High | Dialect detection + configurable mapping |
| Delta Lake Spark dependency | Medium | Low | Use `deltalake` Python lib (no Spark needed) |
| ROS bag format fragmentation | Low | Medium | Convert to MCAP as canonical format |
| Performance vs. in-memory algorithms | High | Medium | Zero-copy Arrow, lazy evaluation |

---

## 9. Summary of Gaps

| # | Gap | Severity | Effort | Dependencies |
|---|-----|----------|--------|--------------|
| 1 | No data ingestion (ULog, MAVLink, MCAP, ROS bags) | **Critical** | 2 weeks | pyulog, pymavlink, mcap |
| 2 | No data processing (sync, clean, transform, validate) | **Critical** | 2 weeks | pandas, polars |
| 3 | No data storage (Parquet, Delta Lake, Zarr, DuckDB) | **Critical** | 2 weeks | pyarrow, deltalake, zarr, duckdb |
| 4 | No data versioning (datasets, manifests, provenance) | **Critical** | 2 weeks | deltalake, dvc |
| 5 | No flight log import (PX4, ArduPilot formats) | **Critical** | 1 week | pyulog, pymavlink |
| 6 | No sensor data pipeline (IMU, GPS, barometer, etc.) | **Critical** | 1 week | — |
| 7 | No experiment reproducibility (data→result lineage) | **High** | 1 week | deltalake, dvc |
| 8 | No dataset-bound benchmarking | **High** | 1 week | — |
| 9 | No data quality/health scoring | **Medium** | 1 week | — |
| 10 | No training data export (PyTorch, TF, LeRobot) | **Medium** | 1 week | — |

**Total estimated effort:** 8 weeks (2 engineers) or 12 weeks (1 engineer)

---

## 10. References

1. **rosbag-resurrector** — Pandas-like analysis for ROS 2 bags with health checks, sync, ML export. https://github.com/vikramnagashoka/rosbag-resurrector
2. **mcap-lancedb** — Ingest MCAP/ROS bag files into LanceDB-ready datasets. https://github.com/lancedb/mcap-lancedb
3. **HFlow** — SDK for multimodal robotics data pipelines (YC S26). Four-stage lifecycle: collect→ingest→quality gate→curate.
4. **Mosaico** — Data platform for Robotics and Physical AI (Rust + Python SDK). https://github.com/mosaico-labs/mosaico
5. **Delta Lake** — Open-source storage layer with ACID transactions, time travel, schema evolution. https://delta.io
6. **Deeplake** — Tensor-native, object-storage-backed, GPU-streamable multimodal datasets. https://deeplake.ai
7. **Bagzel** — Artifact-based build system for ROS bag dataset construction. https://arxiv.org/html/2606.00162
8. **pyulog** — PX4 ULog parser. https://github.com/PX4/pyulog
9. **pymavlink** — MAVLink protocol library. https://github.com/ArduPilot/pymavlink
10. **mcap** — MCAP file format (ROS 2 default since Iron). https://mcap.dev
11. **rosbags** — Pure Python ROS bag reader (no ROS install). https://github.com/ika-rwth-aachen/rosbags
12. **DVC** — Data version control for ML pipelines. https://dvc.org
