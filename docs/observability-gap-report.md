# Observability & Logging Gap Report — apex-autopilot-optimization

**Date:** 2026-10-04  
**Scope:** `src/apex_autopilot_optimization/observability.py` (165 lines) + full source tree + `pyproject.toml` + tests  
**Method:** Static analysis of all 20 modules, dependency audit, comparison with structlog/loguru/python-json-logger patterns

---

## Executive Summary

The observability module is a **skeleton with no working logging**. `StructuredLogger` builds a dict and returns it — nothing is ever written to stdout, a file, or any handler. The `log_level` field is stored but never enforced. `structlog>=24.1.0` is declared as a dependency but never imported. No module outside `observability.py` and its test imports `ObservabilityManager`. The CLI does not initialize or use any logging. There is no log rotation, no aggregation, no lifecycle management, no context propagation, and no exception serialization.

**Severity: Critical** — the project has zero functional observability in production.

---

## 1. What Logging Integration Is Needed

### 1.1 Current State

| Aspect | Status |
|--------|--------|
| `import logging` (stdlib) | **0 occurrences** in entire source tree |
| `import structlog` | **0 occurrences** — declared in `pyproject.toml` but unused |
| `loguru` / `python-json-logger` | Not installed, not used |
| `print()` in production code | **0 occurrences** (good) |
| `ObservabilityManager` imported outside its own module | **0 occurrences** |
| CLI logging initialization | **None** — `cli.py` has no logging setup |
| Log configuration (YAML/env/dictConfig) | **None** |
| `RotatingFileHandler` / `TimedRotatingFileHandler` | **None** |
| OpenTelemetry / Prometheus export | **None** |

### 1.2 The Core Problem

`StructuredLogger._log()` (line 32–40) constructs a dict and **returns it**. It never calls `print()`, `logging.info()`, `structlog.get_logger().info()`, or any output mechanism. The method is a pure function with no side effects. Every log call in the entire codebase produces a dict that is immediately discarded.

```python
# Current — observability.py:32-40
def _log(self, level: str, message: str, **context: Any) -> Dict[str, Any]:
    return {
        "timestamp": int(time.time()),
        "level": level,
        "service": self.service_name,
        "message": message,
        "context": context,
    }
```

### 1.3 What Must Be Integrated

| Integration | Priority | Rationale |
|-------------|----------|-----------|
| **structlog** with stdlib `logging` backend | **Critical** | Already a dependency; provides structured JSON output, context binding, processor pipeline, level filtering |
| **Console handler** (stdout) | **Critical** | Twelve-factor app methodology; container-native |
| **RotatingFileHandler** | **High** | Local development and non-containerized deployments |
| **dictConfig** or `structlog.configure()` at startup | **Critical** | Single initialization point, no scattered config |
| **Module-level `get_logger(__name__)`** | **High** | Standard Python pattern; per-module loggers with service name propagation |
| **OpenTelemetry exporter** | **Medium** | Distributed tracing for multi-module autopilot pipelines |
| **Prometheus metrics exporter** | **Medium** | `MetricCollector` currently has no export path |

---

## 2. How to Implement Structured Logging

### 2.1 Recommended Architecture: structlog + stdlib logging

The project already depends on `structlog>=24.1.0,<25.0.0`. The integration pattern:

```python
# observability.py — proposed replacement for StructuredLogger

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def setup_logging(
    service_name: str,
    log_level: str = "INFO",
    log_dir: str = "logs",
    enable_file: bool = True,
) -> structlog.BoundLogger:
    """Initialize structlog with stdlib logging backend.

    Call once at application startup (CLI entrypoint, test fixture).
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # --- stdlib logging configuration ---
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates on re-init
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler — JSON to stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # File handler — rotating, 10MB × 5 backups
    if enable_file:
        file_handler = RotatingFileHandler(
            Path(log_dir) / f"{service_name}.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(file_handler)

    # --- structlog configuration ---
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger(service_name)
    return logger
```

### 2.2 Context Propagation (Request/Trace IDs)

```python
import structlog
import uuid

# At request/pipeline entry point:
structlog.contextvars.clear_contextvars()
structlog.contextvars.bind_contextvars(
    request_id=str(uuid.uuid4()),
    service="planner",
)

# Anywhere downstream — no manual passing:
logger.info("planning_started", algorithm="astar", nodes=1000)
# Output: {"event": "planning_started", "request_id": "...", "service": "planner", ...}
```

### 2.3 Exception Serialization

```python
try:
    result = planner.plan(problem)
except Exception:
    logger.error("planning_failed", exc_info=True, algorithm="astar")
    # structlog's format_exc_info processor serializes the traceback
    # into a structured dict instead of a raw string
    raise
```

### 2.4 Backward-Compatible API

To avoid breaking the existing 228-line test suite, keep the public API surface:

