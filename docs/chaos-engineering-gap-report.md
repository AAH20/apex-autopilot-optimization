# Chaos Engineering & Fault Injection Gap Report

**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Scope:** All 20 source modules, 20 test files, architecture docs  
**Verdict:** Zero chaos engineering, zero fault injection, zero resilience testing

---

## Executive Summary

The project is a pure algorithmic library (planners, optimizers, estimators, controllers) with **no runtime infrastructure** for handling failure. Every module is deterministic, stateless (except EKF), and has no concept of partial failure, degradation, or recovery. Tests are 100% happy-path — not a single test exercises an error condition, edge case, or failure mode.

---

## 1. What Chaos Engineering Is Needed

### 1.1 Current State

| Aspect | Status |
|--------|--------|
| Fault injection framework | ❌ None |
| Failure mode catalog | ❌ None |
| Steady-state hypotheses | ❌ None |
| Game day / chaos experiments | ❌ None |
| Resilience test suite | ❌ None |
| Degradation strategies | ❌ None |
| Recovery mechanisms | ❌ None |

### 1.2 Needed Chaos Engineering Areas

#### A. Numerical Chaos (Highest Priority)
The EKF estimator (`estimation/ekf.py`) is the most critical target:
- **Covariance blow-up**: No regularization when covariance matrix becomes non-positive-definite
- **Numerical instability**: Joseph form is used but no eigenvalue clamping or condition number checks
- **Divergence**: No innovation monitoring or divergence detection
- **No reset-on-failure**: `reset()` exists but nothing triggers it automatically

#### B. Planning Failure Chaos
All four planners (`astar.py`, `rrt.py`, `prm.py`, `hybrid_astar.py`):
- **Infinite search**: `max_iterations` is a count limit, not a time limit — a planner can hang
- **Memory exhaustion**: No node count limits (RRT/PRM can grow unboundedly)
- **No partial failure**: Planners return `success=False` but no partial result or diagnostic info
- **No fallback**: If A* fails, there is no automatic fallback to RRT or PRM

#### C. Control Instability Chaos
MPC controller (`control/mpc.py`):
- **Simplified PD control**: Not real MPC — no constraint handling, no QP solver
- **No stability guarantees**: No Lyapunov analysis, no boundedness checks
- **No saturation recovery**: Clipping is applied but no anti-windup

#### D. Safety Filter Bypass Chaos
CBF filter (`safety/cbf.py`):
- **Binary safe/unsafe**: Only checks `h > 0` — no graduated response
- **No fault detection**: If obstacle data is corrupt or missing, filter silently passes through
- **No redundancy**: Single filter with no backup

#### E. Swarm Coordination Chaos
Task allocation (`swarm/task_allocation.py`) and formation (`swarm/formation.py`):
- **Agent failure**: No handling of agents dropping out mid-mission
- **Communication loss**: `communication_range` exists but no handling of range violations
- **Task starvation**: Greedy allocator can starve low-priority tasks indefinitely

#### F. System-Level Chaos
- **No circuit breakers**: A failing module will be called repeatedly with no backoff
- **No bulkheads**: One module's failure can consume all resources
- **No timeouts**: No wall-clock time limits on any operation
- **No health degradation**: `HealthCheck.check()` always returns `"healthy"` — it checks nothing

---

## 2. How to Implement Fault Injection

### 2.1 Architecture: Fault Injection Layer

Create a new `src/apex_autopilot_optimization/chaos/` package:

```
chaos/
├── __init__.py              # Public API
├── injector.py              # Core fault injection engine
├── faults.py                # Fault type definitions
├── strategies.py            # Injection strategies (random, targeted, scheduled)
├── experiment.py            # Chaos experiment orchestrator
└── recovery.py              # Recovery and degradation management
```

### 2.2 Fault Types to Implement

