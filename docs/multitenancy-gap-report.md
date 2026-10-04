# Multi-Tenancy Gap Report — apex-autopilot-optimization

**Date:** 2026-10-04  
**Scope:** Tenant isolation, resource quotas, per-tenant config  
**Current State:** 20 modules, zero multi-tenancy support

---

## 1. What Multi-Tenancy Is Needed

### 1.1 Current Architecture (Single-Tenant)

The project is a **single-tenant Python library** with no concept of tenants:

| Layer | Current State | Evidence |
|-------|--------------|----------|
| **Core types** | `StateVector`, `PlanningProblem`, `Trajectory` — no `tenant_id` field | `core/types.py` — all dataclasses lack tenant context |
| **Config** | Global `Dict[str, Any]` validated by `ConfigValidator` — no tenant scoping | `config_validator.py` — `validate_config(config)` takes no tenant parameter |
| **Security** | `AuthenticationHelper` uses in-memory `_tokens: Dict[str, Dict]` — no tenant claim in token payload | `security.py:73` — token payload has `sub`, `iat`, `exp` only |
| **Observability** | `ObservabilityConfig` has `service_name` but no tenant dimension; `MetricCollector` uses flat `_metrics: Dict[str, Any]` | `observability.py:19,63` — no tenant label on metrics |
| **Sizing/Onboarding** | `OrganizationScale` enum (startup→large) — this is **org size**, not tenant identity | `onboarding/sizing.py:14-21` — no tenant concept |
| **Persistence** | None — all state is in-memory, no database, no tenant data separation | No DB models, no ORM, no migrations |
| **API/CLI** | `apex-autopilot` CLI entry point exists but no tenant-aware routing | `pyproject.toml:53` — single CLI, no tenant subcommands |

### 1.2 What "Tenant" Means for This Project

A tenant is a **customer organization** that uses the autopilot optimization framework. Each tenant:

- Has its own fleet of vehicles (UAVs, ground vehicles)
- Runs its own planning/optimization workloads
- Has its own configuration, quotas, and data
- Must be isolated from other tenants' data and compute

### 1.3 Multi-Tenancy Patterns Applicable

Based on research of Python OSS projects (FastAPI + PostgreSQL SaaS, Logto BaaS, agent-governance-toolkit, Kubernetes multi-tenant model serving):

| Pattern | Isolation | Complexity | Fit for This Project |
|---------|-----------|------------|---------------------|
| **Shared schema + tenant_id** (row-level) | Logical | Low | ✅ Best starting point — matches current in-memory dict-based state |
| **Schema-per-tenant** | Physical (schema) | Medium | Overkill — no database yet |
| **Database-per-tenant** | Physical (DB) | High | Future option for enterprise tier |
| **Namespace-per-tenant** (K8s-style) | Physical (runtime) | Medium | Future — if deployed as a service |

**Recommendation:** Start with **shared schema + tenant_id** (the industry standard for early-stage SaaS — Stripe, Notion, Figma all started here). This aligns with the project's current architecture where all state is in-memory dictionaries.

---

## 2. How to Implement Tenant Isolation

### 2.1 Gap Analysis: Missing Isolation Points

| # | Gap | Location | Severity | Description |
|---|-----|----------|----------|-------------|
| G1 | No `tenant_id` in core types | `core/types.py` | **Critical** | `PlanningProblem`, `PlanningResult`, `Trajectory`, `StateVector` — none carry tenant context. Any planning operation can access any tenant's data. |
| G2 | No tenant context in config | `config_validator.py` | **Critical** | `validate_config(config)` validates a flat dict with no tenant scoping. Tenant A's config can leak to Tenant B. |
| G3 | No tenant in auth tokens | `security.py:70-88` | **Critical** | `generate_token(subject)` — token payload has no `tenant_id` claim. `verify_token()` cannot enforce tenant boundaries. |
| G4 | No tenant in observability | `observability.py` | **High** | `MetricCollector._metrics` is a flat dict — metrics from all tenants are aggregated together. No per-tenant log/metric separation. |
| G5 | No tenant in security audit log | `security.py:92-117` | **High** | `SecurityAuditLog.entries` is a single list — audit events from all tenants are mixed. |
| G6 | No tenant in sizing/onboarding | `onboarding/sizing.py` | **Medium** | `SizingProfile` is keyed by `OrganizationScale`, not tenant. No per-tenant module enablement. |
| G7 | No tenant in diagnostics | `diagnostics.py` | **Medium** | `DiagnosticReport` has no tenant context — diagnostics run globally, not per-tenant. |
| G8 | No tenant in benchmark/evaluation | `benchmark.py`, `evaluation.py` | **Medium** | `BenchmarkConfig` and `EvaluationConfig` have no tenant dimension. |
| G9 | No tenant in quickstart | `quickstart.py` | **Low** | `DemoScenario` is keyed by scale, not tenant. |
| G10 | No tenant in setup wizard | `setup_wizard.py` | **Low** | `WizardStep` actions run globally. |

