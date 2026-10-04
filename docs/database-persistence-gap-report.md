# Database & Persistence Layer Gap Report — apex-autopilot-optimization

**Date:** 2026-10-04  
**Scope:** Full source tree (`src/apex_autopilot/optimization/`) — 20 modules, 365 tests  
**Method:** Static analysis of all modules + `pyproject.toml` + `README.md` + existing gap reports

---

## Executive Summary

The project has **zero persistence**. Every module operates purely in-memory using Python dataclasses, lists, and dicts. There is no database, no ORM, no serialization framework, no file I/O, no configuration persistence, and no migration system. All state is lost when the process exits. This is the single largest architectural gap in the project.

| Aspect | Status |
|--------|--------|
| Database / ORM | **None** — no SQLAlchemy, Peewee, Django ORM, or raw SQL |
| File persistence | **None** — no `open()`, `json.dump`, `yaml.dump`, `pickle`, `Path.write_text` |
| Configuration storage | **None** — configs are generated as YAML strings but never saved to disk |
| Audit log persistence | **None** — `SecurityAuditLog` keeps entries in a list, lost on exit |
| Metrics persistence | **None** — `MetricCollector` stores in a dict, no time-series storage |
| Benchmark results | **None** — `EvolutionTracker` keeps generations in a list |
| Planning results | **None** — `PlanningResult` is returned but never persisted |
| Trajectory persistence | **None** — `Trajectory` objects exist only in memory |
| State estimation | **None** — `EKFEstimator` state is in-memory numpy arrays |
| Security tokens | **None** — `AuthenticationHelper` tokens are in a dict |
| Migration framework | **None** — no Alembic, no Django migrations, no version tracking |
| Data consistency | **None** — no transactions, no constraints, no validation at rest |

---

## 1. What Persistence Is Needed

### 1.1 Domain Entities Requiring Persistence

| Entity | Current Representation | Module | Persistence Need |
|--------|----------------------|--------|-----------------|
| `PlanningProblem` | `@dataclass(frozen=True)` | `core/types.py` | Store problem definitions for replay/audit |
| `PlanningResult` | `@dataclass(frozen=True)` | `core/types.py` | Store planning outcomes, cost, iterations |
| `Trajectory` | `@dataclass(frozen=True)` | `core/types.py` | Store trajectories (states, controls, timestamps) |
| `StateVector` | `@dataclass(frozen=True)` | `core/types.py` | Store vehicle state history |
| `ControlInput` | `@dataclass(frozen=True)` | `core/types.py` | Store control commands issued |
| `Waypoint` | `@dataclass(frozen=True)` | `core/types.py` | Store mission waypoints |
| `Pose3D` / `Velocity3D` | `@dataclass(frozen=True)` | `core/types.py` | Store pose/velocity telemetry |
| `BottleneckReport` | `@dataclass(frozen=True)` | `core/types.py` | Store identified bottlenecks |
| `Task` / `Agent` | `@dataclass(slots=True)` | `swarm/task_allocation.py` | Store swarm task assignments |
| `BenchmarkResult` | `@dataclass` | `benchmark.py` | Store benchmark runs for comparison |
| `EvolutionTracker.generations` | `list[dict]` | `benchmark.py` | Store evolution history across runs |
| `EvaluationResult` | `@dataclass` | `evaluation.py` | Store evaluation scores and pass/fail |
| `SecurityAuditLog.entries` | `list[dict]` | `security.py` | Store immutable security events |
| `AuthenticationHelper._tokens` | `dict[str, dict]` | `security.py` | Store auth tokens with expiry |
| `MetricCollector._metrics` | `dict[str, Any]` | `observability.py` | Store time-series metrics |
| `DiagnosticReport` | `@dataclass(frozen=True)` | `diagnostics.py` | Store diagnostic history |
| `SizingProfile` | `@dataclass(frozen=True)` | `onboarding/sizing.py` | Store org scale configuration |
| `ModuleRegistry` | `dict[str, ModuleInfo]` | `onboarding/sizing.py` | Store module metadata |
| `EKFEstimator` state | numpy arrays | `estimation/ekf.py` | Store filter state for warm-start |
| `CBFFilter` config | `@dataclass(frozen=True)` | `safety/cbf.py` | Store safety filter configuration |
| `MPCController` config | `@dataclass(frozen=True)` | `control/mpc.py` | Store controller configuration |

### 1.2 Functional Areas Requiring Persistence

