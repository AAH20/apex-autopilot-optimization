# Distributed Tracing & Observability Gap Report

**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Scope:** Distributed tracing, OpenTelemetry integration, trace context propagation

---

## Executive Summary

The project has a functional `observability.py` (160 lines) providing structured logging, basic metrics, and health checks. However, it has **zero distributed tracing capability** — no OpenTelemetry, no Jaeger, no Zipkin, no trace context propagation, no cross-module or cross-service correlation. For a multi-module autopilot system with 20 modules (planning, control, estimation, swarm, safety), this is a critical observability gap.

---

## 1. Current State Assessment

### What exists (`observability.py`)

| Component | Lines | Capability | Limitation |
|-----------|-------|------------|------------|
| `StructuredLogger` | ~30 | JSON structured logging with levels | No trace_id/span_id correlation |
| `MetricCollector` | ~30 | Counter, gauge, histogram | In-memory only, no export, no labels |
| `HealthCheck` | ~15 | Liveness/readiness probes | Static, no dependency health |
| `ObservabilityManager` | ~30 | Unified facade | No tracing, no context propagation |
| Module-level functions | ~55 | Convenience wrappers | No integration with core modules |

### What is missing

| Gap | Severity | Impact |
|-----|----------|--------|
| No distributed tracing | **CRITICAL** | Cannot trace requests across modules |
| No OpenTelemetry | **HIGH** | No industry-standard instrumentation |
| No trace context propagation | **HIGH** | Cross-module calls are invisible |
| No span lifecycle management | **HIGH** | No latency tracking per operation |
| No trace-to-log correlation | **MEDIUM** | Logs cannot be linked to traces |
| No metrics export (Prometheus/OTLP) | **MEDIUM** | Metrics are in-memory only |
| No sampling strategy | **MEDIUM** | No control over trace volume |
| No collector integration | **MEDIUM** | No centralized trace aggregation |

---

## 2. What Distributed Tracing Is Needed

### 2.1 Cross-Module Trace Context

The autopilot pipeline flows through 6+ modules sequentially:

```
Sensors → EKF → Planner → Optimizer → Safety → Controller → Actuators
```

Each module is a potential span boundary. Without tracing, a 500ms pipeline latency cannot be attributed to a specific module.

### 2.2 Swarm Multi-Agent Tracing

The `swarm/` module coordinates multiple agents. Tracing must capture:
- Task allocation decisions (which agent got which task)
- Formation computation (leader-follower relationships)
- Inter-agent communication patterns

### 2.3 Planning Algorithm Tracing

Path planning (A*, RRT, PRM, Hybrid A*) involves iterative search. Tracing should capture:
- Search iterations and convergence
- Collision checks per node
- Path cost computation
- Timeout/failure conditions

### 2.4 Safety-Critical Decision Tracing

The CBF safety filter makes binary safe/unsafe decisions. Tracing must capture:
- CBF value computation
- Correction magnitude
- Near-miss events (h ≈ 0)
- Safety margin violations

### 2.5 Real-Time Performance Tracing

Autopilot systems have hard real-time constraints (PX4: 200-500 Hz, EKF: 5-15ms). Tracing must:
- Add <1% overhead (sampling)
- Not block real-time loops
- Capture deadline misses

---

## 3. How to Implement OpenTelemetry

### 3.1 Dependency Addition

```toml
# pyproject.toml — add to [project.optional-dependencies]
tracing = [
    "opentelemetry-api>=1.24.0,<2.0.0",
    "opentelemetry-sdk>=1.24.0,<2.0.0",
    "opentelemetry-exporter-otlp-proto-grpc>=1.24.0,<2.0.0",
    "opentelemetry-semantic-conventions>=0.45.0,<1.0.0",
    "opentelemetry-instrumentation>=0.45.0,<1.0.0",
]
```

### 3.2 Core Tracing Module (`tracing.py`)