```python
# chaos/faults.py
class FaultType(Enum):
    # Numerical faults
    COVARIANCE_CORRUPTION = auto()      # Inject noise into EKF covariance
    STATE_DIVERGENCE = auto()           # Force EKF state to diverge
    MEASUREMENT_DROP = auto()           # Drop sensor measurements
    MEASUREMENT_NOISE = auto()          # Inject Gaussian noise into measurements
    
    # Planning faults
    NODE_EXPLOSION = auto()             # Force unbounded node growth
    HEURISTIC_CORRUPTION = auto()       # Corrupt heuristic values
    COLLISION_CHECK_BYPASS = auto()     # Disable collision checking
    TIMEOUT = auto()                    # Exceed time budget
    
    # Control faults
    CONTROL_SATURATION = auto()         # Force control outputs to limits
    TARGET_JUMP = auto()                # Abrupt target state changes
    STATE_DELAY = auto()                # Delay state feedback
    
    # Safety faults
    OBSTACLE_DATA_CORRUPTION = auto()   # Corrupt obstacle positions
    SAFETY_MARGIN_VIOLATION = auto()    # Force safety margin to zero
    CBF_BYPASS = auto()                 # Disable safety filter
    
    # Swarm faults
    AGENT_DROP = auto()                 # Remove agent mid-allocation
    COMMUNICATION_LOSS = auto()         # Exceed communication range
    TASK_CORRUPTION = auto()            # Corrupt task priorities
    
    # System faults
    MEMORY_PRESSURE = auto()            # Simulate memory exhaustion
    CPU_THROTTLE = auto()               # Simulate CPU contention
    CLOCK_SKEW = auto()                 # Simulate clock drift
```

### 2.3 Injection Mechanisms

```python
# chaos/injector.py
@dataclass
class FaultConfig:
    fault_type: FaultType
    target_module: str              # e.g., "estimation.ekf"
    target_function: str            # e.g., "update"
    probability: float              # 0.0-1.0 injection probability
    duration_s: float               # How long the fault persists
    intensity: float                # 0.0-1.0 severity
    trigger: Literal["random", "scheduled", "conditional"] = "random"
    condition: Callable | None = None  # For conditional injection

class FaultInjector:
    def __init__(self, config: FaultConfig):
        self.config = config
        self._active = False
        self._injection_count = 0
    
    def inject(self, *args, **kwargs):
        """Wrap a function call with fault injection."""
        if not self._should_inject():
            return self._call_original(*args, **kwargs)
        return self._apply_fault(*args, **kwargs)
    
    def _should_inject(self) -> bool:
        if self.config.trigger == "random":
            return np.random.random() < self.config.probability
        if self.config.trigger == "conditional" and self.config.condition:
            return self.config.condition()
        return False
```

### 2.4 Integration Points (Monkey-Patching)

Each module needs injection hooks. Example for EKF:

```python
# estimation/ekf.py — add at end of class
class EKFEstimator:
    _fault_injector: FaultInjector | None = None
    
    def attach_fault_injector(self, injector: FaultInjector) -> None:
        self._fault_injector = injector
    
    def update(self, measurement: NDArray[np.float64]) -> None:
        if self._fault_injector:
            measurement = self._fault_injector.apply_to_measurement(measurement)
        # ... existing update logic
```

### 2.5 Recommended Fault Injection Libraries

| Library | Purpose | Integration Effort |
|---------|---------|-------------------|
| `chaoslib` | Python-native chaos experiments | Low — experiment definitions |
| `hypothesis` | Property-based testing (already in dev deps) | Low — already available |
| `pytest-chaos` | Pytest plugin for chaos tests | Low — test integration |
| Custom injector | Module-specific fault injection | Medium — per-module hooks |

---

## 3. What Resilience Testing to Add

### 3.1 Test Categories Missing

#### A. Numerical Stability Tests (Critical)
```python
# tests/chaos/test_ekf_numerical_stability.py
class TestEKFNumericalStability:
    def test_covariance_stays_positive_definite_under_noise(self):
        """Inject measurement noise — covariance must remain PD."""
    
    def test_state_divergence_detection(self):
        """Force divergence — estimator must detect and recover."""
    
    def test_covariance_blowup_prevention(self):
        """Long prediction without update — covariance must not blow up."""
    
    def test_joseph_form_numerical_accuracy(self):
        """Joseph form must maintain symmetry and positive-definiteness."""
    
    def test_reset_after_divergence(self):
        """After divergence detection, reset must restore valid state."""
```

#### B. Planner Failure Mode Tests
```python
# tests/chaos/test_planner_failures.py
class TestPlannerFailures:
    def test_astar_max_iterations_timeout(self):
        """A* must terminate within wall-clock time, not just iteration count."""
    
    def test_rrt_node_explosion_prevention(self):
        """RRT must respect node count limits."""
    
    def test_prm_disconnected_graph(self):
        """PRM must handle disconnected roadmaps gracefully."""
    
    def test_hybrid_astar_steering_singularity(self):
        """Hybrid A* must handle steering angle singularities."""
    
    def test_planner_fallback_chain(self):
        """If A* fails, system must fall back to RRT, then PRM."""
    
    def test_planner_with_corrupt_obstacles(self):
        """Planners must handle NaN/inf obstacle data."""
```

