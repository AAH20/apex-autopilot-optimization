# Plugin / Extensibility System Gap Analysis
**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Status:** Gap Report — No Plugin Architecture Exists

---

## Executive Summary

The apex-autopilot-optimization project contains 20 modules implementing 11 core algorithms (4 planners, 1 optimizer, 1 estimator, 2 swarm, 1 safety, 1 controller, 1 core types) with 365 passing tests. **The project has zero plugin infrastructure**: no abstract interfaces, no registration mechanism, no discovery system, no entry points, and no third-party extension path. Every algorithm is a concrete class with no contract enforcement, no lifecycle hooks, and no way to swap, extend, or override implementations at runtime.

This report identifies four critical gaps and provides specific, actionable recommendations drawing on established Python plugin patterns (Pluggy, Stevedore, `importlib.metadata` entry points).

---

## Gap 1: No Abstract Interfaces (Plugin Contracts)

### Current State

Every algorithm is a **standalone concrete class** with no shared abstract base class:

| Category | Concrete Class | Signature |
|----------|---------------|-----------|
| Planning | `AStarPlanner` | `plan(problem: PlanningProblem) -> PlanningResult` |
| Planning | `RRTPlanner` | `plan(problem: PlanningProblem) -> PlanningResult` |
| Planning | `PRMPlanner` | `plan(problem: PlanningProblem) -> PlanningResult` |
| Planning | `HybridAStarPlanner` | `plan(problem: PlanningProblem) -> PlanningResult` |
| Optimization | `MinimumSnapOptimizer` | `optimize(problem: PlanningProblem) -> PlanningResult` |
| Estimation | `EKFEstimator` | `predict(dt)` / `update(measurement)` |
| Control | `MPCController` | `compute_control(state, target) -> ControlInput` |
| Safety | `CBFFilter` | `filter(state, control, obstacles) -> ControlInput` |

The signatures are **coincidentally similar** (all planners happen to use `plan(problem) -> PlanningResult`) but this is **not enforced by any interface**. A third-party developer has no contract to code against.

### What Is Needed

Abstract base classes (ABCs) defining the plugin contracts:

```python
# planning/base.py
from abc import ABC, abstractmethod
from apex_autopilot_optimization.core.types import PlanningProblem, PlanningResult

class Planner(ABC):
    """Abstract base class for all path planners."""
    
    @abstractmethod
    def plan(self, problem: PlanningProblem) -> PlanningResult:
        """Plan a path from start to goal."""
        ...
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique planner identifier for registration."""
        ...

# optimization/base.py
class Optimizer(ABC):
    @abstractmethod
    def optimize(self, problem: PlanningProblem) -> PlanningResult:
        ...

# estimation/base.py
class Estimator(ABC):
    @abstractmethod
    def predict(self, dt: float) -> None: ...
    
    @abstractmethod
    def update(self, measurement: NDArray) -> None: ...
    
    @abstractmethod
    def get_state(self) -> StateVector: ...

# control/base.py
class Controller(ABC):
    @abstractmethod
    def compute_control(self, state: StateVector, target: StateVector) -> ControlInput: ...

# safety/base.py
class SafetyFilter(ABC):
    @abstractmethod
    def filter(self, state: StateVector, control: ControlInput, obstacles: list[dict]) -> ControlInput: ...
```

### Impact

- **Without this**: Third parties cannot write compatible plugins; there is no type safety; static analysis (mypy strict is enabled) cannot verify plugin correctness.
- **With this**: Clear contracts, IDE autocompletion, type-checked plugin development, testability.

---

## Gap 2: No Registration / Discovery Mechanism

### Current State

All algorithm classes are **hardcoded imports** in their package `__init__.py`:

```python
# planning/__init__.py
from apex_autopilot_optimization.planning.astar import AStarConfig, AStarPlanner
from apex_autopilot_optimization.planning.hybrid_astar import HybridAStarConfig, HybridAStarPlanner
# ... explicit imports only
```

There is **no registry**, **no dynamic discovery**, and **no way to enumerate available planners**. Users must know exact class names and import paths.

### Research: Python Plugin Discovery Patterns