```python
"""OpenTelemetry distributed tracing for apex-autopilot-optimization."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from opentelemetry import trace, propagate, baggage
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


@dataclass(frozen=True, slots=True)
class TracingConfig:
    """Configuration for distributed tracing."""
    service_name: str = "apex-autopilot"
    service_version: str = "0.1.0"
    deployment_environment: str = "production"
    otlp_endpoint: str = "http://localhost:4317"
    sample_rate: float = 0.1  # 10% head sampling
    enabled: bool = True
    console_export: bool = False  # Debug mode


class TracingManager:
    """Manages OpenTelemetry tracing lifecycle."""

    def __init__(self, config: TracingConfig) -> None:
        self.config = config
        self._provider: Optional[TracerProvider] = None
        self._tracer: Optional[trace.Tracer] = None

    def initialize(self) -> None:
        """Initialize the tracer provider with OTLP exporter."""
        if not self.config.enabled:
            return

        resource = Resource(attributes={
            SERVICE_NAME: self.config.service_name,
            SERVICE_VERSION: self.config.service_version,
            DEPLOYMENT_ENVIRONMENT: self.config.deployment_environment,
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
        })

        sampler = ParentBased(TraceIdRatioBased(self.config.sample_rate))
        self._provider = TracerProvider(resource=resource, sampler=sampler)

        # OTLP exporter for production
        otlp_exporter = OTLPSpanExporter(
            endpoint=self.config.otlp_endpoint,
            insecure=True,
        )
        self._provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Console exporter for debugging
        if self.config.console_export:
            self._provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )

        trace.set_tracer_provider(self._provider)
        self._tracer = trace.get_tracer(self.config.service_name)

    @property
    def tracer(self) -> trace.Tracer:
        if self._tracer is None:
            self._tracer = trace.get_tracer(self.config.service_name)
        return self._tracer

    def shutdown(self) -> None:
        if self._provider is not None:
            self._provider.shutdown()

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Iterator[trace.Span]:
        """Start a span as a context manager."""
        with self.tracer.start_as_current_span(name, kind=kind) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span

    def inject_context(self, carrier: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Inject trace context into a carrier for propagation."""
        if carrier is None:
            carrier = {}
        propagate.inject(carrier)
        return carrier

    def extract_context(self, carrier: Dict[str, str]) -> Context:
        """Extract trace context from a carrier."""
        return propagate.extract(carrier)

    def get_current_span(self) -> trace.Span:
        return trace.get_current_span()

    def set_baggage(self, key: str, value: str) -> None:
        """Set baggage for cross-service context."""
        baggage.set_baggage(key, value)

    def get_baggage(self, key: str) -> Optional[str]:
        return baggage.get_baggage(key)
```

### 3.3 Decorator for Automatic Spans

```python
# tracing_decorators.py
from functools import wraps
from typing import Any, Callable, Optional
from opentelemetry.trace import SpanKind, Status, StatusCode

def traced(
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[dict] = None,
):
    """Decorator to automatically trace function execution."""
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            from apex_autopilot_optimization.tracing import get_tracing_manager
            manager = get_tracing_manager()
            if manager is None or not manager.config.enabled:
                return func(*args, **kwargs)

            with manager.start_span(span_name, kind=kind, attributes=attributes) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise
        return wrapper
    return decorator
```

### 3.4 Integration with Existing Modules

```python
# Example: planning/astar.py with tracing
from apex_autopilot_optimization.tracing import traced, get_tracing_manager
from opentelemetry.trace import SpanKind

class AStarPlanner:
    @traced("astar.plan", kind=SpanKind.INTERNAL, attributes={"planner": "astar"})
    def plan(self, problem: PlanningProblem) -> PlanningResult:
        # Existing logic unchanged
        ...
```

---

## 4. Tracing Patterns to Use

### 4.1 Pipeline Pattern (Sequential Modules)

For the autopilot data flow: `EKF → Planner → Optimizer → Safety → Controller`

```python
# Each module creates a child span under the same trace
# The trace context flows automatically via contextvars

def run_autopilot_pipeline(sensor_data):
    with manager.start_span("autopilot.pipeline", kind=SpanKind.INTERNAL) as root:
        root.set_attribute("pipeline.version", "2.0")

        # EKF span (child of pipeline)
        with manager.start_span("ekf.estimate") as span:
            state = ekf.update(sensor_data)
            span.set_attribute("ekf.state_dim", 12)

        # Planner span (child of pipeline)
        with manager.start_span("planner.plan") as span:
            result = planner.plan(problem)
            span.set_attribute("planner.iterations", result.iterations)
            span.set_attribute("planner.cost", result.cost)

        # Optimizer span (child of pipeline)
        with manager.start_span("optimizer.optimize") as span:
            trajectory = optimizer.optimize(result.waypoints)
            span.set_attribute("optimizer.trajectory_points", len(trajectory.positions))

        # Safety span (child of pipeline)
        with manager.start_span("safety.filter") as span:
            safe_control = cbf.filter(state, control, obstacles)
            span.set_attribute("safety.h_value", h_value)

        # Controller span (child of pipeline)
        with manager.start_span("controller.compute") as span:
            control = mpc.compute_control(state, target)
            span.set_attribute("control.horizon", mpc.config.horizon)
```