| Area | Gap | Impact |
|------|-----|--------|
| **Configuration management** | `generate_config_yaml()` returns a string; no `save_config()` / `load_config()` | Users cannot save/reload configurations; setup wizard state is lost |
| **Mission planning** | `PlanningResult` with `Trajectory` is returned but never stored | Cannot replay missions, compare plans, or audit decisions |
| **Telemetry logging** | `StateVector` and `ControlInput` are generated but not logged | No flight history, no post-mission analysis |
| **Security audit** | `SecurityAuditLog` keeps entries in a list | Audit trail lost on exit; no compliance evidence |
| **Metrics & observability** | `MetricCollector` stores in a dict | No time-series data, no trend analysis, no alerting history |
| **Benchmark evolution** | `EvolutionTracker` keeps generations in a list | Cannot track performance across code changes |
| **Evaluation history** | `EvaluationResult` is returned but not stored | Cannot track quality improvements over time |
| **Swarm state** | `TaskAllocator` assignments are in-memory | Cannot recover from crashes, no distributed state |
| **Estimator warm-start** | `EKFEstimator` starts from zero state | No continuity between planning sessions |
| **Setup wizard** | `SetupWizard` tracks progress in `_completed` list | Progress lost between runs |

---

## 2. How to Implement Data Storage

### 2.1 Recommended Architecture: Layered Persistence

```
┌─────────────────────────────────────────────────────┐
│                  Domain Layer                        │
│  (dataclasses: PlanningProblem, Trajectory, etc.)   │
├─────────────────────────────────────────────────────┤
│              Repository Layer (new)                  │
│  (abstract base + concrete implementations)         │
├──────────────────────┬──────────────────────────────┤
│   SQLite (embedded)  │   In-Memory (testing)        │
│   (production)       │   (unit tests)               │
├──────────────────────┴──────────────────────────────┤
│              Migration Layer (new)                   │
│  (schema versioning, upgrade/downgrade)             │
└─────────────────────────────────────────────────────┘
```

### 2.2 ORM Selection: Peewee (Recommended)

| Criterion | SQLAlchemy 2.0 | Django ORM | Peewee |
|-----------|---------------|------------|--------|
| **Weight** | Heavy (~50k LOC) | Very heavy (full framework) | Light (~10k LOC, single file) |
| **Pattern** | Data Mapper | Active Record | Active Record |
| **Async** | First-class | Hybrid | Limited (peewee-async) |
| **Migration** | Alembic (separate) | Built-in | Manual / playhouse.migrate |
| **Type safety** | Excellent (Mapped) | Good (stubs) | Moderate |
| **Learning curve** | Steep | Medium | Low |
| **Fit for this project** | Overkill | Wrong framework | **Best fit** |

**Recommendation: Peewee** — the project is a standalone Python library (not a web app), uses dataclasses extensively, and needs a lightweight ORM that doesn't impose a framework. Peewee's Active Record pattern maps naturally to the existing dataclass-based domain model.

### 2.3 Alternative: SQLite + dataclasses (No ORM)

For a project this size, a simpler approach may be better:

```python
# src/apex_autopilot_optimization/persistence/database.py
import sqlite3
import json
from pathlib import Path
from typing import Any

class Database:
    """SQLite-backed persistence with JSON serialization for complex types."""
    
    def __init__(self, db_path: str = "apex_autopilot.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS planning_problems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_type TEXT NOT NULL,
                start_state TEXT NOT NULL,  -- JSON
                goal TEXT NOT NULL,         -- JSON
                waypoints TEXT NOT NULL,    -- JSON array
                obstacles TEXT NOT NULL,    -- JSON array
                constraints TEXT NOT NULL,  -- JSON array
                objectives TEXT NOT NULL,   -- JSON array
                time_horizon_s REAL NOT NULL,
                resolution_m REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS planning_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id INTEGER NOT NULL,
                success INTEGER NOT NULL,
                trajectory TEXT,            -- JSON
                computation_time_ms REAL NOT NULL,
                iterations INTEGER NOT NULL,
                cost REAL NOT NULL,
                message TEXT NOT NULL,
                metadata TEXT NOT NULL,     -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (problem_id) REFERENCES planning_problems(id)
            );
            
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id INTEGER NOT NULL,
                states TEXT NOT NULL,       -- JSON array of StateVector
                controls TEXT NOT NULL,     -- JSON array of ControlInput
                timestamps TEXT NOT NULL,   -- JSON array of floats
                vehicle_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (result_id) REFERENCES planning_results(id)
            );
            
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL,      -- JSON
                timestamp REAL NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                value REAL NOT NULL,
                timestamp REAL NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mean_ms REAL NOT NULL,
                p50_ms REAL NOT NULL,
                p95_ms REAL NOT NULL,
                p99_ms REAL NOT NULL,
                iterations INTEGER NOT NULL,
                std_dev_ms REAL NOT NULL,
                min_ms REAL NOT NULL,
                max_ms REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS evolution_generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generation INTEGER NOT NULL,
                score REAL NOT NULL,
                metadata TEXT NOT NULL,     -- JSON
                timestamp REAL NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                config TEXT NOT NULL,       -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                subject TEXT NOT NULL,
                issued_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
        """)
        self.conn.commit()
```

