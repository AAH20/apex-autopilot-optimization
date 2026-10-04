# Backup, Restore & Disaster Recovery Gap Report
## apex-autopilot-optimization

**Date:** 2026-10-04  
**Project:** apex-autopilot-optimization (20 modules, ~365 tests)  
**License:** AGPL-3.0  
**Assessment:** Complete audit of all 28 source files, 129+ test files, configuration, documentation

---

## Executive Summary

The project has **zero** backup, restore, or disaster recovery capabilities. No persistence layer exists anywhere in the codebase. All state is ephemeral — created in memory at process start and destroyed at process exit. This is a critical gap for a framework designed to run on physical UAV/UAS and ground vehicle autopilots where data loss can mean hardware loss or safety incidents.

---

## 1. What Backup Is Needed

### 1.1 Data Inventory (What Produces State)

| Module | State Produced | Current Persistence | Risk |
|--------|---------------|---------------------|------|
| `estimation/ekf.py` — `EKFEstimator` | 12-state vector, 12×12 covariance matrix, Kalman gain | None (in-memory only) | State loss on restart = lost position/velocity estimate |
| `swarm/task_allocation.py` — `TaskAllocator` | Agent assignments, task mappings | None | Lost coordination state |
| `swarm/formation.py` — `FormationController` | Formation topology, leader ID, spacing | None | Formation break on restart |
| `security.py` — `SecurityAuditLog` | Immutable security event log (login, auth failures, policy violations) | None (list in memory) | Compliance violation — audit trail lost on crash |
| `observability.py` — `MetricCollector` | Runtime metrics (CPU, memory, request counts) | None | Operational history lost |
| `observability.py` — `StructuredLogger` | Structured JSON log entries | None | Incident forensics impossible |
| `benchmark.py` — `EvolutionTracker` | Multi-generation benchmark scores, convergence data | None | Lost optimization history |
| `benchmark.py` — `BenchmarkResult` | P50/P95/P99 latency, mean, std dev | None | No historical performance comparison |
| `evaluation.py` — `EvaluationResult` | Weighted metric scores, pass/fail status | None | No evaluation history |
| `planning/*` — `PlanningResult` | Waypoints, cost, computation time, iterations | None | Re-computation required after restart |
| `optimization/minimum_snap.py` | Polynomial trajectory coefficients | None | Re-optimization required |
| `control/mpc.py` — `MPCController` | QP solution, control horizon state | None | Control discontinuity on restart |

### 1.2 Backup Categories Needed

#### A. Configuration Backup (CRITICAL)
- **What:** User configuration (scale, planner choice, module parameters, safety margins)
- **Where it exists:** `onboarding/sizing.py` generates YAML configs; `config_validator.py` validates dicts
- **Gap:** Generated configs are returned as strings/dicts but never written to disk. A user who generates a config must manually save it.
- **Impact:** Misconfiguration after restart, lost tuning parameters

#### B. Security Audit Trail Backup (CRITICAL — Compliance)
- **What:** `SecurityAuditLog` entries (login events, auth failures, encryption status checks)
- **Where it exists:** `security.py` — in-memory list only
- **Gap:** No file append, no log rotation, no persistence. All audit data lost on process exit.
- **Impact:** Cannot meet DO-178C / ISO 26262 audit requirements. Security incidents untraceable.

#### C. Operational Telemetry Backup (HIGH)
- **What:** Metrics from `MetricCollector`, logs from `StructuredLogger`
- **Where it exists:** `observability.py` — in-memory dicts only
- **Gap:** No log file output, no metrics export (Prometheus/StatsD), no persistence.
- **Impact:** No incident forensics, no performance trending, no SLA monitoring

#### D. Algorithm State Checkpointing (HIGH)
- **What:** EKF covariance/state, formation topology, allocation assignments, trajectory coefficients
- **Where it exists:** All planner/estimator/controller modules — pure in-memory computation
- **Gap:** No checkpoint/restore mechanism. All algorithm state is lost on restart.
- **Impact:** EKF must re-converge from scratch (loss of position lock). Formation must re-negotiate. Tasks must re-allocate.

#### E. Benchmark & Evaluation History (MEDIUM)
- **What:** `EvolutionTracker` generations, `BenchmarkResult` historical data, `EvaluationResult` scores
- **Where it exists:** `benchmark.py`, `evaluation.py` — in-memory lists
- **Gap:** No CSV/JSON/DB export. No historical comparison possible across runs.
- **Impact:** Cannot track performance regression/improvement over time