```python
class StructuredLogger:
    """Backward-compatible wrapper around structlog."""

    def __init__(self, service_name: str, log_level: str = "INFO") -> None:
        self.service_name = service_name
        self.log_level = log_level
        self._logger = structlog.get_logger(service_name)

    def _log(self, level: str, message: str, **context: Any) -> Dict[str, Any]:
        """Build and emit a structured log entry.

        Returns the dict for backward compatibility with existing tests.
        """
        entry = {
            "timestamp": int(time.time()),
            "level": level,
            "service": self.service_name,
            "message": message,
            "context": context,
        }
        # Actually emit the log
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(message, **context)
        return entry

    def info(self, message: str, **context: Any) -> Dict[str, Any]:
        return self._log("INFO", message, **context)

    def error(self, message: str, **context: Any) -> Dict[str, Any]:
        return self._log("ERROR", message, **context)

    def warning(self, message: str, **context: Any) -> Dict[str, Any]:
        return self._log("WARNING", message, **context)

    def debug(self, message: str, **context: Any) -> Dict[str, Any]:
        return self._log("DEBUG", message, **context)
```

---

## 3. What Log Aggregation to Add

### 3.1 Current State

`MetricCollector` stores metrics in a plain in-memory `Dict[str, Any]`. There is no export path — no Prometheus endpoint, no StatsD, no OpenTelemetry. `get_metrics()` returns a dict that callers must handle manually.

### 3.2 Aggregation Layers Needed

| Layer | Tool/Pattern | Priority | Use Case |
|-------|-------------|----------|----------|
| **JSON stdout** | `structlog.JSONRenderer()` | **Critical** | Container log drivers (Docker, Kubernetes) collect stdout and ship to Loki/Elasticsearch/Datadog |
| **Prometheus exporter** | `prometheus-client` library | **High** | Scrape `/metrics` endpoint for RED metrics (Rate, Errors, Duration) |
| **OpenTelemetry** | `opentelemetry-sdk` | **Medium** | Distributed tracing across planning → control → estimation pipeline |
| **Log shipping** | Fluentd / Filebeat / Vector | **Medium** | Ship JSON logs from stdout to centralized aggregator |
| **Error tracking** | Sentry SDK | **Medium** | Automatic error deduplication, alerting, stack trace grouping |

### 3.3 Prometheus Integration

```python
# observability.py — proposed MetricCollector extension

from prometheus_client import Counter, Gauge, Histogram, start_http_server

class MetricCollector:
    """Metrics collector with Prometheus export."""

    def __init__(self, export_port: int = 0) -> None:
        self._metrics: Dict[str, Any] = {}
        self._prometheus: Dict[str, Any] = {}
        self._export_port = export_port

    def increment(self, name: str, value: int = 1) -> None:
        self._metrics[name] = self._metrics.get(name, 0) + value
        if name not in self._prometheus:
            self._prometheus[name] = Counter(name, f"Counter metric: {name}")
        self._prometheus[name].inc(value)

    def gauge(self, name: str, value: float) -> None:
        self._metrics[name] = value
        if name not in self._prometheus:
            self._prometheus[name] = Gauge(name, f"Gauge metric: {name}")
        self._prometheus[name].set(value)

    def histogram(self, name: str, value: float) -> None:
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(value)
        if name not in self._prometheus:
            self._prometheus[name] = Histogram(name, f"Histogram metric: {name}")
        self._prometheus[name].observe(value)

    def start_server(self) -> None:
        """Start Prometheus metrics HTTP server."""
        if self._export_port > 0:
            start_http_server(self._export_port)
```

### 3.4 Container-Native Pattern (Recommended)

For containerized deployments, the simplest and most robust pattern:

1. **Application writes JSON to stdout** via `structlog.JSONRenderer()`
2. **Container runtime** (Docker `--log-driver`, Kubernetes `kubectl logs`) captures stdout
3. **Log shipper** (Fluentd/Vector/Filebeat as DaemonSet) forwards to aggregator
4. **Aggregator** (Loki, Elasticsearch, Datadog) indexes and makes queryable

No file handlers needed inside containers — avoids the "logs lost when pod replaced" problem.

---

## 4. How to Maintain Log Lifecycle

### 4.1 Current State

No lifecycle management exists. No rotation, no retention, no cleanup, no size bounds.

### 4.2 Rotation Strategy

| Environment | Strategy | Implementation |
|-------------|----------|----------------|
| **Container (Docker/K8s)** | stdout only; runtime handles rotation | `structlog.JSONRenderer()` → stdout; Docker `log-opts: max-size=10m, max-file=5` |
| **Systemd service** | stdout → journald; `logrotate` for files | `StandardOutput=journal`; `/etc/logrotate.d/apex-autopilot` |
| **Local development** | `RotatingFileHandler` | 10MB × 5 backups = 60MB max per service |
| **Bare metal / VM** | `TimedRotatingFileHandler` | Daily rotation, 30-day retention |

### 4.3 Retention Policy