### 2.2 Implementation Plan: Tenant Isolation

#### Phase 1: Core Tenant Context (Critical)

**New module: `src/apex_autopilot_optimization/tenancy/`**

```
tenancy/
├── __init__.py
├── context.py          # TenantContext dataclass + contextvar
├── resolver.py         # TenantResolver (from token, header, config)
├── isolation.py        # TenantIsolationEnforcer (decorator/middleware)
└── models.py           # Tenant, TenantStatus, TenantTier
```

**Key design decisions:**

1. **`TenantContext` dataclass** (frozen, slots):
   ```python
   @dataclass(frozen=True, slots=True)
   class TenantContext:
       tenant_id: str
       tier: TenantTier  # FREE, PRO, ENTERPRISE
       scale: OrganizationScale
       config: dict[str, Any]  # per-tenant config overlay
   ```

2. **Context variable for request-scoped tenant:**
   ```python
   _current_tenant: ContextVar[TenantContext | None] = ContextVar("tenant", default=None)
   ```
   This is the Python-native way to propagate tenant context through async call chains without threading it through every function signature.

3. **Tenant resolution from auth token:**
   - Extend `AuthenticationHelper.generate_token()` to include `tenant_id` in payload
   - Extend `verify_token()` to return `tenant_id`
   - Add `TenantResolver` that extracts tenant from: JWT claim → header → config fallback

4. **Isolation enforcement decorator:**
   ```python
   def require_tenant(func):
       """Decorator that ensures a tenant context is active."""
       @wraps(func)
       def wrapper(*args, **kwargs):
           if get_current_tenant() is None:
               raise TenantIsolationError("No tenant context")
           return func(*args, **kwargs)
       return wrapper
   ```

#### Phase 2: Add `tenant_id` to Core Types (Critical)

Modify `core/types.py`:

| Type | Change |
|------|--------|
| `PlanningProblem` | Add `tenant_id: str = ""` field |
| `PlanningResult` | Add `tenant_id: str = ""` field |
| `Trajectory` | Add `tenant_id: str = ""` field |
| `StateVector` | Add `tenant_id: str = ""` field (in `metadata` dict) |
| `BottleneckReport` | Add `tenant_id: str = ""` field |

**Backward compatibility:** Default `tenant_id=""` means "legacy single-tenant mode." Existing code continues to work.

#### Phase 3: Tenant-Aware Config (High)

Modify `config_validator.py`:

- Add `validate_config_for_tenant(config, tenant_id)` function
- Config resolution order: `global defaults → tier defaults → tenant overrides`
- Store per-tenant config in `tenancy/models.py` or external store

#### Phase 4: Tenant-Aware Observability (High)

Modify `observability.py`:

- `MetricCollector` metrics keyed by `(tenant_id, metric_name)` instead of flat `metric_name`
- `StructuredLogger` includes `tenant_id` in every log entry
- `SecurityAuditLog` entries include `tenant_id`

#### Phase 5: Tenant-Aware Security (High)

Modify `security.py`:

- `AuthenticationHelper._tokens` keyed by `(tenant_id, token)` instead of just `token`
- `SecurityAuditLog` entries include `tenant_id`
- `SecurityPolicy.check_all()` accepts optional `tenant_id` for tenant-specific policy checks

### 2.3 Isolation Enforcement Points

Every module that processes data must enforce tenant isolation:

| Module | Enforcement |
|--------|-------------|
| `planning/astar.py` | `AStarPlanner.plan()` checks `tenant_id` matches context |
| `planning/rrt.py` | Same |
| `planning/prm.py` | Same |
| `planning/hybrid_astar.py` | Same |
| `optimization/minimum_snap.py` | Same |
| `estimation/ekf.py` | Same |
| `swarm/task_allocation.py` | Same |
| `swarm/formation.py` | Same |
| `safety/cbf.py` | Same |
| `control/mpc.py` | Same |

---

## 3. What Resource Quotas to Enforce