---

## 2. How to Implement Restore

### 2.1 Architecture: New `persistence` Module

Create `src/apex_autopilot_optimization/persistence/` with:

```
persistence/
├── __init__.py              # Public API exports
├── base.py                  # Serializable ABC + DataStore ABC
├── file_store.py            # JSON/YAML file-based store (default)
├── checkpoint.py            # Checkpoint/restore orchestrator
├── config_store.py          # Configuration persistence
├── audit_store.py           # Append-only audit log persistence
├── metrics_store.py         # Metrics + log persistence
└── state_store.py           # Algorithm state (EKF, formation, allocation)
```

### 2.2 Core Interfaces

```python
# persistence/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
from pathlib import Path

T = TypeVar("T")

@dataclass(frozen=True)
class CheckpointMetadata:
    """Metadata for a checkpoint."""
    checkpoint_id: str
    timestamp: str  # ISO 8601
    module: str
    version: str    # schema version
    checksum: str   # SHA-256 of payload

class Serializable(ABC, Generic[T]):
    """ABC for objects that can be checkpointed."""
    
    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        ...
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> T:
        """Restore from dict, with validation."""
        ...

class DataStore(ABC):
    """Abstract storage backend."""
    
    @abstractmethod
    def save(self, key: str, data: dict[str, Any]) -> None:
        ...
    
    @abstractmethod
    def load(self, key: str) -> dict[str, Any] | None:
        ...
    
    @abstractmethod
    def append(self, key: str, entry: dict[str, Any]) -> None:
        """Append-only write (for audit logs)."""
        ...
    
    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        ...
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        ...
```

### 2.3 Checkpoint/Restore Orchestrator

```python
# persistence/checkpoint.py
class CheckpointManager:
    """Create and restore checkpoints of module state."""
    
    def __init__(self, store: DataStore, retention: int = 5):
        self.store = store
        self.retention = retention  # Keep last N checkpoints
    
    def create(self, module: str, state: Serializable) -> str:
        """Create a checkpoint. Returns checkpoint ID."""
        checkpoint_id = f"{module}-{datetime.now(timezone.utc).isoformat()}"
        payload = state.to_dict()
        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            timestamp=payload.get("timestamp", ""),
            module=module,
            version="1.0",
            checksum=hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
        )
        self.store.save(checkpoint_id, {
            "metadata": asdict(metadata),
            "payload": payload,
        })
        self._enforce_retention(module)
        return checkpoint_id
    
    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        """Restore from checkpoint with checksum verification."""
        record = self.store.load(checkpoint_id)
        if record is None:
            raise CheckpointNotFoundError(checkpoint_id)
        
        # Verify checksum
        payload = record["payload"]
        expected = record["metadata"]["checksum"]
        actual = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        if actual != expected:
            raise CheckpointCorruptedError(checkpoint_id)
        
        return payload
    
    def restore_latest(self, module: str) -> dict[str, Any]:
        """Find and restore the latest checkpoint for a module."""
        keys = self.store.list_keys(prefix=f"{module}-")
        if not keys:
            raise CheckpointNotFoundError(f"No checkpoints for {module}")
        return self.restore(sorted(keys)[-1])
    
    def _enforce_retention(self, module: str) -> None:
        """Keep only the last N checkpoints for a module."""
        keys = sorted(self.store.list_keys(prefix=f"{module}-"))
        while len(keys) > self.retention:
            self.store.delete(keys.pop(0))
```

### 2.4 Module Integration Points

Each module gets checkpoint/restore methods:

```python
# estimation/ekf.py — Add to EKFEstimator
class EKFEstimator:
    # ... existing code ...
    
    def checkpoint(self) -> dict[str, Any]:
        """Serialize estimator state for checkpointing."""
        return {
            "state": self.state.to_array().tolist(),
            "covariance": self.P.tolist(),
            "timestamp": time.time(),
        }
    
    @classmethod
    def restore(cls, data: dict[str, Any], config: EKFConfig) -> EKFEstimator:
        """Restore estimator from checkpoint."""
        est = cls(config)
        est._x = np.array(data["state"])
        est._P = np.array(data["covariance"])
        return est
```

```python
# security.py — Add to SecurityAuditLog
class SecurityAuditLog:
    # ... existing code ...
    
    def attach_store(self, store: DataStore) -> None:
        """Attach persistent store for append-only audit trail."""
        self._store = store
    
    def log_event(self, event_type: str, details: dict[str, Any]) -> None:
        entry = {
            "timestamp": int(time.time()),
            "event_type": event_type,
            "details": details,
        }
        self.entries.append(entry)
        if self._store:
            self._store.append("audit", entry)
```