```
Hot storage (queryable):     7 days   → Loki / Elasticsearch
Warm storage (searchable):  30 days  → S3 / GCS with index
Cold storage (archive):     90 days  → S3 Glacier / GCS Archive
Compliance archive:         1 year   → S3 Glacier Deep Archive (if required by aviation regs)
```

### 4.4 Logrotate Configuration (Non-Container)

```ini
# /etc/logrotate.d/apex-autopilot
/var/log/apex-autopilot/*.log {
    daily
    rotate 30
    maxsize 100M
    compress
    delaycompress
    missingok
    notifempty
    create 0644 apex apex
    sharedscripts
    postrotate
        systemctl reload apex-autopilot 2>/dev/null || true
    endscript
}
```

### 4.5 Structured Log Entry Schema

Every log entry should conform to a consistent schema for aggregation:

```json
{
  "timestamp": "2026-10-04T12:30:15.000000Z",
  "level": "info",
  "service": "apex-autopilot",
  "logger": "apex_autopilot_optimization.planning.astar",
  "event": "planning_complete",
  "request_id": "req-abc123",
  "trace_id": "trace-def456",
  "duration_ms": 312,
  "algorithm": "astar",
  "nodes_explored": 1523,
  "path_length": 45.67,
  "status": "success"
}
```

**Fields:**
- `timestamp` — ISO 8601 UTC (lexicographically sortable)
- `level` — `debug` | `info` | `warning` | `error` | `critical`
- `service` — service name from config
- `logger` — module name (`__name__`)
- `event` — event identifier (snake_case, e.g. `planning_complete`)
- `request_id` — correlation ID (bound via contextvars)
- `trace_id` — distributed trace ID (if OpenTelemetry enabled)
- `duration_ms` — operation latency (for performance debugging)
- Additional domain-specific fields as key-value pairs

### 4.6 Cardinality Management

High-cardinality fields (user IDs, request IDs) should be used sparingly in log labels/metrics. Best practice:
- **Logs**: include full context (request_id, user_id) — logs are append-only and cheap
- **Metrics**: use low-cardinality labels only (service, status, algorithm) — high cardinality explodes Prometheus storage

---

## 5. Implementation Roadmap

### Phase 1: Critical — Make Logging Work (1–2 days)

1. Replace `StructuredLogger._log()` to actually emit via structlog
2. Add `setup_logging()` function with console + file handlers
3. Call `setup_logging()` in `cli.py` entrypoint
4. Add `structlog.contextvars` binding for request IDs
5. Update `test_observability.py` to verify logs are emitted (not just returned)

### Phase 2: High — Structured Output & Rotation (2–3 days)

6. Configure `structlog.JSONRenderer()` for production, `ConsoleRenderer()` for dev
7. Add `RotatingFileHandler` with 10MB × 5 backups
8. Add `dictConfig` alternative for YAML-based log configuration
9. Add exception serialization (`format_exc_info` processor)

### Phase 3: Medium — Metrics Export (3–5 days)

10. Integrate `prometheus-client` with `MetricCollector`
11. Add `/metrics` HTTP endpoint (optional, for non-container deployments)
12. Add OpenTelemetry tracing spans for planning/control/estimation pipelines

### Phase 4: Low — Aggregation & Lifecycle (5–7 days)

13. Add Fluentd/Vector configuration for log shipping
14. Add logrotate configuration for bare-metal deployments
15. Document retention policy and compliance considerations
16. Add Sentry integration for error tracking

---

## 6. Dependency Changes

| Package | Current | Action | Reason |
|---------|---------|--------|--------|
| `structlog>=24.1.0,<25.0.0` | In `pyproject.toml` | **Use it** | Already declared, never imported |
| `prometheus-client` | Not installed | **Add to dependencies** | Metrics export |
| `opentelemetry-sdk` | Not installed | **Add to optional-dependencies** | Distributed tracing |
| `sentry-sdk` | Not installed | **Add to optional-dependencies** | Error tracking |

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking 228-line test suite | Tests fail | Keep `StructuredLogger` public API backward-compatible; `_log()` still returns dict |
| Log volume explosion | Disk full, performance degradation | `RotatingFileHandler` with strict bounds; DEBUG off in production; sample high-frequency events |
| PII in logs | GDPR/aviation compliance violation | Add `structlog.processors` to redact known PII fields; document what NOT to log |
| Cardinality explosion in metrics | Prometheus storage bloat | Use low-cardinality labels only; full context in logs only |
| Thread safety in `MetricCollector` | Race conditions in concurrent planning | Add `threading.Lock` around metric mutations |

---

## 8. References

- [structlog documentation](https://www.structlog.org/en/stable/)
- [Python logging best practices](https://docs.python.org/3/howto/logging.html)
- [Twelve-Factor App: Logs](https://12factor.net/logs)
- [Prometheus Python client](https://github.com/prometheus/client_python)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