### 3.1 Gap Analysis: No Quota System Exists

| # | Gap | Severity |
|---|-----|----------|
| Q1 | No quota data model | **Critical** |
| Q2 | No quota enforcement | **Critical** |
| Q3 | No rate limiting | **High** |
| Q4 | No concurrency limits | **High** |
| Q5 | No storage quotas | **Medium** |
| Q6 | No compute time quotas | **Medium** |
| Q7 | No quota exceeded handling | **High** |
| Q8 | No quota usage tracking | **High** |

### 3.2 Quota Dimensions

Based on research (FastAPI SaaS quotas, K8s resource quotas, LLM platform token quotas, agent-governance-toolkit):

| Quota | Description | Free Tier | Pro Tier | Enterprise Tier |
|-------|-------------|-----------|----------|-----------------|
| `max_concurrent_plans` | Simultaneous planning operations | 2 | 10 | 100 |
| `max_plans_per_hour` | Planning operations per hour | 100 | 1,000 | 10,000 |
| `max_vehicles` | Registered vehicles per tenant | 5 | 50 | 500 |
| `max_waypoints_per_plan` | Waypoints in a single plan | 50 | 500 | 5,000 |
| `max_obstacles` | Obstacles in planning problem | 100 | 1,000 | 10,000 |
| `max_trajectory_duration_s` | Maximum trajectory duration | 300 | 3,600 | 86,400 |
| `max_iterations` | Planner iteration limit | 10,000 | 100,000 | 1,000,000 |
| `max_compute_time_ms` | Single planning operation timeout | 5,000 | 30,000 | 300,000 |
| `max_storage_mb` | Persistent storage | 100 | 1,000 | 10,000 |
| `max_api_calls_per_hour` | API rate limit | 100 | 1,000 | 10,000 |
| `max_swarm_agents` | Vehicles in a single swarm | 3 | 20 | 200 |
| `max_daily_plans` | Daily planning budget | 50 | 500 | 5,000 |

### 3.3 Implementation Plan: Quota System

**New module: `src/apex_autopilot_optimization/tenancy/quotas.py`**

```python
@dataclass(frozen=True, slots=True)
class QuotaLimit:
    name: str
    limit: int
    period: str  # "hourly", "daily", "monthly"
    action: QuotaAction  # REJECT, THROTTLE, NOTIFY

@dataclass
class QuotaUsage:
    tenant_id: str
    quota_name: str
    current: int
    window_start: float
    window_end: float

class QuotaManager:
    """Enforces per-tenant resource quotas."""
    
    def check_quota(self, tenant_id: str, quota_name: str, cost: int = 1) -> QuotaCheckResult
    def record_usage(self, tenant_id: str, quota_name: str, cost: int = 1) -> None
    def get_usage(self, tenant_id: str, quota_name: str) -> QuotaUsage
    def reset_window(self, tenant_id: str, quota_name: str) -> None
```

**Enforcement pattern** (from research — atomic counters with UPSERT):

1. **Pre-flight check:** Before any planning/optimization operation, call `QuotaManager.check_quota()`
2. **Post-flight accounting:** After operation completes, call `QuotaManager.record_usage()`
3. **Atomic increment:** Use atomic operations (Redis INCRBY + EXPIREAT, or in-memory with locks) to prevent race conditions
4. **Graceful degradation:** When quota exceeded, return structured error with retry-after hint

**Integration points:**

| Module | Quota Check |
|--------|-------------|
| `AStarPlanner.plan()` | `max_concurrent_plans`, `max_plans_per_hour`, `max_compute_time_ms` |
| `RRTPlanner.plan()` | Same |
| `PRMPlanner.plan()` | Same |
| `HybridAStarPlanner.plan()` | Same |
| `MinimumSnapOptimizer.optimize()` | `max_compute_time_ms` |
| `TaskAllocator.allocate()` | `max_swarm_agents` |
| `FormationController.compute()` | `max_swarm_agents` |

---

## 4. How to Maintain Tenant-Specific Config

### 4.1 Gap Analysis: No Per-Tenant Config

| # | Gap | Severity |
|---|-----|----------|
| C1 | No tenant config store | **Critical** |
| C2 | No config inheritance/override | **High** |
| C3 | No config validation per tenant | **High** |
| C4 | No config versioning | **Medium** |
| C5 | No config hot-reload | **Medium** |
| C6 | No tenant-specific module enablement | **Medium** |

### 4.2 Config Inheritance Model