### 2.4 Repository Pattern

```python
# src/apex_autopilot_optimization/persistence/repositories.py
from typing import Optional, List
import json
import time
from apex_autopilot_optimization.core.types import (
    PlanningProblem, PlanningResult, Trajectory, StateVector, ControlInput
)

class PlanningResultRepository:
    """Repository for planning results."""
    
    def __init__(self, db):
        self.db = db
    
    def save(self, problem: PlanningProblem, result: PlanningResult) -> int:
        """Save a planning problem and its result. Returns the result ID."""
        cursor = self.db.conn.execute(
            """INSERT INTO planning_problems 
               (vehicle_type, start_state, goal, waypoints, obstacles, 
                constraints, objectives, time_horizon_s, resolution_m)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                problem.vehicle_type.name,
                json.dumps(problem.start.__dict__),
                json.dumps(problem.goal.__dict__),
                json.dumps([w.__dict__ for w in problem.waypoints]),
                json.dumps(problem.obstacles),
                json.dumps([c.__dict__ for c in problem.constraints]),
                json.dumps([o.__dict__ for o in problem.objectives]),
                problem.time_horizon_s,
                problem.resolution_m,
            )
        )
        problem_id = cursor.lastrowid
        
        trajectory_json = None
        if result.trajectory:
            trajectory_json = json.dumps({
                'states': [s.__dict__ for s in result.trajectory.states],
                'controls': [c.__dict__ for c in result.trajectory.controls],
                'timestamps': result.trajectory.timestamps.tolist(),
                'vehicle_type': result.trajectory.vehicle_type.name,
            })
        
        cursor = self.db.conn.execute(
            """INSERT INTO planning_results 
               (problem_id, success, trajectory, computation_time_ms, 
                iterations, cost, message, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                problem_id,
                int(result.success),
                trajectory_json,
                result.computation_time_ms,
                result.iterations,
                result.cost,
                result.message,
                json.dumps(result.metadata),
            )
        )
        self.db.conn.commit()
        return cursor.lastrowid
    
    def get(self, result_id: int) -> Optional[PlanningResult]:
        """Retrieve a planning result by ID."""
        row = self.db.conn.execute(
            "SELECT * FROM planning_results WHERE id = ?", (result_id,)
        ).fetchone()
        if row is None:
            return None
        # Deserialize and return PlanningResult...
        return self._deserialize_result(row)
    
    def list_recent(self, limit: int = 10) -> List[PlanningResult]:
        """List recent planning results."""
        rows = self.db.conn.execute(
            "SELECT * FROM planning_results ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [self._deserialize_result(r) for r in rows]
```

---

## 3. What Migration Patterns to Use

### 3.1 Schema Versioning

```python
# src/apex_autopilot_optimization/persistence/migrations.py
import sqlite3
from typing import Callable, List, Tuple

Migration = Tuple[int, str, Callable[[sqlite3.Connection], None]]

MIGRATIONS: List[Migration] = [
    (1, "initial_schema", lambda conn: conn.executescript("""
        CREATE TABLE IF NOT EXISTS planning_problems (...);
        CREATE TABLE IF NOT EXISTS planning_results (...);
        -- etc.
    """)),
    (2, "add_trajectory_table", lambda conn: conn.executescript("""
        CREATE TABLE IF NOT EXISTS trajectories (...);
    """)),
    (3, "add_audit_log_table", lambda conn: conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (...);
    """)),
    # Future migrations...
]

class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self, db):
        self.db = db
        self._ensure_version_table()
    
    def _ensure_version_table(self) -> None:
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.commit()
    
    def current_version(self) int:
        row = self.db.conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] if row and row[0] else 0
    
    def migrate(self) -> None:
        """Apply all pending migrations."""
        current = self.current_version()
        for version, name, fn in MIGRATIONS:
            if version > current:
                fn(self.db.conn)
                self.db.conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (version,)
                )
                self.db.conn.commit()
```

### 3.2 Migration Patterns

| Pattern | Use Case | Implementation |
|---------|----------|---------------|
| **Versioned migrations** | Schema evolution | `schema_version` table + ordered migration list |
| **Additive changes** | New columns/tables | `ALTER TABLE ... ADD COLUMN` (non-destructive) |
| **Data migration** | Backfill existing data | Python function in migration |
| **Rollback** | Failed migration | `down` function in each migration |
| **Idempotent migrations** | Safe re-runs | `IF NOT EXISTS` / `IF EXISTS` guards |