### 2.5 Restore Procedures

| Scenario | Procedure | Downtime |
|----------|-----------|----------|
| Process restart (planned) | `CheckpointManager.restore_latest(module)` → re-inject state | ~10-100ms |
| Process crash (unplanned) | On startup: check for latest checkpoint → restore or re-initialize | ~10-500ms |
| Configuration loss | `config_store.load_latest()` → re-apply | ~1ms |
| Audit trail recovery | Read from append-only file store → re-index in memory | ~100ms |
| Full system rebuild | Restore all checkpoints in dependency order: config → EKF → planning → control | ~1-5s |

---

## 3. What Disaster Recovery to Add

### 3.1 Disaster Recovery Scenarios & Mitigations

| Scenario | Probability | Impact | Current Posture | Required DR |
|----------|------------|--------|-----------------|-------------|
| SD card corruption (embedded Linux) | HIGH on UAV | Catastrophic — total state loss | None | Config + EKF checkpoint to companion computer |
| Process crash (segfault, OOM kill) | HIGH | Algorithm state lost | None | Periodic EKF/formation checkpointing |
| Power loss (battery depletion) | MEDIUM | In-flight state loss | None | 1Hz checkpoint of critical state to non-volatile storage |
| Sensor failure (IMU, GPS) | MEDIUM | EKF divergence | None | EKF covariance floor + automatic re-initialization |
| Communication loss (MAVLink drop) | MEDIUM | No new commands | None | Autonomous RTL (Return-to-Launch) trigger |
| Memory corruption (cosmic ray bit flip) | LOW | Silent data corruption | None | Checksum-verified checkpoints + dual-store redundancy |
| Software bug (planner infinite loop) | LOW | No output | None | Watchdog timer + planner timeout + fallback path |

### 3.2 DR Mechanisms to Implement

#### A. Periodic State Checkpointing
```python
# persistence/checkpoint.py — Background checkpoint scheduler
class PeriodicCheckpoint:
    """Background thread that periodically checkpoints critical state."""
    
    def __init__(self, manager: CheckpointManager, interval_s: float = 1.0):
        self.manager = manager
        self.interval_s = interval_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
    
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def _run(self) -> None:
        while not self._stop_event.is_set():
            # Checkpoint all registered providers
            for provider in self._providers:
                try:
                    self.manager.create(provider.module, provider.get_state())
                except Exception:
                    pass  # Don't let checkpoint failure crash the system
            self._stop_event.wait(self.interval_s)
    
    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
```

#### B. Crash-Resilient Audit Logging
```python
# persistence/audit_store.py
class AuditLogStore(FileStore):
    """Append-only audit log with fsync for crash resilience."""
    
    def append(self, key: str, entry: dict[str, Any]) -> None:
        path = self._path_for(key)
        with open(path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())  # Ensure durability
```

#### C. Configuration Versioning & Rollback
```python
# persistence/config_store.py
class ConfigStore(FileStore):
    """Store configuration with versioning and rollback support."""
    
    VERSION_FILE = "config_versions.json"
    
    def save_versioned(self, config: dict[str, Any]) -> str:
        """Save a new config version. Returns version ID."""
        version_id = f"v{int(time.time() * 1000)}"
        self.save(f"config/{version_id}", config)
        
        # Update version index
        versions = self._load_versions()
        versions.append({
            "version_id": version_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checksum": hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()
            ).hexdigest(),
        })
        self.save(self.VERSION_FILE, {"versions": versions})
        return version_id
    
    def rollback(self, version_id: str) -> dict[str, Any]:
        """Roll back to a previous config version."""
        config = self.load(f"config/{version_id}")
        if config is None:
            raise ConfigVersionNotFoundError(version_id)
        return config
```

#### D. Health-Aware Automatic Recovery
```python
# diagnostics.py — Add recovery recommendations
def check_checkpoint_status() -> DiagnosticResult:
    """Check if checkpoint system is functioning."""
    try:
        from apex_autopilot_optimization.persistence import CheckpointManager
        # Verify store is writable
        return DiagnosticResult(
            name="checkpoint_system",
            status=DiagnosticStatus.PASS,
            message="Checkpoint system available",
        )
    except Exception as e:
        return DiagnosticResult(
            name="checkpoint_system",
            status=DiagnosticStatus.FAIL,
            message=f"Checkpoint system unavailable: {e}",
            fix="Install persistence module: pip install -e '.[persistence]'",
        )
```