Based on research (agent-governance-toolkit multi-tenant.yaml, Logto dynamic tenant config):

```
┌─────────────────────────────────────────────────────┐
│                  Config Resolution                   │
│                                                      │
│  1. Global defaults (config_validator.py)            │
│       ↓                                              │
│  2. Tier defaults (FREE / PRO / ENTERPRISE)          │
│       ↓                                              │
│  3. Scale defaults (startup → large)                 │
│       ↓                                              │
│  4. Tenant-specific overrides                        │
│       ↓                                              │
│  5. Request-level overrides (optional)               │
│                                                      │
│  Final merged config → validated → used              │
└─────────────────────────────────────────────────────┘
```

### 4.3 Implementation Plan: Per-Tenant Config

**New module: `src/apex_autopilot_optimization/tenancy/config.py`**

```python
@dataclass
class TenantConfig:
    """Per-tenant configuration with inheritance."""
    tenant_id: str
    tier: TenantTier
    scale: OrganizationScale
    overrides: dict[str, Any]  # tenant-specific overrides
    enabled_modules: set[str]  # tenant-specific module enablement
    quota_limits: dict[str, int]  # tenant-specific quota overrides
    updated_at: float

class TenantConfigManager:
    """Manages per-tenant configuration with inheritance."""
    
    def get_config(self, tenant_id: str) -> TenantConfig
    def resolve_config(self, tenant_id: str) -> dict[str, Any]  # merged
    def update_config(self, tenant_id: str, overrides: dict[str, Any]) -> None
    def enable_module(self, tenant_id: str, module_name: str) -> None
    def disable_module(self, tenant_id: str, module_name: str) -> None
    def set_quota_override(self, tenant_id: str, quota_name: str, limit: int) -> None
```

**Config resolution order:**

1. **Global defaults** — from `config_validator.py` `MODULE_RULES` and `SIZING_PROFILES`
2. **Tier defaults** — from `TenantTier` enum (FREE/PRO/ENTERPRISE)
3. **Scale defaults** — from `SIZING_PROFILES[scale].config_defaults`
4. **Tenant overrides** — from `TenantConfig.overrides`
5. **Request overrides** — optional per-request config

**Storage options:**

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| In-memory dict | Fast, simple | Lost on restart | ✅ Phase 1 — matches current architecture |
| JSON file per tenant | Persistent, human-readable | I/O overhead | ✅ Phase 2 |
| SQLite | Persistent, queryable | New dependency | ✅ Phase 3 |
| Redis | Fast, distributed, atomic | Infrastructure | Future — multi-instance |
| etcd/consul | Distributed KV | Infrastructure | Future — multi-instance |

**Config validation per tenant:**

- Extend `ConfigValidator.validate()` to accept `tenant_id` parameter
- Validate tenant overrides against `MODULE_RULES`
- Reject invalid tenant config with `ValidationIssue` list
- Warn about unknown fields (already exists)

### 4.4 Tenant-Specific Module Enablement

Extend `onboarding/sizing.py`:

```python
@dataclass(frozen=True)
class TenantModuleConfig:
    tenant_id: str
    enabled_modules: frozenset[str]
    disabled_modules: frozenset[str]
    
    def is_enabled(self, module_name: str) -> bool:
        if module_name in self.disabled_modules:
            return False
        if module_name in self.enabled_modules:
            return True
        # Fall back to scale-based default
        return module_name in get_available_modules(self.scale)
```

---

## 5. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Create `tenancy/` module with `TenantContext`, `TenantResolver`, `TenantIsolationError`
- [ ] Add `tenant_id` field to core types (`PlanningProblem`, `PlanningResult`, `Trajectory`)
- [ ] Extend `AuthenticationHelper` to include `tenant_id` in token payload
- [ ] Add `require_tenant` decorator
- [ ] Write tests for tenant isolation

### Phase 2: Config & Quotas (Weeks 3-4)
- [ ] Implement `TenantConfigManager` with in-memory store
- [ ] Implement `QuotaManager` with atomic counters
- [ ] Add quota checks to all planner/optimizer entry points
- [ ] Extend `ConfigValidator` for per-tenant validation
- [ ] Write tests for quota enforcement and config inheritance

### Phase 3: Observability & Audit (Week 5)
- [ ] Add `tenant_id` to `MetricCollector` keys
- [ ] Add `tenant_id` to `StructuredLogger` entries
- [ ] Add `tenant_id` to `SecurityAuditLog` entries
- [ ] Write tests for tenant-aware observability