| Mechanism | Used By | Pros | Cons |
|-----------|---------|------|------|
| `importlib.metadata` entry points | pytest (via pluggy), stevedore, many others | Standard lib, pip-installable, auto-discovery | Requires packaging; all-or-nothing discovery |
| Pluggy (`@hookspec`/`@hookimpl`) | pytest, tox | Decorator-based, ordering, result collection, error isolation | Additional dependency (~100 LOC) |
| Stevedore | OpenStack | Entry-point based, namespace isolation, lazy loading | Additional dependency |
| Manual registry (dict-based) | Many projects | Zero dependencies, full control | No auto-discovery |

### Recommended Approach: Hybrid Entry Points + Lightweight Registry

**Layer 1 — Entry Points (discovery)**: Use `importlib.metadata` entry points (standard library, zero new dependencies) for pip-installed plugin auto-discovery.

Add to `pyproject.toml`:

```toml
[project.entry-points."apex_autopilot.planners"]
astar = "apex_autopilot_optimization.planning.astar:AStarPlanner"
rrt = "apex_autopilot_optimization.planning.rrt:RRTPlanner"
prm = "apex_autopilot_optimization.planning.prm:PRMPlanner"
hybrid_astar = "apex_autopilot_optimization.planning.hybrid_astar:HybridAStarPlanner"

[project.entry-points."apex_autopilot.optimizers"]
minimum_snap = "apex_autopilot_optimization.optimization.minimum_snap:MinimumSnapOptimizer"

[project.entry-points."apex_autopilot.estimators"]
ekf = "apex_autopilot_optimization.estimation.ekf:EKFEstimator"

[project.entry-points."apex_autopilot.controllers"]
mpc = "apex_autopilot_optimization.control.mp:MPCController"

[project.entry-points."apex_autopilot.safety_filters"]
cbf = "apex_autopilot_optimization.safety.cbf:CBFFilter"
```

Third-party plugins register their own entry points in their `pyproject.toml`:

```toml
[project.entry-points."apex_autopilot.planners"]
my_custom_planner = "my_package.planning:MyCustomPlanner"
```

**Layer 2 — Runtime Registry (lookup)**: A lightweight registry that loads entry points and provides lookup by name:

```python
# plugin/registry.py
from importlib.metadata import entry_points

PLUGIN_GROUPS = {
    "planners": "apex_autopilot.planners",
    "optimizers": "apex_autopilot.optimizers",
    "estimators": "apex_autopilot.estimators",
    "controllers": "apex_autopilot.controllers",
    "safety_filters": "apex_autopilot.safety_filters",
}

class PluginRegistry:
    """Runtime plugin discovery and lookup."""
    
    def __init__(self):
        self._plugins: dict[str, dict[str, type]] = {}
    
    def discover(self, group: str) -> dict[str, type]:
        """Discover all plugins in a group."""
        if group in self._plugins:
            return self._plugins[group]
        
        plugins = {}
        eps = entry_points(group=PLUGIN_GROUPS[group])
        for ep in eps:
            try:
                plugins[ep.name] = ep.load()
            except Exception:
                # Log and continue — one bad plugin shouldn't break discovery
                continue
        
        self._plugins[group] = plugins
        return plugins
    
    def get(self, group: str, name: str):
        """Get a plugin by name."""
        return self.discover(group)[name]
    
    def names(self, group: str) -> list[str]:
        """List all available plugin names in a group."""
        return list(self.discover(group).keys())
```

**Layer 3 — Registration API (manual)**: For plugins distributed outside pip (local modules):

```python
# plugin/manager.py
class PluginManager:
    def register(self, group: str, name: str, plugin_class: type) -> None:
        """Manually register a plugin at runtime."""
        # Validate the plugin implements the correct ABC
        ...
```

### Impact

- **Without this**: No way to enumerate or discover available algorithms; users hardcode imports.
- **With this**: Auto-discovery via pip install, runtime lookup by name, manual registration for development, lazy loading.

---

## Gap 3: No Lifecycle Hooks / Extension Points

### Current State

Algorithms are **stateless function-like objects** — you instantiate them, call one method, get a result. There are no hooks for:

- Pre/post-processing (e.g., transform problem before planning)
- Validation (e.g., check problem feasibility before running)
- Events (e.g., notify on planning success/failure)
- Composition (e.g., chain planner -> optimizer -> safety filter)

