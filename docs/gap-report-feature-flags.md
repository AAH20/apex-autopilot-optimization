# Gap Analysis Report: Feature Flags & Experiment Framework

**Project:** `apex-autopilot-optimization`  
**Date:** 2026-10-04  
**Researcher:** Apex Research Swarm  

---

## Executive Summary

The `apex-autopilot-optimization` project currently has **zero feature flag infrastructure, no A/B testing capability, and no experiment tracking system**. This is a critical gap for a production autopilot optimization framework where safe rollout of new algorithms, planners, and controllers is essential. The project has 20 modules with 365 passing tests, a well-structured macro architecture, and strong domain types — but lacks the operational tooling to safely evolve algorithms in production.

**Severity:** HIGH — Without feature flags, every algorithm change is an all-or-nothing deploy with no kill switch, no gradual rollout, and no way to measure impact.

---

## 1. Feature Flag System — Gap Analysis

### Current State
- **No feature flags exist** anywhere in the codebase
- No `feature_flags.py`, `flags.py`, `toggles.py`, or equivalent module
- The project uses a static `config_validator.py` for config validation, but no runtime flag evaluation
- No environment-based configuration (dev/staging/prod)
- No remote configuration capability

### What's Needed

| Component | Description | Priority |
|-----------|-------------|----------|
| **Flag Store** | Central registry of all feature flags with metadata (name, description, owner, type, default value) | P0 |
| **Evaluation Engine** | Runtime flag evaluation with context (user_id, vehicle_type, environment, percentage rollout) | P0 |
| **Persistence Backend** | Pluggable backend: YAML file (default), Redis (distributed), env vars (CI/CD) | P1 |
| **CLI Integration** | `apex-autopilot flags list`, `flags get <name>`, `flags set <name> <value>` | P1 |
| **Programmatic API** | `FeatureFlags.is_enabled(flag_name, context) -> bool` | P0 |
| **Structured Logging** | Flag evaluation events logged for audit trail | P1 |

### Flag Categories Needed for This Project

1. **Algorithm Selection Flags** — Toggle between planner implementations (A* vs RRT vs PRM vs Hybrid A*)
2. **Optimization Strategy Flags** — Switch between minimum-snap and other trajectory optimizers
3. **Safety Filter Flags** — Enable/disable CBF with different safety margins
4. **Estimation Algorithm Flags** — EKF vs future UKF/particle filter implementations
5. **Swarm Coordination Flags** — Task allocation strategy (greedy vs auction-based vs market-based)
6. **Controller Selection Flags** — MPC vs PID vs LQR controller switching
7. **Formation Control Flags** — Line vs Wedge vs Hexagon formation patterns

### Recommended Implementation

