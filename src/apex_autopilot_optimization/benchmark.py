"""Benchmark module for apex-autopilot-optimization.

Provides benchmarking, evolution tracking, and comparison capabilities
to exceed all benchmarks with evolution parameters.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""

    name: str
    iterations: int = 100
    warmup_iterations: int = 10
    description: str = ""


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    name: str
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    iterations: int
    std_dev_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "mean_ms": self.mean_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "iterations": self.iterations,
            "std_dev_ms": self.std_dev_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
        }


class BenchmarkRunner:
    """Runs benchmarks and collects results."""

    def __init__(self, config: BenchmarkConfig) -> None:
        self.config = config

    def run(self, func: Optional[Callable[[], Any]] = None) -> BenchmarkResult:
        """Run a benchmark and return results."""
        if func is None:
            func = self._default_benchmark

        # Warmup
        for _ in range(self.config.warmup_iterations):
            func()

        # Benchmark
        times: List[float] = []
        for _ in range(self.config.iterations):
            start = time.perf_counter()
            func()
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        times.sort()
        return BenchmarkResult(
            name=self.config.name,
            mean_ms=statistics.mean(times),
            p50_ms=statistics.median(times),
            p95_ms=times[int(len(times) * 0.95)],
            p99_ms=times[int(len(times) * 0.99)],
            iterations=self.config.iterations,
            std_dev_ms=statistics.stdev(times) if len(times) > 1 else 0.0,
            min_ms=min(times),
            max_ms=max(times),
        )

    def _default_benchmark(self) -> int:
        """Default benchmark function."""
        return sum(range(100))


class EvolutionTracker:
    """Tracks evolution of benchmark results across generations."""

    def __init__(self) -> None:
        self.generations: List[Dict[str, Any]] = []

    def record_generation(self, generation: int, score: float, **metadata: Any) -> None:
        """Record a generation's score."""
        entry = {
            "generation": generation,
            "score": score,
            "timestamp": int(time.time()),
        }
        entry.update(metadata)
        self.generations.append(entry)

    def get_best_generation(self) -> Optional[Dict[str, Any]]:
        """Get the best generation."""
        if not self.generations:
            return None
        return min(self.generations, key=lambda g: g["score"])

    def get_improvement_rate(self) -> Optional[float]:
        """Get the improvement rate between first and last generation."""
        if len(self.generations) < 2:
            return None
        first = self.generations[0]["score"]
        last = self.generations[-1]["score"]
        if first == 0:
            return None
        return (first - last) / first * 100

    def get_convergence_generation(self, threshold: float = 1.0) -> Optional[int]:
        """Get the generation where improvement fell below threshold."""
        if len(self.generations) < 2:
            return None
        for i in range(1, len(self.generations)):
            prev = self.generations[i - 1]["score"]
            curr = self.generations[i]["score"]
            improvement = prev - curr
            if improvement < threshold:
                return self.generations[i]["generation"]
        return None


def run_benchmark(config: BenchmarkConfig) -> BenchmarkResult:
    """Run a benchmark with the given config."""
    runner = BenchmarkRunner(config)
    return runner.run()


def run_benchmark_suite(configs: List[BenchmarkConfig]) -> Dict[str, BenchmarkResult]:
    """Run a suite of benchmarks."""
    results: Dict[str, BenchmarkResult] = {}
    for config in configs:
        results[config.name] = run_benchmark(config)
    return results


def compare_benchmarks(
    baseline: BenchmarkResult, current: BenchmarkResult
) -> Dict[str, Any]:
    """Compare two benchmark results."""
    mean_improvement = (baseline.mean_ms - current.mean_ms) / baseline.mean_ms * 100
    p95_improvement = (baseline.p95_ms - current.p95_ms) / baseline.p95_ms * 100
    p99_improvement = (baseline.p99_ms - current.p99_ms) / baseline.p99_ms * 100

    return {
        "name": baseline.name,
        "mean_improvement_pct": round(mean_improvement, 2),
        "p95_improvement_pct": round(p95_improvement, 2),
        "p99_improvement_pct": round(p99_improvement, 2),
        "improvement_pct": round(mean_improvement, 2),
        "baseline": baseline.to_dict(),
        "current": current.to_dict(),
    }