### Phase 4: Persistence & Hardening (Weeks 6-7)
- [ ] Add SQLite-backed tenant config store
- [ ] Add quota usage persistence
- [ ] Implement config hot-reload
- [ ] Add tenant onboarding flow (create tenant → assign tier → provision config)
- [ ] Write integration tests

### Phase 5: Advanced (Week 8+)
- [ ] Redis-backed quota store for multi-instance
- [ ] Tenant migration tools
- [ ] Tenant-specific rate limiting (token bucket)
- [ ] Cross-tenant injection protection (from agent-governance-toolkit patterns)
- [ ] Tenant suspension/emergency controls

---

## 6. Research References

| Source | Key Takeaway |
|--------|-------------|
| [Multi-Tenancy Patterns 2026](https://blog.rajpoot.dev/posts/backend/multitenancy-patterns-2026) | Shared schema + tenant_id is the standard starting point; RLS as defense-in-depth |
| [Multi-Tenant LLM Platform](https://wickedsmartdata.com/articles/building-a-multi-tenant-llm-platform-isolating-contexts-enforcing-usage-quotas-and-managing-costs-per-customer) | Atomic quota enforcement with Redis Lua scripts; pre-flight + post-flight pattern |
| [agent-governance-toolkit multi-tenant.yaml](https://github.com/NousResearch/agent-governance-toolkit/blob/main/agent-governance-python/agent-os/templates/policies/multi-tenant.yaml) | Tier-based quotas, cross-tenant injection protection, tenant onboarding, emergency controls |
| [Logto Python OSS BaaS](https://johal.in/logto-python-oss-auth-infrastructure-consoleless-baas-multi-tenancy-2026) | Dynamic tenant resolution from JWT claims; tenant-aware Redis namespaces |
| [FastAPI + PostgreSQL Multi-Tenancy](https://dev.to/martin_palopoli/real-multi-tenancy-with-fastapi-and-postgresql-plans-quotas-and-data-isolation-36ah) | Atomic UPSERT for quota counters; plan enforcement on all resources |
| [Gemini API Multi-Tenant SaaS](https://gemilab.net/en/articles/gemini-api/gemini-api-multi-tenant-saas-architecture-guide) | Per-tenant token bucket rate limiting; budget guard with 80%/100% alerts |
| [K8s Multi-Tenant Model Serving](https://truly.cloud/design-patterns-for-multi-tenant-model-serving-isolation-res) | Namespace-per-tenant; resource quotas; cgroups enforcement; node pools by SLA tier |
| [Context Engineering for Enterprise AI](https://dev.to/kirandeepjassalcrypto/context-engineering-for-enterprise-ai-part-5-multi-tenant-patterns-that-dont-leak-starve-or-b63) | Pool by default, promote on threshold; tenant_id filter at router level; cache key carries tenant |

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing single-tenant API | High | Medium | Default `tenant_id=""` for backward compatibility |
| Performance overhead from tenant checks | Medium | Low | ContextVar is O(1); quota checks are in-memory dict lookups |
| Race conditions in quota counters | Medium | High | Use atomic operations (locks, Redis Lua scripts) |
| Config inheritance bugs | Medium | Medium | Comprehensive tests for all inheritance orderings |
| Tenant data leakage via metadata | Low | Critical | Audit all `metadata: dict[str, Any]` fields for tenant context |
| No database for tenant persistence | High | Medium | Start with in-memory, migrate to SQLite in Phase 4 |

---

## 8. Summary of Gaps

| Category | Gaps | Critical | High | Medium | Low |
|----------|------|----------|------|--------|-----|
| Tenant Isolation | G1-G10 | 3 | 2 | 3 | 2 |
| Resource Quotas | Q1-Q8 | 2 | 4 | 2 | 0 |
| Per-Tenant Config | C1-C6 | 1 | 2 | 3 | 0 |
| **Total** | **24** | **6** | **8** | **8** | **2** |

**Bottom line:** The project has **zero multi-tenancy support**. Every module operates on global, un-scoped state. Implementing multi-tenancy requires changes to all 20 modules, with the most critical being: (1) adding `tenant_id` to core types, (2) extending auth tokens with tenant claims, (3) building a quota system, and (4) implementing per-tenant config inheritance. The recommended approach is **shared schema + tenant_id** with `ContextVar`-based tenant context propagation, starting with in-memory stores and migrating to persistent storage in later phases.