#### C. Control Stability Tests
```python
# tests/chaos/test_control_stability.py
class TestControlStability:
    def test_mpc_bounded_output_under_disturbance(self):
        """MPC outputs must remain bounded under external disturbances."""
    
    def test_mpc_recovery_from_saturation(self):
        """After saturation, MPC must recover without oscillation."""
    
    def test_mpc_with_delayed_feedback(self):
        """MPC must tolerate delayed state feedback."""
    
    def test_mpc_with_noisy_state(self):
        """MPC must be robust to noisy state estimates."""
```

#### D. Safety Filter Tests
```python
# tests/chaos/test_safety_filter.py
class TestSafetyFilter:
    def test_cbf_with_missing_obstacle_data(self):
        """CBF must fail-safe when obstacle data is missing."""
    
    def test_cbf_with_corrupt_obstacle_positions(self):
        """CBF must detect and reject NaN/inf obstacle positions."""
    
    def test_cbf_graduated_response(self):
        """CBF should provide graduated response, not binary safe/unsafe."""
    
    def test_cbf_recovery_from_violation(self):
        """After safety violation, CBF must guide system back to safety."""
    
    def test_cbf_with_zero_safety_margin(self):
        """CBF must handle zero/negative safety margin gracefully."""
```

#### E. Swarm Resilience Tests
```python
# tests/chaos/test_swarm_resilience.py
class TestSwarmResilience:
    def test_allocation_with_agent_failure(self):
        """Task allocation must handle agents dropping out."""
    
    def test_allocation_with_communication_loss(self):
        """Tasks must be reallocated when communication is lost."""
    
    def test_formation_with_agent_dropout(self):
        """Formation must reconfigure when an agent drops out."""
    
    def test_task_starvation_prevention(self):
        """Low-priority tasks must not be starved indefinitely."""
```

#### F. System-Level Resilience Tests
```python
# tests/chaos/test_system_resilience.py
class TestSystemResilience:
    def test_circuit_breaker_on_repeated_failure(self):
        """Repeated failures must trigger circuit breaker."""
    
    def test_graceful_degradation_under_load(self):
        """System must degrade gracefully under resource pressure."""
    
    def test_recovery_after_failure(self):
        """System must recover after transient failure."""
    
    def test_partial_failure_isolation(self):
        """One module's failure must not cascade to others."""
    
    def test_health_check_accuracy(self):
        """Health check must reflect actual module health."""
```

### 3.2 Property-Based Tests (Using hypothesis — already in dev deps)

```python
# tests/chaos/test_properties.py
from hypothesis import given, strategies as st

class TestProperties:
    @given(st.lists(st.floats(allow_nan=True, allow_infinity=True), min_size=6))
    def test_ekf_never_crashes_on_any_measurement(self, measurement):
        """EKF must not crash on any input, even NaN/inf."""
    
    @given(st.lists(st.floats(), min_size=3, max_size=3))
    def test_cbf_never_returns_nan(self, obstacle_center):
        """CBF must never return NaN control inputs."""
    
    @given(st.integers(min_value=0, max_value=10000))
    def test_planner_always_terminates(self, max_iterations):
        """Planners must always terminate within max_iterations."""
```

### 3.3 Load and Performance Under Failure Tests

```python
# tests/chaos/test_performance_under_failure.py
class TestPerformanceUnderFailure:
    def test_planning_time_under_memory_pressure(self):
        """Planning time must not degrade catastrophically under memory pressure."""
    
    def test_estimation_accuracy_under_measurement_noise(self):
        """EKF accuracy must degrade gracefully with increasing noise."""
    
    def test_control_stability_under_cpu_throttle(self):
        """Control must remain stable when CPU is throttled."""
```

---

## 4. How to Maintain System Stability

### 4.1 Stability Mechanisms to Implement