### What Is Needed

A pipeline/hook system for extension points. **Recommendation: Use a lightweight hook approach rather than full Pluggy**, since the project's needs are simpler (pipeline composition, not pytest's multi-plugin result collection).

**Option A (Recommended): Pipeline Pattern with Hooks**

```python
# pipeline/base.py
@dataclass
class PipelineContext:
    problem: PlanningProblem
    result: PlanningResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

class PipelineHook(ABC):
    @abstractmethod
    def before_planning(self, context: PipelineContext) -> None: ...
    
    @abstractmethod
    def after_planning(self, context: PipelineContext) -> None: ...

class Pipeline:
    def __init__(self, planner, optimizer, safety_filter):
        self.planner = planner
        self.optimizer = optimizer
        self.safety_filter = safety_filter
        self.hooks: list[PipelineHook] = []
    
    def add_hook(self, hook: PipelineHook) -> None:
        self.hooks.append(hook)
    
    def execute(self, problem: PlanningProblem) -> PlanningResult:
        ctx = PipelineContext(problem=problem)
        for hook in self.hooks:
            hook.before_planning(ctx)
        
        plan_result = self.planner.plan(problem)
        ctx.result = plan_result
        
        for hook in self.hooks:
            hook.after_planning(ctx)
        
        return plan_result
```

**Option B (Alternative): Pluggy for Full Hook System**

If the project grows to need multiple plugins contributing to the same operation (e.g., multiple cost functions, multiple validators), adopt Pluggy:

```python
import pluggy

hookspec = pluggy.HookspecMarker("apex_autopilot")
hookimpl = pluggy.HookimplMarker("apex_autopilot")

@hookspec
def before_planning(problem: PlanningProblem) -> PlanningProblem:
    """Hook: transform/validate problem before planning."""

@hookspec
def cost_function(state: StateVector) -> float:
    """Hook: contribute to cost computation."""
```

**Recommendation**: Start with Option A (Pipeline + hooks) for now. Migrate to Option B (Pluggy) only if multiple plugins need to contribute to the same operation. This keeps dependencies minimal.

### Impact

- **Without this**: No way to add cross-cutting concerns (logging, metrics, validation, caching) without modifying core algorithm code.
- **With this**: Clean separation of concerns, testable extensions, composable pipeline.

---

## Gap 4: No Backward Compatibility Strategy

### Current State

The project is at **v0.1.0** (Alpha) with no published stable API. This is both a risk (breaking changes will happen) and an opportunity (establish the plugin interface now before external users depend on internal APIs).

### What Is Needed

**1. Versioned Plugin API**

```python
# plugin/api.py
PLUGIN_API_VERSION = 1

class PluginBase:
    """Base class for all plugins. Versioned for compatibility."""
    
    PLUGIN_API_VERSION = PLUGIN_API_VERSION
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Validate API version on registration
        if hasattr(cls, 'PLUGIN_API_VERSION') and cls.PLUGIN_API_VERSION > PLUGIN_API_VERSION:
            raise PluginIncompatibleError(
                f"{cls.__name__} requires API v{cls.PLUGIN_API_VERSION}, "
                f"but runtime supports v{PLUGIN_API_VERSION}"
            )
```

**2. Deprecation Policy**

- Use `warnings.warn(..., DeprecationWarning, stacklevel=2)` for deprecated interfaces
- Maintain a `CHANGELOG.md` with semantic versioning
- Mark experimental APIs with `@experimental` decorator

**3. Stable vs. Experimental Split**

```python
# Stable API (guaranteed backward-compatible within major version)
apex_autopilot_optimization.planning.base.Planner
apex_autopilot_optimization.optimization.base.Optimizer
apex_autopilot_optimization.plugin.registry.PluginRegistry

# Experimental API (may change without notice)
apex_autopilot_optimization.control.*  # Not yet stable
apex_autopilot_optimization.safety.*   # Not yet stable
```

---

## Summary: Priority Recommendations