**Phase 1: Core Flag System (P0)**
```python
# src/apex_autopilot_optimization/feature_flags/__init__.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
import hashlib
import yaml
from pathlib import Path

class FlagType(Enum):
    BOOLEAN = "boolean"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    JSON = "json"

class FlagCategory(Enum):
    ALGORITHM = "algorithm"
    OPTIMIZATION = "optimization"
    SAFETY = "safety"
    ESTIMATION = "estimation"
    SWARM = "swarm"
    CONTROL = "control"
    PLANNING = "planning"
    OPS = "ops"

@dataclass
class FeatureFlag:
    name: str
    flag_type: FlagType
    category: FlagCategory
    default_value: Any
    description: str = ""
    owner: str = ""
    enabled: bool = True
    rollout_percentage: float = 100.0
    allowed_contexts: list[str] = field(default_factory=list)
    expires_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class FeatureFlagStore:
    """Central feature flag registry with YAML persistence."""
    
    def __init__(self, config_path: str = "configs/feature_flags.yaml"):
        self.config_path = Path(config_path)
        self._flags: Dict[str, FeatureFlag] = {}
        self._load()
    
    def _load(self) -> None:
        if self.config_path.exists():
            with open(self.config_path) as f:
                data = yaml.safe_load(f)
                for name, flag_data in data.get("flags", {}).items():
                    self._flags[name] = FeatureFlag(name=name, **flag_data)
    
    def save(self) -> None:
        """Persist flags to YAML."""
        data = {"flags": {}}
        for name, flag in self._flags.items():
            data["flags"][name] = {
                "flag_type": flag.flag_type.value,
                "category": flag.category.value,
                "default_value": flag.default_value,
                "description": flag.description,
                "owner": flag.owner,
                "enabled": flag.enabled,
                "rollout_percentage": flag.rollout_percentage,
                "allowed_contexts": flag.allowed_contexts,
                "expires_at": flag.expires_at,
                "metadata": flag.metadata,
            }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
    
    def get(self, name: str) -> Optional[FeatureFlag]:
        return self._flags.get(name)
    
    def set(self, flag: FeatureFlag) -> None:
        self._flags[flag.name] = flag
        self.save()
    
    def list_all(self) -> list[FeatureFlag]:
        return list(self._flags.values())

class FeatureFlagEvaluator:
    """Evaluates feature flags with context-aware rollout."""
    
    def __init__(self, store: FeatureFlagStore):
        self.store = store
    
    def is_enabled(self, flag_name: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Check if a flag is enabled for the given context."""
        flag = self.store.get(flag_name)
        if flag is None or not flag.enabled:
            return False
        
        if context is None:
            return True
        
        # Check allowed contexts
        if flag.allowed_contexts:
            context_key = context.get("context_key", "")
            if context_key not in flag.allowed_contexts:
                return False
        
        # Percentage rollout via consistent hashing
        if flag.rollout_percentage < 100.0:
            user_id = context.get("user_id", "")
            bucket = self._hash_bucket(flag_name, user_id)
            return bucket < flag.rollout_percentage
        
        return True
    
    def get_value(self, flag_name: str, context: Optional[Dict[str, Any]] = None) -> Any:
        """Get the value of a flag for the given context."""
        flag = self.store.get(flag_name)
        if flag is None:
            return None
        if not self.is_enabled(flag_name, context):
            return flag.default_value
        return flag.metadata.get("value", flag.default_value)
    
    @staticmethod
    def _hash_bucket(flag_name: str, user_id: str) -> float:
        """Consistent hash for stable percentage rollout (0-100)."""
        key = f"{flag_name}:{user_id}".encode()
        digest = hashlib.sha256(key).hexdigest()
        return (int(digest[:8], 16) / 0xFFFFFFFF) * 100
```

**Phase 2: CLI Integration (P1)**
```python
# In cli.py or a new flags_cli.py
import typer
from apex_autopilot_optimization.feature_flags import FeatureFlagStore, FlagType, FlagCategory

flags_app = typer.Typer(help="Feature flag management")

@flags_app.command("list")
def list_flags():
    """List all feature flags."""
    store = FeatureFlagStore()
    for flag in store.list_all():
        status = "✓" if flag.enabled else "✗"
        typer.echo(f"{status} {flag.name} ({flag.category.value}): {flag.description}")

@flags_app.command("get")
def get_flag(name: str):
    """Get details of a specific flag."""
    store = FeatureFlagStore()
    flag = store.get(name)
    if flag:
        typer.echo(f"Name: {flag.name}")
        typer.echo(f"Type: {flag.flag_type.value}")
        typer.echo(f"Category: {flag.category.value}")
        typer.echo(f"Default: {flag.default_value}")
        typer.echo(f"Enabled: {flag.enabled}")
        typer.echo(f"Rollout: {flag.rollout_percentage}%")
        typer.echo(f"Owner: {flag.owner}")
    else:
        typer.echo(f"Flag '{name}' not found", err=True)
        raise typer.Exit(1)

@flags_app.command("set")
def set_flag(name: str, value: str, enabled: bool = True):
    """Set a flag's value."""
    store = FeatureFlagStore()
    flag = store.get(name)
    if flag:
        flag.metadata["value"] = value
        flag.enabled = enabled
        store.set(flag)
        typer.echo(f"Flag '{name}' updated")
    else:
        typer.echo(f"Flag '{name}' not found", err=True)
        raise typer.Exit(1)
```