### 4.2 Fan-Out Pattern (Swarm Coordination)

For multi-agent task allocation:

```python
def allocate_and_execute(agents, tasks):
    with manager.start_span("swarm.allocate") as span:
        span.set_attribute("swarm.agent_count", len(agents))
        span.set_attribute("swarm.task_count", len(tasks))

        assignments = allocator.allocate(agents, tasks)

        # Fan-out: one span per agent execution
        for agent_id, task_id in assignments:
            with manager.start_span(f"swarm.agent.{agent_id}.execute") as agent_span:
                agent_span.set_attribute("agent.id", agent_id)
                agent_span.set_attribute("task.id", task_id)
                execute_task(agent_id, task_id)
```

### 4.3 Timed Operation Pattern (Real-Time Loops)

For control loops with deadline monitoring:

```python
def control_loop(state, target, deadline_ms: float):
    with manager.start_span("control.loop") as span:
        start = time.perf_counter()

        control = mpc.compute_control(state, target)

        elapsed_ms = (time.perf_counter() - start) * 1000
        span.set_attribute("control.elapsed_ms", elapsed_ms)
        span.set_attribute("control.deadline_ms", deadline_ms)

        if elapsed_ms > deadline_ms:
            span.set_attribute("control.deadline_miss", True)
            span.set_status(Status(StatusCode.ERROR, "Deadline missed"))
```

### 4.4 Error Tracking Pattern

```python
def safe_plan(problem):
    with manager.start_span("planner.plan") as span:
        try:
            result = planner.plan(problem)
            if not result.success:
                span.set_status(Status(StatusCode.ERROR, result.message))
                span.set_attribute("planner.failure_reason", result.message)
            return result
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
```

### 4.5 Span Link Pattern (Cross-Trace Correlation)

For correlating independent traces (e.g., sensor fusion triggering replanning):

```python
from opentelemetry.trace import Link

def on_sensor_anomaly(sensor_trace_id):
    # Link to the sensor trace that triggered this replan
    link = Link(sensor_trace_id)
    with manager.start_span("planner.replan", links=[link]) as span:
        span.set_attribute("replan.trigger", "sensor_anomaly")
        planner.plan(new_problem)
```

---

## 5. How to Maintain Trace Context

### 5.1 Context Propagation Mechanisms

| Boundary | Mechanism | Implementation |
|----------|-----------|----------------|
| **Same process, sync** | `contextvars` | Automatic via OTel SDK |
| **Same process, async** | `contextvars` + `asyncio` | Automatic (Python 3.7+) |
| **Same process, threads** | `contextvars.copy_context()` | Manual propagation |
| **Cross-process (HTTP)** | W3C `traceparent` header | `propagate.inject()` / `extract()` |
| **Cross-process (gRPC)** | W3C `traceparent` metadata | `propagate.inject()` / `extract()` |
| **Cross-process (MQ)** | Message headers/properties | `propagate.inject()` / `extract()` |

### 5.2 Thread Pool Propagation

```python
from concurrent.futures import ThreadPoolExecutor
from opentelemetry import context as otel_context

def run_in_thread_pool(fn, *args):
    """Propagate trace context to thread pool workers."""
    ctx = otel_context.get_current()
    def wrapped():
        token = otel_context.attach(ctx)
        try:
            return fn(*args)
        finally:
            otel_context.detach(token)
    return wrapped
```

### 5.3 Async Task Propagation

```python
import asyncio
from opentelemetry import context as otel_context

async def traced_async_task(coro, span_name: str):
    """Propagate trace context to async tasks."""
    ctx = otel_context.get_current()
    with manager.start_span(span_name) as span:
        # contextvars automatically propagate in asyncio
        return await coro
```