### 3.3 DR Tiers

| Tier | RTO | RPO | Mechanism | Use Case |
|------|-----|-----|-----------|----------|
| Tier 1 — Process restart | <1s | 1s | In-memory checkpoint restore | Development, testing |
| Tier 2 — Service failover | <5s | 1s | File-based checkpoint on local disk | Single-vehicle deployment |
| Tier 3 — Vehicle recovery | <60s | 1s | Checkpoint replicated to companion computer | Field deployment |
| Tier 4 — Site disaster | <24h | 1h | Config + code in git; checkpoints in cloud | Fleet management |

---

## 4. How to Maintain Data Durability

### 4.1 Durability Mechanisms

#### A. Write-Ahead Logging (WAL) for Audit Logs
```python
# persistence/audit_store.py
class WALAuditStore(AuditLogStore):
    """Write-ahead log for guaranteed durability."""
    
    def append(self, key: str, entry: dict[str, Any]) -> None:
        path = self._path_for(key)
        # 1. Append to WAL
        wal_path = f"{path}.wal"
        with open(wal_path, "a") as f:
            record = json.dumps(entry, default=str)
            f.write(record + "\n")
            f.flush()
            os.fsync(f.fileno())
        
        # 2. Compact into main log periodically
        self._maybe_compact(path)
    
    def recover(self) -> list[dict[str, Any]]:
        """Recover entries from WAL after crash."""
        entries = []
        for wal_file in self._store_path.glob("*.wal"):
            with open(wal_file) as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # Partial write — skip
        return entries
```

#### B. Checksum-Verified State Snapshots
Every checkpoint includes SHA-256 checksum (shown in §2.3). On restore, checksum is verified before state is accepted. Corrupted checkpoints are rejected and the next-latest is tried.

#### C. Dual-Store Redundancy
```python
# persistence/file_store.py
class RedundantFileStore(FileStore):
    """Write to two independent storage locations."""
    
    def __init__(self, primary: Path, secondary: Path):
        self.primary = primary
        self.secondary = secondary
    
    def save(self, key: str, data: dict[str, Any]) -> None:
        # Write to both stores
        for base in [self.primary, self.secondary]:
            path = base / f"{key}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
    
    def load(self, key: str) -> dict[str, Any] | None:
        # Try primary, fall back to secondary
        for base in [self.primary, self.secondary]:
            path = base / f"{key}.json"
            if path.exists():
                with open(path) as f:
                    return json.load(f)
        return None
```

#### D. Configuration Drift Detection
```python
# persistence/config_store.py
def detect_config_drift(
    current: dict[str, Any], 
    stored: dict[str, Any]
) -> list[dict[str, Any]]:
    """Detect configuration drift between current and stored."""
    drift = []
    for key in set(current.keys()) | set(stored.keys()):
        if key not in stored:
            drift.append({"field": key, "type": "new", "current": current[key]})
        elif key not in current:
            drift.append({"field": key, "type": "removed", "stored": stored[key]})
        elif current[key] != stored[key]:
            drift.append({
                "field": key,
                "type": "changed",
                "stored": stored[key],
                "current": current[key],
            })
    return drift
```

### 4.2 Durability Guarantees by Data Type

| Data Type | Durability Level | Mechanism | Guarantee |
|-----------|-----------------|-----------|-----------|
| Security audit log | Strong (fsync per write) | Append-only + fsync | No audit loss on crash |
| EKF state | Periodic (1Hz) | JSON checkpoint + checksum | Max 1s state loss |
| Configuration | On-change | Versioned JSON + dual-store | Zero config loss |
| Metrics/Logs | Best-effort | Async file write | <5s telemetry loss |
| Benchmark history | On-completion | JSON export | No benchmark loss |
| Formation state | Periodic (10Hz) | JSON checkpoint | Max 100ms formation loss |

### 4.3 Retention & Lifecycle Policy

```python
# persistence/lifecycle.py
@dataclass(frozen=True)
class RetentionPolicy:
    """Retention policy for different data types."""
    max_age_days: int = 90
    max_size_mb: int = 100
    min_versions: int = 3
    compaction_interval_hours: int = 24

RETENTION_POLICIES: dict[str, RetentionPolicy] = {
    "audit": RetentionPolicy(max_age_days=365, max_size_mb=500),  # Compliance
    "checkpoint": RetentionPolicy(max_age_days=7, max_size_mb=50),
    "config": RetentionPolicy(max_age_days=365, max_size_mb=10),
    "metrics": RetentionPolicy(max_age_days=30, max_size_mb=100),
    "benchmark": RetentionPolicy(max_age_days=365, max_size_mb=50),
}
```