**Phase 3: YAML Configuration (P0)**
```yaml
# configs/feature_flags.yaml
flags:
  planner_use_rrt:
    flag_type: boolean
    category: planning
    default_value: false
    description: "Use RRT planner instead of A* for path planning"
    owner: "planning-team"
    enabled: true
    rollout_percentage: 10.0
    allowed_contexts: []
    expires_at: null
    metadata:
      value: false
  
  optimizer_minimum_snap_v2:
    flag_type: boolean
    category: optimization
    default_value: false
    description: "Use improved minimum snap optimizer with jerk constraints"
    owner: "optimization-team"
    enabled: false
    rollout_percentage: 0.0
    allowed_contexts: []
    expires_at: null
    metadata:
      value: false
  
  safety_cbf_enhanced:
    flag_type: boolean
    category: safety
    default_value: false
    description: "Use enhanced CBF with adaptive safety margins"
    owner: "safety-team"
    enabled: true
    rollout_percentage: 50.0
    allowed_contexts: []
    expires_at: null
    metadata:
      value: false
  
  swarm_auction_allocation:
    flag_type: boolean
    category: swarm
    default_value: false
    description: "Use auction-based task allocation instead of greedy"
    owner: "swarm-team"
    enabled: false
    rollout_percentage: 0.0
    allowed_contexts: []
    expires_at: null
    metadata:
      value: false
  
  control_mpc_adaptive:
    flag_type: boolean
    category: control
    default_value: false
    description: "Use adaptive MPC with online parameter estimation"
    owner: "control-team"
    enabled: true
    rollout_percentage: 25.0
    allowed_contexts: []
    expires_at: null
    metadata:
      value: false
```

---

## 2. A/B Testing — Gap Analysis

### Current State
- **No A/B testing infrastructure** exists
- The `benchmark.py` module provides performance benchmarking but not statistical A/B testing
- The `evaluation.py` module provides scoring but not experiment comparison
- No variant assignment, no exposure tracking, no statistical significance testing

### What's Needed

| Component | Description | Priority |
|-----------|-------------|----------|
| **Experiment Registry** | Define experiments with variants, traffic allocation, success metrics | P0 |
| **Variant Assignment** | Deterministic, sticky variant assignment via consistent hashing | P0 |
| **Exposure Tracking** | Log every variant assignment for analysis denominators | P0 |
| **Statistical Analysis** | Compute p-values, confidence intervals, and effect sizes | P1 |
| **Guardrail Metrics** | Automatic abort if error rate or latency degrades | P1 |
| **Experiment Dashboard** | CLI or web UI to view experiment results | P2 |

### Recommended Implementation

