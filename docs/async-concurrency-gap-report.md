# Async/Concurrency Gap Report — apex-autopilot-optimization

**Date:** 2026-10-04  
**Scope:** Full source tree (`src/apex_autopilot_optimization/`)  
**Method:** Static analysis of all 20 modules + tests + README + pyproject.toml

---

## Executive Summary

The project has **zero async support, zero concurrency primitives, and zero parallel execution**. Every module is purely synchronous and single-threaded. The codebase is CPU-bound (NumPy/SciPy numerical computing) with no I/O operations that would benefit from async/await. However, there are significant opportunities for **parallel planning**, **concurrent benchmarking**, and **thread-safe state management** that would improve performance and robustness.

---

## 1. What Async Support Is Needed

### 1.1 Current State

| Aspect | Status |
|--------|--------|
| `async`/`await` keywords | **0 occurrences** in entire source tree |
| `asyncio` import | **0 occurrences** |
| `threading` module | **0 occurrences** |
| `concurrent.futures` | **0 occurrences** |
| `multiprocessing` | **0 occurrences** |
| `Lock`/`Semaphore`/`RLock` | **0 occurrences** |
| `pytest-asyncio` | Listed in `[project.optional-dependencies] dev` only; `asyncio_mode = "auto"` set in pytest config but no async tests exist |

### 1.2 Where Async Would Help

| Module | Use Case | Priority |
|--------|----------|----------|
| `benchmark.py` — `BenchmarkRunner.run()` | Run multiple benchmark iterations concurrently to reduce wall-clock time | **Medium** |
| `evaluation.py` — `EvaluationRunner.run()` | Evaluate multiple metrics in parallel | **Low** |
| `planning/` (all 4 planners) | Run multiple planners concurrently, return best/fastest result | **High** |
| `swarm/task_allocation.py` | Parallel task-to-agent matching for large swarms | **Medium** |
| `observability.py` — `MetricCollector` | Thread-safe metric collection from multiple sources | **High** |
| `estimation/ekf.py` — `EKFEstimator` | Thread-safe state estimation when predict/update called from different threads | **High** |

### 1.3 Where Async Is NOT Needed

- **No I/O-bound operations**: No network calls, no file I/O, no database access, no message queue consumption
- **No event loop**: No server, no WebSocket, no long-running service
- **Pure computation**: All modules are CPU-bound numerical algorithms (NumPy/SciPy)

**Verdict:** Traditional `async/await` (coroutine-based async) provides **minimal value** for this codebase. The real need is **thread-based and process-based parallelism** for CPU-bound work.

---

## 2. How to Implement Concurrent Planning

### 2.1 Current Architecture

All four planners share the same interface:
```python
class AStarPlanner:
    def plan(self, problem: PlanningProblem) -> PlanningResult: ...
```

They are called sequentially:
```python
planner = AStarPlanner()
result = planner.plan(problem)  # Blocks until complete
```

### 2.2 Proposed: Parallel Planner Execution

**Pattern:** Race multiple planners concurrently, return the first successful result (or best result).

```python
# New module: planning/parallel.py
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Callable

class ParallelPlanner:
    """Runs multiple planners concurrently and returns the best result."""
    
    def __init__(self, planners: list[Planner], strategy: str = "first_success"):
        self.planners = planners
        self.strategy = strategy  # "first_success", "best_cost", "best_time"
    
    def plan(self, problem: PlanningProblem) -> PlanningResult:
        with ThreadPoolExecutor(max_workers=len(self.planners)) as executor:
            futures = {
                executor.submit(p.plan, problem): p 
                for p in self.planners
            }
            # Collect results as they complete
            results = []
            for future in as_completed(futures):
                result = future.result()
                if result.success and self.strategy == "first_success":
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    return result
                results.append(result)
            
            if not results:
                return PlanningResult(success=False, message="All planners failed")
            
            # Return best by cost
            successful = [r for r in results if r.success]
            if not successful:
                return PlanningResult(success=False, message="All planners failed")
            return min(successful, key=lambda r: r.cost)
```

### 2.3 Proposed: Concurrent Benchmark Suite

```python
# benchmark.py enhancement
class ConcurrentBenchmarkRunner:
    def run_suite_parallel(self, configs: list[BenchmarkConfig]) -> dict[str, BenchmarkResult]:
        with ThreadPoolExecutor(max_workers=min(len(configs), 8)) as executor:
            futures = {
                executor.submit(self.run, config): config.name 
                for config in configs
            }
            results = {}
            for future in as_completed(futures):
                name = futures[future]
                results[name] = future.result()
            return results
```

