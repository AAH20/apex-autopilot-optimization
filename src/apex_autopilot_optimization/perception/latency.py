"""LatencyTracker: per-stage timing against the 100 ms end-to-end budget.

Implements Section 7 of the perception pipeline spec. Ten stages, budgets
totalling 100 ms, p95 target 92 ms (8 ms margin to the hard ceiling).

Usage::

    tracker = LatencyTracker.from_config(config)
    with tracker.stage("ingestion"):
        ...do ingestion work...
    tracker.assert_budgets()   # per-stage p95 <= budget
    tracker.assert_end_to_end()  # end-to-end p95 <= p95_target_ms
"""

from __future__ import annotations

import time
from typing import Any

from apex_autopilot_optimization.perception import Extrinsics  # noqa: F401  (re-export convenience)

# The 10 budget stages (ms) from the spec; order matters for end-to-end sum.
STAGE_BUDGETS_MS: dict[str, float] = {
    "camera_to_topic": 8,
    "inference": 44,
    "transport": 6,
    "ingestion": 2,
    "filtering": 4,
    "fusion": 10,
    "transform": 4,
    "publish": 2,
    "wta_solve": 12,
    "control_dispatch": 8,
}
TOTAL_BUDGET_MS = 100.0
P95_TARGET_MS = 92.0


class _StageTimer:
    def __init__(self, tracker: LatencyTracker, name: str) -> None:
        self._tracker = tracker
        self._name = name
        self._start = 0.0

    def __enter__(self) -> _StageTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        elapsed_ms = (time.perf_counter() - self._start) * 1000.0
        self._tracker.record(self._name, elapsed_ms)


class LatencyTracker:
    """Records per-stage latency samples and checks budgets."""

    def __init__(
        self, budgets: dict[str, float] | None = None, p95_target_ms: float = P95_TARGET_MS
    ) -> None:
        self.budgets = dict(budgets) if budgets is not None else dict(STAGE_BUDGETS_MS)
        self.p95_target_ms = float(p95_target_ms)
        self._samples: dict[str, list[float]] = {name: [] for name in self.budgets}
        self._active: dict[str, float] = {}

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> LatencyTracker:
        budget_ms = config.get("latency_budget_ms", {})
        budgets = {
            name: float(budget_ms.get(name, default)) for name, default in STAGE_BUDGETS_MS.items()
        }
        p95_target = float(budget_ms.get("p95_target_ms", P95_TARGET_MS))
        return cls(budgets=budgets, p95_target_ms=p95_target)

    def stage(self, name: str) -> _StageTimer:
        """Context manager timing a single stage."""
        return _StageTimer(self, name)

    def record(self, name: str, elapsed_ms: float) -> None:
        if name in self._samples:
            self._samples[name].append(float(elapsed_ms))

    def start(self, name: str) -> None:
        """Manual start (pair with ``stop``)."""
        self._active[name] = time.perf_counter()

    def stop(self, name: str) -> float:
        """Manual stop; returns elapsed ms and records the sample."""
        start = self._active.pop(name, None)
        if start is None:
            return 0.0
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self.record(name, elapsed_ms)
        return elapsed_ms

    def p95(self, name: str) -> float:
        samples = sorted(self._samples.get(name, []))
        if not samples:
            return 0.0
        k = max(0, min(len(samples) - 1, int(__import__("math").ceil(0.95 * len(samples))) - 1))
        return float(samples[k])

    def stage_over_budget(self, name: str) -> bool:
        return name in self.budgets and self.p95(name) > self.budgets[name]

    def assert_budgets(self) -> None:
        """Assert every stage's p95 <= its budget (fail on first overrun)."""
        for name, budget in self.budgets.items():
            p = self.p95(name)
            assert p <= budget, f"latency stage '{name}' p95={p:.2f}ms exceeds budget={budget}ms"

    def end_to_end_ms(self) -> float:
        return sum(self.p95(name) for name in self.budgets)

    def assert_end_to_end(self) -> None:
        total = self.end_to_end_ms()
        assert total <= self.p95_target_ms, (
            f"end-to-end latency p95={total:.2f}ms exceeds p95_target={self.p95_target_ms}ms"
        )