```python
# src/apex_autopilot_optimization/experimentation/__init__.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import hashlib
import time
from collections import defaultdict

class ExperimentStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"

@dataclass
class ExperimentVariant:
    name: str
    weight: float  # 0-1, proportion of traffic
    config: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Experiment:
    name: str
    description: str
    variants: List[ExperimentVariant]
    success_metric: str
    guardrail_metrics: List[str] = field(default_factory=list)
    status: ExperimentStatus = ExperimentStatus.DRAFT
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    min_sample_size: int = 1000
    max_sample_size: int = 100000
    confidence_level: float = 0.95
    
    def __post_init__(self):
        total_weight = sum(v.weight for v in self.variants)
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Variant weights must sum to 1.0, got {total_weight}")

@dataclass
class ExposureEvent:
    experiment: str
    variant: str
    user_id: str
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)

class ExperimentTracker:
    """Tracks experiment exposures and computes statistics."""
    
    def __init__(self):
        self._experiments: Dict[str, Experiment] = {}
        self._exposures: List[ExposureEvent] = []
        self._metrics: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
    
    def register_experiment(self, experiment: Experiment) -> None:
        """Register a new experiment."""
        self._experiments[experiment.name] = experiment
    
    def assign_variant(self, experiment_name: str, user_id: str, 
                       context: Optional[Dict[str, Any]] = None) -> str:
        """Assign a variant to a user deterministically."""
        exp = self._experiments.get(experiment_name)
        if not exp or exp.status != ExperimentStatus.RUNNING:
            return exp.variants[0].name if exp else "control"
        
        # Consistent hashing for sticky assignment
        bucket = self._hash_bucket(experiment_name, user_id)
        cumulative = 0.0
        for variant in exp.variants:
            cumulative += variant.weight
            if bucket < cumulative:
                # Log exposure
                self._exposures.append(ExposureEvent(
                    experiment=experiment_name,
                    variant=variant.name,
                    user_id=user_id,
                    timestamp=time.time(),
                    context=context or {},
                ))
                return variant.name
        
        return exp.variants[-1].name
    
    def get_variant_config(self, experiment_name: str, variant_name: str) -> Dict[str, Any]:
        """Get the configuration for a specific variant."""
        exp = self._experiments.get(experiment_name)
        if not exp:
            return {}
        for v in exp.variants:
            if v.name == variant_name:
                return v.config
        return {}
    
    def record_metric(self, experiment_name: str, variant_name: str, 
                      metric_name: str, value: float) -> None:
        """Record a metric value for a variant."""
        self._metrics[experiment_name][variant_name].append(value)
    
    def get_results(self, experiment_name: str) -> Dict[str, Any]:
        """Get statistical results for an experiment."""
        exp = self._experiments.get(experiment_name)
        if not exp:
            return {}
        
        results = {
            "experiment": experiment_name,
            "status": exp.status.value,
            "variants": {},
        }
        
        for variant in exp.variants:
            exposures = [e for e in self._exposures 
                        if e.experiment == experiment_name and e.variant == variant.name]
            metrics = self._metrics.get(experiment_name, {}).get(variant.name, [])
            
            results["variants"][variant.name] = {
                "exposure_count": len(exposures),
                "metrics": {
                    metric_name: {
                        "count": len(metrics),
                        "mean": sum(metrics) / len(metrics) if metrics else 0,
                        "min": min(metrics) if metrics else 0,
                        "max": max(metrics) if metrics else 0,
                    }
                    for metric_name in [exp.success_metric] + exp.guardrail_metrics
                }
            }
        
        return results
    
    def check_guardrails(self, experiment_name: str) -> List[str]:
        """Check if any guardrail metrics have been breached."""
        exp = self._experiments.get(experiment_name)
        if not exp:
            return []
        
        breaches = []
        # Implementation would compare guardrail metrics against thresholds
        # and return list of breached guardrails
        
        return breaches
    
    @staticmethod
    def _hash_bucket(experiment_name: str, user_id: str) -> float:
        """Consistent hash for stable variant assignment (0-1)."""
        key = f"{experiment_name}:{user_id}".encode()
        digest = hashlib.sha256(key).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF
```

### Example Usage in Planning Pipeline

```python
# In planning/astar.py or a planner factory
from apex_autopilot_optimization.experimentation import ExperimentTracker

class PlannerFactory:
    def __init__(self, tracker: ExperimentTracker):
        self.tracker = tracker
    
    def create_planner(self, problem: PlanningProblem, user_id: str = ""):
        variant = self.tracker.assign_variant("planner_selection", user_id)
        
        if variant == "rrt":
            from .rrt import RRTPlanner
            return RRTPlanner(problem)
        elif variant == "prm":
            from .prm import PRMPlanner
            return PRMPlanner(problem)
        else:  # control
            from .astar import AStarPlanner
            return AStarPlanner(problem)
```

---

## 3. Experiment Tracking — Gap Analysis

### Current State
- **No experiment tracking** exists
- `benchmark.py` provides one-off benchmark runs but no historical tracking
- `evaluation.py` provides scoring but no experiment comparison
- `observability.py` provides logging but no experiment correlation
- No way to compare algorithm versions over time

### What's Needed

| Component | Description | Priority |
|-----------|-------------|----------|
| **Experiment Run Tracking** | Record every algorithm run with config, metrics, and metadata | P0 |
| **Version Comparison** | Compare results across algorithm versions | P1 |
| **Artifact Storage** | Store trajectories, paths, and other outputs | P1 |
| **Reproducibility** | Capture git commit, dependencies, and config for every run | P0 |
| **Metrics Dashboard** | CLI to view and compare experiment results | P2 |

### Recommended Implementation