### 4.4 Monitoring & Alerting

Add to `observability.py`:
```python
class DurabilityMonitor:
    """Monitor data durability health."""
    
    def check_store_writable(self, store: DataStore) -> bool:
        try:
            test_key = f"durability_test_{int(time.time())}"
            store.save(test_key, {"test": True})
            store.delete(test_key)
            return True
        except OSError:
            return False
    
    def check_checkpoint_freshness(
        self, module: str, max_age_s: float
    ) -> dict[str, Any]:
        """Check if a module's checkpoint is fresh."""
        # Implementation: check latest checkpoint timestamp
        ...
```

---

## 5. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
| Task | Priority | Effort |
|------|----------|--------|
| Create `persistence/base.py` (ABCs) | P0 | 2d |
| Create `persistence/file_store.py` (JSON store) | P0 | 2d |
| Create `persistence/checkpoint.py` | P0 | 3d |
| Add `Serializable` to `core/types.py` | P1 | 1d |
| Write unit tests for persistence module | P0 | 2d |

### Phase 2: Critical State (Week 3-4)
| Task | Priority | Effort |
|------|----------|--------|
| EKF checkpoint/restore | P0 | 2d |
| Security audit log persistence (append-only + fsync) | P0 | 2d |
| Configuration persistence with versioning | P1 | 3d |
| Periodic checkpoint scheduler | P1 | 2d |

### Phase 3: Operational Data (Week 5-6)
| Task | Priority | Effort |
|------|----------|--------|
| Metrics/log file export | P1 | 3d |
| Benchmark/evaluation history export | P2 | 2d |
| Dual-store redundancy | P2 | 2d |
| WAL recovery | P2 | 3d |

### Phase 4: DR & Hardening (Week 7-8)
| Task | Priority | Effort |
|------|----------|--------|
| Crash recovery integration tests | P0 | 3d |
| Config drift detection | P2 | 2d |
| Retention policy enforcement | P2 | 2d |
| DR runbook documentation | P1 | 1d |

---

## 6. Dependencies to Add

```toml
# pyproject.toml additions
[project.optional-dependencies]
persistence = [
    "jsonschema>=4.0.0",      # Schema validation for checkpoints
]

[project.optional-dependencies]
dr = [
    "jsonschema>=4.0.0",
    "tenacity>=8.0.0",        # Retry logic for store operations
]
```

No new runtime dependencies required for core persistence — Python stdlib `json`, `pathlib`, `hashlib`, `os.fsync` are sufficient.

---

## 7. Testing Strategy

| Test Category | Count | Approach |
|---------------|-------|----------|
| Unit tests — store operations | ~20 | File I/O round-trip, corruption detection |
| Unit tests — checkpoint/restore | ~15 | Checksum verification, retention enforcement |
| Unit tests — serialization | ~15 | Each `Serializable` type: `from_dict(to_dict(x)) == x` |
| Integration tests — crash recovery | ~5 | Simulate crash: write partial checkpoint → verify WAL recovery |
| Integration tests — EKF restore | ~3 | Checkpoint EKF → restore → verify state convergence |
| Property-based tests — round-trip | ~10 | `hypothesis`: all dataclasses survive round-trip |
| Performance tests — checkpoint overhead | ~3 | Assert <1ms per checkpoint operation |

---

## 8. Summary of Gaps

| # | Gap | Severity | Category |
|---|-----|----------|----------|
| 1 | No persistence layer exists | CRITICAL | Architecture |
| 2 | Security audit log is ephemeral | CRITICAL | Compliance |
| 3 | No algorithm state checkpointing | HIGH | Safety |
| 4 | Configuration not persisted | HIGH | Operations |
| 5 | No metrics/log persistence | HIGH | Observability |
| 6 | No crash recovery mechanism | HIGH | Reliability |
| 7 | No config versioning/rollback | MEDIUM | Operations |
| 8 | No checkpoint integrity verification | MEDIUM | Reliability |
| 9 | No durability monitoring | MEDIUM | Observability |
| 10 | No retention/lifecycle management | LOW | Operations |

**Recommendation:** Phase 1 + Phase 2 (foundation + critical state) should be implemented before any field deployment. The project's stated goal of running on physical UAV/UAS makes state durability a safety requirement, not a nice-to-have.