### 2.4 Proposed: Parallel Evaluation

```python
# evaluation.py enhancement
class ParallelEvaluationRunner:
    def run_parallel(self, configs: list[EvaluationConfig]) -> list[EvaluationResult]:
        with ThreadPoolExecutor(max_workers=min(len(configs), 8)) as executor:
            futures = [executor.submit(self._run_single, c) for c in configs]
            return [f.result() for f in futures]
```

---

## 3. What Parallel Execution Patterns to Use

### 3.1 Pattern Selection Matrix

| Pattern | Use Case | Module | Rationale |
|---------|----------|--------|-----------|
| **ThreadPoolExecutor** | Parallel planning (race planners) | `planning/parallel.py` | Planners are CPU-bound but release GIL during NumPy ops; threads are lightweight |
| **ProcessPoolExecutor** | Heavy computation isolation | `benchmark.py` | True parallelism for CPU-intensive benchmarks; avoids GIL contention |
| **ThreadPoolExecutor** | Concurrent metric collection | `observability.py` | Multiple threads may report metrics simultaneously |
| **ThreadPoolExecutor** | Parallel task allocation | `swarm/task_allocation.py` | Independent agent-task matching can be parallelized |
| **asyncio.gather** | Future: async I/O (network, file) | N/A (no I/O today) | Not needed now; add when I/O is introduced |

### 3.2 Recommended Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Client Code                        │
├─────────────────────────────────────────────────────┤
│  ParallelPlanner                                    │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐  │
│  │ ThreadPool  │ │ ThreadPool  │ │ ThreadPool   │  │
│  │ AStar.plan  │ │ RRT.plan    │ │ PRM.plan     │  │
│  └─────────────┘ └─────────────┘ └──────────────┘  │
│         │                │               │          │
│         └────────────────┼───────────────┘          │
│                          ▼                          │
│              BestResult / FirstSuccess               │
└─────────────────────────────────────────────────────┘
```

### 3.3 GIL Considerations

- **NumPy releases the GIL** during most array operations → `ThreadPoolExecutor` is effective for parallel planning
- **Pure Python loops** (e.g., RRT tree search, A* heap operations) hold the GIL → `ProcessPoolExecutor` may be needed for true parallelism
- **Recommendation:** Start with `ThreadPoolExecutor` (simpler, shared memory); profile; switch to `ProcessPoolExecutor` if GIL contention is measured

---

## 4. How to Maintain Thread Safety

### 4.1 Current Thread Safety Issues

| Module | Issue | Severity |
|--------|-------|----------|
| `estimation/ekf.py` — `EKFEstimator` | `_state` and `_covariance` are mutable; `predict()` and `update()` are not atomic; concurrent calls will corrupt state | **Critical** |
| `observability.py` — `MetricCollector` | `_metrics` dict is mutated by `increment()`, `gauge()`, `histogram()` without synchronization; lost updates possible | **High** |
| `swarm/task_allocation.py` — `TaskAllocator` | Mutates `Task.assigned_agent` and `Agent.assigned_tasks` during allocation; not safe for concurrent access to shared task/agent lists | **Medium** |
| `planning/rrt.py` — `RRTPlanner` | Uses `np.random` without seeding; parallel runs produce different results (not a safety issue but a reproducibility issue) | **Low** |
| `planning/prm.py` — `PRMPlanner` | Same `np.random` issue as RRT | **Low** |
| `benchmark.py` — `EvolutionTracker` | `self.generations` list mutated by `record_generation()` without lock | **Medium** |

### 4.2 Thread Safety Solutions

#### EKF Estimator — Add Lock

```python
import threading

class EKFEstimator:
    def __init__(self, config: EKFConfig | None = None) -> None:
        self.config = config or EKFConfig()
        self._state = np.zeros(self.config.state_dim, dtype=np.float64)
        self._covariance = np.eye(self.config.state_dim, dtype=np.float64)
        self._lock = threading.RLock()  # <-- ADD
    
    def predict(self, dt: float) -> None:
        with self._lock:  # <-- ADD
            # ... existing predict logic ...
    
    def update(self, measurement: NDArray[np.float64]) -> None:
        with self._lock:  # <-- ADD
            # ... existing update logic ...
    
    def get_state(self) -> StateVector:
        with self._lock:  # <-- ADD
            # ... existing get_state logic ...
```

#### MetricCollector — Add Lock

```python
import threading