```python
# src/apex_autopilot_optimization/experimentation/tracking.py
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json
import time
import subprocess
from pathlib import Path

@dataclass
class ExperimentRun:
    """A single experiment run with full context."""
    run_id: str
    experiment_name: str
    variant: str
    algorithm: str
    config: Dict[str, Any]
    metrics: Dict[str, float]
    git_commit: str
    timestamp: float
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)

class ExperimentTracker:
    """Tracks experiment runs with full reproducibility context."""
    
    def __init__(self, storage_path: str = "experiments/"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._runs: Dict[str, ExperimentRun] = {}
    
    def start_run(self, experiment_name: str, variant: str, 
                  algorithm: str, config: Dict[str, Any]) -> str:
        """Start a new experiment run."""
        run_id = f"{experiment_name}_{variant}_{int(time.time() * 1000)}"
        
        # Capture git commit
        try:
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).parent,
                text=True
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_commit = "unknown"
        
        run = ExperimentRun(
            run_id=run_id,
            experiment_name=experiment_name,
            variant=variant,
            algorithm=algorithm,
            config=config,
            metrics={},
            git_commit=git_commit,
            timestamp=time.time(),
            duration_ms=0.0,
        )
        
        self._runs[run_id] = run
        return run_id
    
    def record_metric(self, run_id: str, metric_name: str, value: float) -> None:
        """Record a metric for a run."""
        if run_id in self._runs:
            self._runs[run_id].metrics[metric_name] = value
    
    def finish_run(self, run_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Finish a run and persist it."""
        if run_id not in self._runs:
            return
        
        run = self._runs[run_id]
        run.duration_ms = (time.time() - run.timestamp) * 1000
        if metadata:
            run.metadata.update(metadata)
        
        # Persist to disk
        run_path = self.storage_path / f"{run_id}.json"
        with open(run_path, "w") as f:
            json.dump(asdict(run), f, indent=2, default=str)
    
    def get_run(self, run_id: str) -> Optional[ExperimentRun]:
        """Get a specific run."""
        return self._runs.get(run_id)
    
    def list_runs(self, experiment_name: Optional[str] = None) -> List[ExperimentRun]:
        """List all runs, optionally filtered by experiment."""
        runs = list(self._runs.values())
        if experiment_name:
            runs = [r for r in runs if r.experiment_name == experiment_name]
        return runs
    
    def compare_runs(self, run_ids: List[str]) -> Dict[str, Any]:
        """Compare multiple runs side by side."""
        runs = [self._runs[rid] for rid in run_ids if rid in self._runs]
        
        if not runs:
            return {}
        
        # Collect all metric names
        all_metrics = set()
        for run in runs:
            all_metrics.update(run.metrics.keys())
        
        comparison = {
            "runs": [asdict(run) for run in runs],
            "metrics_comparison": {},
        }
        
        for metric in all_metrics:
            values = {run.run_id: run.metrics.get(metric) for run in runs}
            comparison["metrics_comparison"][metric] = values
        
        return comparison
    
    def get_best_run(self, experiment_name: str, metric: str, 
                     maximize: bool = True) -> Optional[ExperimentRun]:
        """Get the best run for an experiment by a specific metric."""
        runs = self.list_runs(experiment_name)
        runs = [r for r in runs if metric in r.metrics]
        
        if not runs:
            return None
        
        return max(runs, key=lambda r: r.metrics[metric]) if maximize else min(runs, key=lambda r: r.metrics[metric])
```

---

## 4. Feature Flag Lifecycle Management — Gap Analysis

### Current State
- **No lifecycle management** — no concept of flag states, ownership, or expiration
- No flag audit trail
- No automated cleanup
- No flag health monitoring

### What's Needed

| Component | Description | Priority |
|-----------|-------------|----------|
| **Flag States** | Draft → Active → Deprecated → Archived lifecycle | P0 |
| **Ownership** | Every flag has a named owner | P0 |
| **Expiration** | Automatic flag expiration with warnings | P1 |
| **Audit Trail** | Log all flag changes with actor and timestamp | P1 |
| **Health Monitoring** | Track flag evaluation frequency and stale flags | P2 |
| **Cleanup Automation** | Automated removal of expired flags | P2 |

### Recommended Lifecycle

```
┌─────────┐    ┌────────┐    ┌────────────┐    ┌───────────┐
│  DRAFT  │───▶│ ACTIVE │───▶│ DEPRECATED │───▶│  ARCHIVED │
└─────────┘    └────────┘    └────────────┘    └───────────┘
                    │                              │
                    │         ┌────────┐           │
                    └────────▶│ PAUSED │◀──────────┘
                              └────────┘
```