#### A. Circuit Breaker Pattern
```python
# chaos/recovery.py
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout_s: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self._failure_count = 0
        self._state = "closed"  # closed, open, half-open
        self._last_failure_time: float | None = None
    
    def call(self, func, *args, **kwargs):
        if self._state == "open":
            if self._should_attempt_reset():
                self._state = "half-open"
            else:
                raise CircuitBreakerOpen("Service temporarily unavailable")
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

#### B. Bulkhead Pattern
```python
# Limit concurrent operations per module
class Bulkhead:
    def __init__(self, max_concurrent: int, module_name: str):
        self.semaphore = threading.Semaphore(max_concurrent)
        self.module_name = module_name
    
    def execute(self, func, *args, **kwargs):
        if not self.semaphore.acquire(timeout=5.0):
            raise BulkheadFull(f"{self.module_name} bulkhead full")
        try:
            return func(*args, **kwargs)
        finally:
            self.semaphore.release()
```

#### C. Timeout Enforcement
```python
# Add wall-clock timeouts to all planners
@dataclass
class AStarConfig:
    # ... existing fields ...
    max_time_s: float = 5.0  # Wall-clock timeout

class AStarPlanner:
    def plan(self, problem: PlanningProblem) -> PlanningResult:
        start_time = time.perf_counter()
        # ... in the main loop:
        while open_set and iterations < self.config.max_iterations:
            if time.perf_counter() - start_time > self.config.max_time_s:
                return PlanningResult(
                    success=False,
                    computation_time_ms=(time.perf_counter() - start_time) * 1000,
                    message="Time limit exceeded",
                )
            # ... rest of loop
```

#### D. Degradation Strategies
```python
# Graceful degradation chain for planners
class PlannerChain:
    def __init__(self, planners: list):
        self.planners = planners  # Ordered by preference
    
    def plan(self, problem: PlanningProblem) -> PlanningResult:
        for planner in self.planners:
            result = planner.plan(problem)
            if result.success:
                return result
        # All planners failed — return best-effort result
        return PlanningResult(
            success=False,
            message="All planners failed",
            metadata={"attempted_planners": len(self.planners)},
        )
```

#### E. Health Check Integration
```python
# Make HealthCheck actually check things
class HealthCheck:
    def check(self, service_name: str, modules: dict) -> Dict[str, Any]:
        checks = {}
        for name, module in modules.items():
            checks[name] = self._check_module(name, module)
        healthy = all(c == "pass" for c in checks.values())
        return {
            "service": service_name,
            "status": "healthy" if healthy else "degraded",
            "checks": checks,
        }
    
    def _check_module(self, name: str, module) -> str:
        # Check EKF covariance is PD
        if name == "ekf":
            cov = module.get_covariance()
            eigenvals = np.linalg.eigvalsh(cov)
            return "pass" if np.all(eigenvals > 0) else "fail"
        # Check planner responsiveness
        if name.startswith("planning."):
            # Run a trivial plan
            return "pass"
        return "pass"
```

### 4.2 Monitoring and Alerting Integration

```python
# Extend observability module
class ChaosMetrics:
    def __init__(self):
        self._fault_injections = 0
        self._circuit_breaker_trips = 0
        self._degradation_events = 0
        self._recovery_events = 0
    
    def record_fault_injection(self, fault_type: FaultType, module: str):
        self._fault_injections += 1
        # Emit metric
    
    def record_circuit_breaker_trip(self, module: str):
        self._circuit_breaker_trips += 1
        # Emit metric
    
    def record_degradation(self, from_module: str, to_module: str):
        self._degradation_events += 1
        # Emit metric
```

### 4.3 Configuration for Chaos Engineering

```yaml
# configs/chaos.yaml
chaos:
  enabled: false  # Off by default in production
  
  # Global settings
  default_probability: 0.01
  default_duration_s: 5.0
  max_concurrent_faults: 3
  
  # Module-specific settings
  modules:
    estimation.ekf:
      faults:
        - type: MEASUREMENT_DROP
          probability: 0.05
        - type: COVARIANCE_CORRUPTION
          probability: 0.01
      circuit_breaker:
        failure_threshold: 10
        recovery_timeout_s: 60.0
    
    planning.astar:
      faults:
        - type: TIMEOUT
          probability: 0.001
      max_time_s: 10.0
    
    safety.cbf:
      faults:
        - type: CBF_BYPASS
          probability: 0.0001  # Very rare — safety critical
      # No circuit breaker for safety — fail-safe instead