class MetricCollector:
    def __init__(self) -> None:
        self._metrics: dict[str, Any] = {}
        self._lock = threading.Lock()  # <-- ADD
    
    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:  # <-- ADD
            if name not in self._metrics:
                self._metrics[name] = 0
            self._metrics[name] += value
    
    def gauge(self, name: str, value: float) -> None:
        with self._lock:  # <-- ADD
            self._metrics[name] = value
    
    def histogram(self, name: str, value: float) -> None:
        with self._lock:  # <-- ADD
            if name not in self._metrics:
                self._metrics[name] = []
            if not isinstance(self._metrics[name], list):
                self._metrics[name] = []
            self._metrics[name].append(value)
    
    def get_metrics(self) -> dict[str, Any]:
        with self._lock:  # <-- ADD
            return dict(self._metrics)
```

#### TaskAllocator — Make Stateless

```python
class TaskAllocator:
    def allocate(
        self,
        agents: list[Agent],
        tasks: list[Task],
    ) -> list[tuple[int, int]]:
        # Don't mutate input objects; return new assignment data
        # ... existing logic but without mutating task.assigned_agent ...
```

#### Planners — Add Seed Control

```python
@dataclass(frozen=True, slots=True)
class RRTConfig:
    max_iterations: int = 1000
    step_size: float = 1.0
    goal_sample_rate: float = 0.1
    goal_tolerance: float = 1.0
    seed: int | None = None  # <-- ADD for reproducibility
```

### 4.3 Thread Safety Checklist

- [ ] Add `threading.RLock()` to `EKFEstimator` (predict/update/get_state)
- [ ] Add `threading.Lock()` to `MetricCollector` (all mutation methods)
- [ ] Add `threading.Lock()` to `EvolutionTracker` (record_generation)
- [ ] Make `TaskAllocator.allocate()` stateless (don't mutate inputs)
- [ ] Add `seed` parameter to `RRTConfig` and `PRMConfig`
- [ ] Add `seed` parameter to `AStarConfig` and `HybridAStarConfig` (for tie-breaking)
- [ ] Document thread-safety guarantees in each module's docstring
- [ ] Add concurrency tests (test parallel planning, test thread-safe EKF)

---

## 5. Implementation Roadmap

### Phase 1: Thread Safety (Critical)
1. Add locks to `EKFEstimator`, `MetricCollector`, `EvolutionTracker`
2. Make `TaskAllocator` stateless
3. Add seed parameters to all planner configs
4. Write concurrency tests

### Phase 2: Parallel Planning (High Value)
1. Create `planning/parallel.py` with `ParallelPlanner`
2. Implement "first success" strategy (race planners, return first)
3. Implement "best cost" strategy (run all, return cheapest)
4. Add `planning/__init__.py` exports

### Phase 3: Concurrent Benchmarking (Medium Value)
1. Add `ConcurrentBenchmarkRunner` to `benchmark.py`
2. Add parallel evaluation to `evaluation.py`
3. Profile to determine if `ProcessPoolExecutor` is needed

### Phase 4: Async Foundation (Future)
1. Add `asyncio` as a main dependency (not just dev)
2. Create async wrappers for I/O-bound operations when they appear
3. Add `pytest-asyncio` to main dependencies when async tests exist

---

## 6. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| GIL contention limits ThreadPool speedup | Profile first; use ProcessPoolExecutor for pure-Python loops |
| Deadlocks from nested locks | Use `RLock` (reentrant) everywhere; document lock ordering |
| Shared mutable state corruption | Minimize shared state; prefer immutable data structures |
| Reproducibility loss from parallel random sampling | Add explicit seed parameters to all stochastic planners |
| Over-engineering for current scale | Start with ThreadPoolExecutor; add complexity only when measured |

---

## 7. Summary

| Category | Current State | Gap | Priority |
|----------|--------------|-----|----------|
| Async/await | None | Not needed (no I/O) | N/A |
| Concurrent planning | None | High value for racing planners | **High** |
| Parallel benchmarking | Sequential only | Medium value | **Medium** |
| Thread safety | None | Critical for any concurrency | **Critical** |
| Reproducibility | Unseeded RNG | Affects testing/debugging | **Medium** |
| Async tests | None | No async code to test | N/A |

**Bottom line:** The project needs **thread safety fixes first**, then **parallel planning infrastructure**. Traditional `async/await` is not applicable to this CPU-bound numerical computing codebase. The recommended path is `ThreadPoolExecutor` for parallel planning and benchmarking, with `ProcessPoolExecutor` as a fallback if GIL contention is measured.