### Implementation

```python
# src/apex_autopilot_optimization/feature_flags/lifecycle.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import json
from pathlib import Path

class FlagState(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"

@dataclass
class FlagAuditEntry:
    timestamp: str
    actor: str
    action: str
    old_value: Any
    new_value: Any
    reason: str

class FlagLifecycleManager:
    """Manages the full lifecycle of feature flags."""
    
    def __init__(self, store, audit_log_path: str = "configs/flag_audit.jsonl"):
        self.store = store
        self.audit_log_path = Path(audit_log_path)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def transition(self, flag_name: str, new_state: FlagState, 
                   actor: str, reason: str = "") -> bool:
        """Transition a flag to a new state."""
        flag = self.store.get(flag_name)
        if not flag:
            return False
        
        old_state = flag.metadata.get("state", FlagState.DRAFT.value)
        flag.metadata["state"] = new_state.value
        flag.metadata["state_changed_at"] = datetime.utcnow().isoformat()
        flag.metadata["state_changed_by"] = actor
        
        self.store.set(flag)
        self._audit(flag_name, actor, "state_change", old_state, new_state.value, reason)
        
        return True
    
    def deprecate(self, flag_name: str, actor: str, 
                  removal_date: str, reason: str = "") -> bool:
        """Mark a flag as deprecated with a planned removal date."""
        flag = self.store.get(flag_name)
        if not flag:
            return False
        
        flag.metadata["state"] = FlagState.DEPRECATED.value
        flag.metadata["deprecation_date"] = datetime.utcnow().isoformat()
        flag.metadata["planned_removal_date"] = removal_date
        flag.metadata["deprecation_reason"] = reason
        flag.metadata["deprecated_by"] = actor
        
        self.store.set(flag)
        self._audit(flag_name, actor, "deprecate", 
                   FlagState.ACTIVE.value, FlagState.DEPRECATED.value, reason)
        
        return True
    
    def archive(self, flag_name: str, actor: str, reason: str = "") -> bool:
        """Archive a flag (soft delete)."""
        flag = self.store.get(flag_name)
        if not flag:
            return False
        
        flag.metadata["state"] = FlagState.ARCHIVED.value
        flag.metadata["archived_at"] = datetime.utcnow().isoformat()
        flag.metadata["archived_by"] = actor
        flag.metadata["archive_reason"] = reason
        flag.enabled = False
        
        self.store.set(flag)
        self._audit(flag_name, actor, "archive", 
                   FlagState.DEPRECATED.value, FlagState.ARCHIVED.value, reason)
        
        return True
    
    def get_stale_flags(self, days_threshold: int = 30) -> List[Dict[str, Any]]:
        """Get flags that haven't been evaluated recently."""
        stale = []
        for flag in self.store.list_all():
            last_eval = flag.metadata.get("last_evaluated_at")
            if last_eval:
                last_date = datetime.fromisoformat(last_eval)
                if datetime.utcnow() - last_date > timedelta(days=days_threshold):
                    stale.append({
                        "name": flag.name,
                        "last_evaluated": last_eval,
                        "days_since_eval": (datetime.utcnow() - last_date).days,
                    })
        return stale
    
    def get_expired_flags(self) -> List[Dict[str, Any]]:
        """Get flags past their expiration date."""
        expired = []
        for flag in self.store.list_all():
            expires_at = flag.expires_at
            if expires_at:
                expiry_date = datetime.fromisoformat(expires_at)
                if datetime.utcnow() > expiry_date:
                    expired.append({
                        "name": flag.name,
                        "expires_at": expires_at,
                        "days_overdue": (datetime.utcnow() - expiry_date).days,
                    })
        return expired
    
    def _audit(self, flag_name: str, actor: str, action: str,
               old_value: Any, new_value: Any, reason: str) -> None:
        """Write an audit log entry."""
        entry = FlagAuditEntry(
            timestamp=datetime.utcnow().isoformat(),
            actor=actor,
            action=action,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
        
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps({
                "timestamp": entry.timestamp,
                "actor": entry.actor,
                "action": entry.action,
                "old_value": entry.old_value,
                "new_value": entry.new_value,
                "reason": entry.reason,
            }) + "\n")
```