```

### 4.4 Stability Maintenance Workflow

```
┌─────────────────────────────────────────────────────┐
│              Stability Maintenance Cycle             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. DEFINE steady-state hypothesis                  │
│     "EKF covariance stays PD for 24h operation"     │
│                                                     │
│  2. INJECT faults that violate hypothesis           │
│     "Drop 5% of measurements"                       │
│                                                     │
│  3. OBSERVE system behavior                         │
│     Monitor: covariance eigenvalues, state error     │
│                                                     │
│  4. VERIFY hypothesis holds (or not)                 │
│     If violated → fix the module                    │
│                                                     │
│  5. AUTOMATE the experiment                         │
│     Run in CI on every merge to main                 │
│                                                     │
│  6. EXPAND fault coverage                           │
│     Add new fault types monthly                     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 5. Implementation Priority Matrix

| Priority | Item | Effort | Impact | Module |
|----------|------|--------|--------|--------|
| P0 | EKF covariance regularization | Low | Critical | estimation/ekf.py |
| E0 | Wall-clock timeouts for planners | Low | Critical | planning/*.py |
| P0 | Health check actually checks something | Low | High | observability.py |
| P0 | Happy-path-only test gap | Medium | Critical | tests/ |
| P1 | Fault injection framework | Medium | High | chaos/ (new) |
| P1 | Circuit breaker pattern | Medium | High | chaos/recovery.py |
| P1 | Planner fallback chain | Medium | High | planning/chain.py |
| P1 | CBF fail-safe on missing data | Low | High | safety/cbf.py |
| P1 | Property-based tests | Medium | High | tests/chaos/ |
| P2 | Numerical stability test suite | Medium | High | tests/chaos/ |
| P2 | Swarm resilience tests | Medium | Medium | tests/chaos/ |
| P2 | Degradation strategies | Medium | Medium | chaos/recovery.py |
| P2 | Chaos experiment CI integration | Medium | Medium | .github/ |
| P3 | Bulkhead pattern | Medium | Medium | chaos/recovery.py |
| P3 | Load/performance under failure | High | Medium | tests/chaos/ |
| P3 | Chaos configuration system | Medium | Low | configs/ |

---

## 6. Reference: Chaos Engineering Patterns from OSS Projects

### 6.1 Chaos Monkey (Netflix)
- **Pattern**: Random instance termination
- **Application**: Randomly drop swarm agents, disable planners
- **Key takeaway**: Start with random faults, evolve to targeted

### 6.2 Litmus (CNCF)
- **Pattern**: Declarative chaos experiments (YAML)
- **Application**: `configs/chaos.yaml` experiment definitions
- **Key takeaway**: Experiments should be declarative and version-controlled

### 6.3 Gremlin
- **Pattern**: Fault injection as a service (CPU, memory, network, disk)
- **Application**: System-level faults (CPU throttle, memory pressure, clock skew)
- **Key takeaway**: Platform-level faults complement application-level faults

### 6.4 Pumba
- **Pattern**: Docker container chaos (network delay, packet loss, kill)
- **Application**: If deployed in containers, network-level fault injection
- **Key takeaway**: Infrastructure-level chaos for deployment scenarios

### 6.5 Hypothesis (Property-Based Testing)
- **Pattern**: Generate random inputs to find edge cases
- **Application**: Already in dev dependencies — use for numerical stability tests
- **Key takeaway**: Property-based tests find bugs that example-based tests miss

---

## 7. Summary of Gaps

| # | Gap | Severity | Modules Affected |
|---|-----|----------|-----------------|
| 1 | No fault injection framework | Critical | All |
| 2 | No resilience testing | Critical | All |
| 3 | Tests are 100% happy-path | Critical | All |
| 4 | EKF has no numerical stability safeguards | Critical | estimation/ekf.py |
| 5 | Planners have no wall-clock timeouts | Critical | planning/*.py |
| 6 | Health check always returns "healthy" | High | observability.py |
| 7 | No circuit breakers | High | All |
| 8 | No degradation/fallback strategies | High | All |
| 9 | CBF fails unsafe on missing data | High | safety/cbf.py |
| 10 | No swarm agent failure handling | Medium | swarm/*.py |
| 11 | No property-based tests | Medium | All |
| 12 | No chaos experiment automation | Medium | CI/CD |
| 13 | No stability monitoring/metrics | Medium | observability.py |
| 14 | No configuration for chaos scenarios | Low | configs/ |
| 15 | No bulkhead isolation | Low | All |

---

**Recommendation:** Start with P0 items (EKF covariance regularization, planner timeouts, real health checks) — they are low effort, high impact, and address the most critical safety gaps. Then build the fault injection framework incrementally, starting with EKF and planners.