| Priority | Gap | Recommendation | Effort |
|----------|-----|----------------|--------|
| **P0** | No abstract interfaces | Create ABCs for Planner, Optimizer, Estimator, Controller, SafetyFilter | Low — refactoring existing classes to inherit ABCs |
| **P0** | No registration | Add `PluginRegistry` using `importlib.metadata` entry points | Low — ~100 lines, stdlib only |
| **P1** | No discovery | Add entry points to `pyproject.toml` for all 7 algorithm classes | Low — pyproject.toml metadata only |
| **P1** | Third-party path | Implement `PluginManager.register()` for manual registration + docs | Medium — needs validation logic |
| **P2** | No lifecycle hooks | Add Pipeline pattern with before/after hooks | Medium — new subsystem |
| **P2** | No compat strategy | Add versioned API + deprecation policy | Low — mostly documentation + warnings |
| **P3** | Full hook system | Adopt Pluggy if multi-plugin composition needed | High — new dependency, API redesign |

### Recommended Implementation Order

1. **Create ABCs** (`planning/base.py`, `optimization/base.py`, etc.) — refactoring existing classes to inherit from them (backward-compatible: existing code continues to work).
2. **Add entry points** to `pyproject.toml` — zero code change, just metadata.
3. **Implement `PluginRegistry`** — new module, no changes to existing code.
4. **Implement `PluginManager`** — new module, supports manual registration.
5. **Write plugin development guide** — docs on how to write a third-party plugin.
6. **Add Pipeline + hooks** — optional, if cross-cutting concerns emerge.
7. **Consider Pluggy** — only if the hook system grows beyond simple pipeline composition.

### Third-Party Plugin Example (Target State)

After implementation, a third-party developer should be able to:

```python
# my_custom_planner.py
from apex_autopilot_optimization.planning.base import Planner
from apex_autopilot_optimization.core.types import PlanningProblem, PlanningResult

class MyCustomPlanner(Planner):
    @property
    def name(self) -> str:
        return "my_custom_planner"
    
    def plan(self, problem: PlanningProblem) -> PlanningResult:
        # Custom implementation
        ...
```

```toml
# their pyproject.toml
[project.entry-points."apex_autopilot.planners"]
my_custom_planner = "my_custom_planner:MyCustomPlanner"
```

```python
# user code
from apex_autopilot_optimization.plugin.registry import PluginRegistry

registry = PluginRegistry()
planner_class = registry.get("planners", "my_custom_planner")
planner = planner_class()
result = planner.plan(problem)
```

---

## Appendix: Files That Need Changes

| File | Change |
|------|--------|
| `src/apex_autopilot_optimization/planning/base.py` | **NEW** — `Planner` ABC |
| `src/apex_autopilot_optimization/optimization/base.py` | **NEW** — `Optimizer` ABC |
| `src/apex_autopilot_optimization/estimation/base.py` | **NEW** — `Estimator` ABC |
| `src/apex_autopilot_optimization/control/base.py` | **NEW** — `Controller` ABC |
| `src/apex_autopilot_optimization/safety/base.py` | **NEW** — `SafetyFilter` ABC |
| `src/apex_autopilot_optimization/plugin/__init__.py` | **NEW** — plugin package |
| `src/apex_autopilot_optimization/plugin/registry.py` | **NEW** — `PluginRegistry` |
| `src/apex_autopilot_optimization/plugin/manager.py` | **NEW** — `PluginManager` |
| `src/apex_autopilot_optimization/planning/astar.py` | MODIFY — inherit `Planner` ABC |
| `src/apex_autopilot_optimization/planning/rrt.py` | MODIFY — inherit `Planner` ABC |
| `src/apex_autopilot_optimization/planning/prm.py` | MODIFY — inherit `Planner` ABC |
| `src/apex_autopilot_optimization/planning/hybrid_astar.py` | MODIFY — inherit `Planner` ABC |
| `src/apex_autopilot_optimization/optimization/minimum_snap.py` | MODIFY — inherit `Optimizer` ABC |
| `src/apex_autopilot_optimization/estimation/ekf.py` | MODIFY — inherit `Estimator` ABC |
| `src/apex_autopilot_optimization/control/mpc.py` | MODIFY — inherit `Controller` ABC |
| `src/apex_autopilot_optimization/safety/cbf.py` | MODIFY — inherit `SafetyFilter` ABC |
| `pyproject.toml` | MODIFY — add `[project.entry-points.*]` sections |
| `docs/architecture/plugin-development-guide.md` | **NEW** — third-party plugin author guide |