---

## 5. Integration Points

### Where Feature Flags Should Be Integrated

| Module | Flag Integration Point | Use Case |
|--------|----------------------|----------|
| `planning/astar.py` | Planner selection | A/B test A* vs RRT vs PRM |
| `planning/rrt.py` | RRT parameters | Test different step sizes, goal bias |
| `optimization/minimum_snap.py` | Optimizer version | Test v1 vs v2 with jerk constraints |
| `estimation/ekf.py` | Estimator selection | EKF vs UKF vs particle filter |
| `safety/cbf.py` | Safety margin | Test adaptive vs fixed safety margins |
| `control/mpc.py` | Controller parameters | Test different horizons, weights |
| `swarm/task_allocation.py` | Allocation strategy | Greedy vs auction vs market-based |
| `swarm/formation.py` | Formation pattern | Line vs wedge vs hexagon |
| `config_validator.py` | Config validation | Validate flag values at startup |
| `diagnostics.py` | Health checks | Include flag status in health reports |
| `observability.py` | Logging | Log flag evaluations as structured events |
| `benchmark.py` | Benchmarking | Run benchmarks per variant |
| `evaluation.py` | Scoring | Score per variant for comparison |

### Example: Planner Selection with Feature Flags

```python
# src/apex_autopilot_optimization/planning/factory.py
from typing import Optional
from apex_autopilot_optimization.core.types import PlanningProblem, PlanningResult
from apex_autopilot_optimization.feature_flags import FeatureFlagEvaluator

class PlannerFactory:
    """Factory for creating planners based on feature flags."""
    
    def __init__(self, evaluator: FeatureFlagEvaluator):
        self.evaluator = evaluator
    
    def create_planner(self, problem: PlanningProblem, 
                       user_id: str = "default"):
        """Create a planner based on feature flags."""
        context = {"user_id": user_id, "vehicle_type": problem.vehicle_type.name}
        
        if self.evaluator.is_enabled("planner_use_rrt", context):
            from .rrt import RRTPlanner
            return RRTPlanner(problem)
        elif self.evaluator.is_enabled("planner_use_prm", context):
            from .prm import PRMPlanner
            return PRMPlanner(problem)
        elif self.evaluator.is_enabled("planner_use_hybrid_astar", context):
            from .hybrid_astar import HybridAStarPlanner
            return HybridAStarPlanner(problem)
        else:
            from .astar import AStarPlanner
            return AStarPlanner(problem)
```

---

## 6. Testing Strategy

### Unit Tests Needed

```python
# tests/unit/test_feature_flags.py
import pytest
from apex_autopilot_optimization.feature_flags import (
    FeatureFlagStore, FeatureFlagEvaluator, FeatureFlag, FlagType, FlagCategory
)

def test_flag_creation():
    flag = FeatureFlag(
        name="test_flag",
        flag_type=FlagType.BOOLEAN,
        category=FlagCategory.ALGORITHM,
        default_value=False,
    )
    assert flag.name == "test_flag"
    assert flag.default_value is False

def test_flag_evaluation_disabled():
    store = FeatureFlagStore(":memory:")
    evaluator = FeatureFlagEvaluator(store)
    assert evaluator.is_enabled("nonexistent") is False

def test_percentage_rollout_consistency():
    store = FeatureFlagStore(":memory:")
    evaluator = FeatureFlagEvaluator(store)
    
    # Same user should always get same result
    results = [evaluator.is_enabled("test", {"user_id": "user1"}) for _ in range(10)]
    assert all(r == results[0] for r in results)

def test_variant_assignment_determinism():
    tracker = ExperimentTracker()
    exp = Experiment(
        name="test_exp",
        description="test",
        variants=[
            ExperimentVariant(name="control", weight=0.5),
            ExperimentVariant(name="treatment", weight=0.5),
        ],
        success_metric="conversion",
    )
    tracker.register_experiment(exp)
    exp.status = ExperimentStatus.RUNNING
    
    # Same user should always get same variant
    variants = [tracker.assign_variant("test_exp", "user1") for _ in range(10)]
    assert all(v == variants[0] for v in variants)
```