### 5.4 Message Queue Propagation

```python
# Producer
def publish_message(queue, message: dict):
    with manager.start_span("mq.publish") as span:
        headers = manager.inject_context()
        queue.publish(message, headers=headers)
        span.set_attribute("mq.destination", queue.name)

# Consumer
def consume_message(raw_message: dict):
    headers = raw_message.get("headers", {})
    ctx = manager.extract_context(headers)
    with manager.start_span("mq.consume", context=ctx) as span:
        process(raw_message["data"])
```

### 5.5 Log-to-Trace Correlation

```python
import logging
from opentelemetry import trace

class TraceContextFilter(logging.Filter):
    """Inject trace_id and span_id into log records."""
    def filter(self, record):
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            record.trace_id = format(ctx.trace_id, '032x')
            record.span_id = format(ctx.span_id, '016x')
        else:
            record.trace_id = ""
            record.span_id = ""
        return True

# Add to existing StructuredLogger
logger = logging.getLogger("apex_autopilot")
logger.addFilter(TraceContextFilter())
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Add `tracing.py` with `TracingManager` and `TracingConfig`
- [ ] Add OpenTelemetry dependencies to `pyproject.toml`
- [ ] Initialize tracing in `ObservabilityManager`
- [ ] Add trace context filter to `StructuredLogger`

### Phase 2: Core Instrumentation (Week 2)
- [ ] Instrument `planning/` module (A*, RRT, PRM, Hybrid A*)
- [ ] Instrument `control/mpc.py` with control loop spans
- [ ] Instrument `estimation/ekf.py` with predict/update spans
- [ ] Instrument `safety/cbf.py` with safety decision spans

### Phase 3: Swarm & Pipeline (Week 3)
- [ ] Instrument `swarm/task_allocation.py` with fan-out spans
- [ ] Instrument `swarm/formation.py` with formation computation spans
- [ ] Add pipeline-level span in `quickstart.py` / `evaluation.py`
- [ ] Add span links for cross-trace correlation

### Phase 4: Production Hardening (Week 4)
- [ ] Configure OTLP exporter with collector endpoint
- [ ] Implement sampling strategy (10% baseline, 100% errors)
- [ ] Add metrics-to-trace correlation (Prometheus exemplars)
- [ ] Add tracing to `diagnostics.py` for health check correlation
- [ ] Performance benchmark: verify <1% overhead

---

## 7. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tracing SDK | OpenTelemetry | Industry standard, vendor-neutral, CNCF |
| Exporter | OTLP gRPC | Efficient, binary, widely supported |
| Sampling | ParentBased(TraceIdRatioBased(0.1)) | 10% baseline, consistent trace decisions |
| Span processor | BatchSpanProcessor | Non-blocking, production-safe |
| Context format | W3C TraceContext | Standard, interoperable |
| Async support | contextvars (native) | Python 3.7+ automatic propagation |
| Thread support | contextvars.copy_context() | Explicit, safe propagation |
| Backend | Jaeger / Tempo / Zipkin | All support OTLP; switch without code changes |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Trace overhead on real-time loops | Deadline misses | Sampling + async export + span budget |
| Context loss across threads | Broken traces | Explicit context propagation |
| High cardinality attributes | Storage explosion | Attribute allow-list, events for high-cardinality |
| Collector outage | Trace data loss | Batch buffering + local fallback |
| Clock skew across nodes | Incorrect latency | NTP sync + monotonic clocks |

---

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| Trace coverage | 100% of pipeline stages |
| Overhead | <1% latency increase |
| Context propagation | 100% across all module boundaries |
| Trace completeness | >99% (no orphaned spans) |
| Time-to-debug | 50% reduction in MTTR |

---

## 10. References

- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/)
- [W3C Trace Context Specification](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry Python Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [OpenTelemetry Python Cookbook](https://opentelemetry.io/docs/languages/python/cookbook/)
- [Jaeger](https://www.jaegertracing.io/) — OpenTracing-compatible backend
- [Zipkin](https://zipkin.io/) — Distributed tracing system
- [Grafana Tempo](https://grafana.com/oss/tempo/) — High-scale trace storage