### 3.3 Naming Convention

```
migrations/
  001_initial_schema.py
  002_add_trajectory_table.py
  003_add_audit_log.py
  004_add_metrics_table.py
  005_add_benchmark_tables.py
  006_add_config_tables.py
  007_add_auth_tables.py
```

---

## 4. How to Maintain Data Consistency

### 4.1 Transaction Management

```python
# src/apex_autopilot_optimization/persistence/database.py
from contextlib import contextmanager

class Database:
    # ... existing code ...
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        try:
            self.conn.execute("BEGIN")
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
```

### 4.2 Consistency Rules

| Rule | Implementation |
|------|---------------|
| **Foreign key enforcement** | `PRAGMA foreign_keys = ON` |
| **Unique constraints** | `UNIQUE` on config names, token values |
| **NOT NULL constraints** | Required fields enforced at DB level |
| **Cascading deletes** | `ON DELETE CASCADE` for child records |
| **Audit immutability** | `audit_log` table has no UPDATE/DELETE grants |
| **Timestamp consistency** | `DEFAULT CURRENT_TIMESTAMP` for all `created_at` |

### 4.3 Data Validation at Rest

```python
# Validation before persistence
def validate_planning_result(result: PlanningResult) -> None:
    """Validate a planning result before saving."""
    if result.computation_time_ms < 0:
        raise ValueError("computation_time_ms must be non-negative")
    if result.iterations < 0:
        raise ValueError("iterations must be non-negative")
    if result.cost < 0:
        raise ValueError("cost must be non-negative")
    if result.success and result.trajectory is None:
        raise ValueError("Successful result must have a trajectory")
    if not result.success and result.trajectory is not None:
        raise ValueError("Failed result should not have a trajectory")
```

### 4.4 Concurrency Control

```python
# For multi-threaded access (e.g., parallel planning)
import threading

class ThreadSafeDatabase:
    """Thread-safe database wrapper."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
    
    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
```

### 4.5 Backup & Recovery

```python
def backup_database(db_path: str, backup_path: str) -> None:
    """Create a consistent backup of the database."""
    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)
    dest.close()
    source.close()
```

---

## 5. Implementation Roadmap

### Phase 1: Core Persistence (Week 1)
- [ ] Create `persistence/` package with `Database` class
- [ ] Implement SQLite schema for core entities
- [ ] Add `PlanningResultRepository`
- [ ] Add `ConfigurationRepository`
- [ ] Write unit tests with in-memory SQLite

### Phase 2: Audit & Metrics (Week 2)
- [ ] Add `AuditLogRepository` (immutable)
- [ ] Add `MetricsRepository` (time-series)
- [ ] Add `BenchmarkRepository`
- [ ] Add `EvolutionRepository`
- [ ] Integrate with existing modules

### Phase 3: Migration System (Week 3)
- [ ] Implement `MigrationManager`
- [ ] Create initial migration
- [ ] Add schema version tracking
- [ ] Write migration tests
- [ ] Document migration process

### Phase 4: Advanced Features (Week 4)
- [ ] Add `TrajectoryRepository` with compression
- [ ] Implement `ThreadSafeDatabase`
- [ ] Add backup/restore functionality
- [ ] Add data export (JSON/CSV)
- [ ] Performance optimization (indexing, WAL mode)

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Schema changes break existing data** | Versioned migrations with rollback capability |
| **SQLite concurrency limitations** | WAL mode + connection pooling + busy timeout |
| **Large trajectory data bloats DB** | Compress numpy arrays; store as BLOB or separate files |
| **No ORM means more boilerplate** | Code generation for repository classes |
| **Testing with real DB slows tests** | In-memory SQLite for unit tests; tmpdir for integration |
| **Data corruption** | Regular backups + integrity checks (`PRAGMA integrity_check`) |

---

## 7. Dependencies to Add

```toml
# pyproject.toml additions
[project.optional-dependencies]
persistence = [
    "peewee>=3.17.0,<4.0.0",  # Optional ORM alternative
]
```

**Note:** The recommended approach uses only stdlib `sqlite3` — no new required dependencies. Peewee is optional for teams that prefer an ORM.

---

## 8. Summary

| Question | Answer |
|----------|--------|
| **What persistence is needed?** | 20 domain entities across 8 functional areas |
| **How to implement?** | SQLite + stdlib `sqlite3` + repository pattern |
| **What migration patterns?** | Versioned migrations with `schema_version` table |
| **How to maintain consistency?** | Transactions, FK constraints, validation at rest, WAL mode |

The project can be made fully persistent with **zero new required dependencies** using Python's built-in `sqlite3` module. The repository pattern provides a clean separation between domain logic and persistence, and the migration system ensures schema evolution is safe and reversible.