### Integration Tests Needed

```python
# tests/integration/test_flag_integration.py
def test_planner_factory_with_flags():
    """Test that planner factory respects feature flags."""
    store = FeatureFlagStore("tests/fixtures/test_flags.yaml")
    evaluator = FeatureFlagEvaluator(store)
    factory = PlannerFactory(evaluator)
    
    problem = PlanningProblem(
        vehicle_type=VehicleType.UAV_MULTIROTOR,
        start=StateVector(...),
        goal=Waypoint(...),
    )
    
    # With RRT flag enabled, should get RRT planner
    planner = factory.create_planner(problem, user_id="test_user")
    assert isinstance(planner, RRTPlanner)
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Create `feature_flags/` module with core types
- [ ] Implement `FeatureFlagStore` with YAML persistence
- [ ] Implement `FeatureFlagEvaluator` with context-aware rollout
- [ ] Add `configs/feature_flags.yaml` with initial flags
- [ ] Write unit tests for flag system
- [ ] Add CLI commands for flag management

### Phase 2: A/B Testing (Week 3-4)
- [ ] Create `experimentation/` module
- [ ] Implement `ExperimentTracker` with variant assignment
- [ ] Implement exposure tracking
- [ ] Add statistical analysis functions
- [ ] Integrate with planner factory
- [ ] Write unit and integration tests

### Phase 3: Experiment Tracking (Week 5-6)
- [ ] Implement `ExperimentRun` tracking with git commit capture
- [ ] Add artifact storage
- [ ] Implement run comparison
- [ ] Add CLI for viewing experiment results
- [ ] Integrate with benchmark module

### Phase 4: Lifecycle Management (Week 7-8)
- [ ] Implement `FlagLifecycleManager`
- [ ] Add audit logging
- [ ] Implement stale flag detection
- [ ] Add expiration warnings
- [ ] Create cleanup automation script
- [ ] Write tests for lifecycle transitions

### Phase 5: Production Hardening (Week 9-10)
- [ ] Add Redis backend for distributed flag storage
- [ ] Implement flag evaluation metrics
- [ ] Add flag health monitoring
- [ ] Create experiment dashboard (CLI-based)
- [ ] Performance optimization (caching, async)
- [ ] Documentation and runbooks

---

## 8. Dependencies to Add

```toml
# pyproject.toml additions
[project.optional-dependencies]
flags = [
    "redis>=5.0.0,<6.0.0",  # For distributed flag storage
    "pandas>=2.0.0,<3.0.0",  # For experiment analysis
    "scipy>=1.12.0,<2.0.0",  # Already present, for statistical tests
]
```

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Flag evaluation adds latency to planning | High | Use in-memory caching with 30s TTL |
| Flag misconfiguration causes wrong algorithm | High | Validate flags at startup, default to safe values |
| Experiment tracking storage grows unbounded | Medium | Implement retention policy, archive old runs |
| Flag sprawl (too many flags) | Medium | Enforce ownership, expiration, and cleanup |
| Inconsistent variant assignment | Medium | Use consistent hashing, test thoroughly |
| Flag changes not propagated to all nodes | Medium | Use Redis pub/sub or polling with short TTL |

---

## 10. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Flag evaluation latency | < 1ms | Benchmark p99 |
| Flag propagation delay | < 30s | Time from set to visible |
| Experiment tracking overhead | < 5% | Compare with/without tracking |
| Flag cleanup compliance | 100% | % of expired flags removed |
| Variant assignment consistency | 100% | Same user → same variant |
| Test coverage for flag system | > 90% | pytest-cov |

---

## References

1. LaunchDarkly Python SDK: https://launchdarkly.com/docs/sdk/server-side/python
2. Unleash Python SDK: https://github.com/Unleash/unleash-python-sdk
3. Flagsmith Python Client: https://github.com/Flagsmith/flagsmith-python-client
4. Feature Flag Lifecycle Best Practices: https://beefed.ai/en/feature-flag-governance-lifecycle-best-practices
5. A/B Testing in Python: https://python.codeguides.io/enterprise-delivery/a-b-testing-and-experimentation
6. GrowthBook Open Source: https://github.com/growthbook/growthbook
