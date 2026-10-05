"""Diagnostic and health check system for apex-autopilot-optimization.

Provides system validation, health checks, and diagnostic reporting
to help users identify and resolve configuration issues.
"""

from __future__ import annotations

import importlib
import platform
import sys
from dataclasses import dataclass
from datetime import UTC
from enum import StrEnum
from typing import Any


class DiagnosticStatus(StrEnum):
    """Status levels for diagnostic checks."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class DiagnosticResult:
    """Result of a single diagnostic check."""

    name: str
    status: DiagnosticStatus
    message: str
    fix: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class DiagnosticReport:
    """Complete diagnostic report."""

    results: tuple[DiagnosticResult, ...]
    python_version: str
    platform: str
    timestamp: str

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == DiagnosticStatus.PASS)

    @property
    def warnings(self) -> int:
        return sum(1 for r in self.results if r.status == DiagnosticStatus.WARN)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == DiagnosticStatus.FAIL)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def healthy(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "warnings": self.warnings,
                "failed": self.failed,
                "healthy": self.healthy,
            },
            "environment": {
                "python_version": self.python_version,
                "platform": self.platform,
                "timestamp": self.timestamp,
            },
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "fix": r.fix,
                    "details": r.details,
                }
                for r in self.results
            ],
        }


def check_python_version() -> DiagnosticResult:
    """Check Python version compatibility."""
    version = sys.version_info
    if version >= (3, 11):
        return DiagnosticResult(
            name="python_version",
            status=DiagnosticStatus.PASS,
            message=f"Python {version.major}.{version.minor}.{version.micro} is supported",
        )
    elif version >= (3, 10):
        return DiagnosticResult(
            name="python_version",
            status=DiagnosticStatus.WARN,
            message=f"Python {version.major}.{version.minor} works but 3.11+ recommended",
            fix="Upgrade to Python 3.11 or later",
        )
    else:
        return DiagnosticResult(
            name="python_version",
            status=DiagnosticStatus.FAIL,
            message=f"Python {version.major}.{version.minor} is not supported",
            fix="Upgrade to Python 3.11 or later",
        )


def check_numpy() -> DiagnosticResult:
    """Check NumPy installation."""
    try:
        import numpy as np

        version = np.__version__
        major, minor = map(int, version.split(".")[:2])
        if major >= 1 and minor >= 26:
            return DiagnosticResult(
                name="numpy",
                status=DiagnosticStatus.PASS,
                message=f"NumPy {version} is installed and compatible",
            )
        else:
            return DiagnosticResult(
                name="numpy",
                status=DiagnosticStatus.WARN,
                message=f"NumPy {version} is installed but 1.26+ recommended",
                fix="pip install 'numpy>=1.26.0,<2.0.0'",
            )
    except ImportError:
        return DiagnosticResult(
            name="numpy",
            status=DiagnosticStatus.FAIL,
            message="NumPy is not installed",
            fix="pip install 'numpy>=1.26.0,<2.0.0'",
        )


def check_scipy() -> DiagnosticResult:
    """Check SciPy installation."""
    try:
        import scipy

        version = scipy.__version__
        return DiagnosticResult(
            name="scipy",
            status=DiagnosticStatus.PASS,
            message=f"SciPy {version} is installed",
        )
    except ImportError:
        return DiagnosticResult(
            name="scipy",
            status=DiagnosticStatus.WARN,
            message="SciPy is not installed (required for optimization)",
            fix="pip install 'scipy>=1.12.0,<2.0.0'",
        )


def check_pydantic() -> DiagnosticResult:
    """Check Pydantic installation."""
    try:
        import pydantic

        version = pydantic.__version__
        return DiagnosticResult(
            name="pydantic",
            status=DiagnosticStatus.PASS,
            message=f"Pydantic {version} is installed",
        )
    except ImportError:
        return DiagnosticResult(
            name="pydantic",
            status=DiagnosticStatus.WARN,
            message="Pydantic is not installed (required for config validation)",
            fix="pip install 'pydantic>=2.5.0,<3.0.0'",
        )


def check_modules() -> DiagnosticResult:
    """Check core module availability."""
    from apex_autopilot_optimization.onboarding.sizing import MODULE_REGISTRY

    available = []
    missing = []
    for name in MODULE_REGISTRY:
        try:
            importlib.import_module(f"apex_autopilot_optimization.{name}")
            available.append(name)
        except ImportError:
            missing.append(name)

    if not missing:
        return DiagnosticResult(
            name="modules",
            status=DiagnosticStatus.PASS,
            message=f"All {len(available)} modules are available",
        )
    else:
        return DiagnosticResult(
            name="modules",
            status=DiagnosticStatus.WARN,
            message=f"{len(missing)} modules have import issues: {', '.join(missing[:3])}",
            fix="Reinstall package: pip install -e .",
            details={"available": available, "missing": missing},
        )


def check_planners() -> DiagnosticResult:
    """Check planner availability."""
    planners = []
    try:
        import apex_autopilot_optimization.planning.astar  # noqa: F401

        planners.append("astar")
    except ImportError:
        pass
    try:
        import apex_autopilot_optimization.planning.rrt  # noqa: F401

        planners.append("rrt")
    except ImportError:
        pass
    try:
        import apex_autopilot_optimization.planning.prm  # noqa: F401

        planners.append("prm")
    except ImportError:
        pass
    try:
        import apex_autopilot_optimization.planning.hybrid_astar  # noqa: F401

        planners.append("hybrid_astar")
    except ImportError:
        pass

    if len(planners) >= 3:
        return DiagnosticResult(
            name="planners",
            status=DiagnosticStatus.PASS,
            message=f"{len(planners)} planners available: {', '.join(planners)}",
        )
    else:
        return DiagnosticResult(
            name="planners",
            status=DiagnosticStatus.WARN,
            message=f"Only {len(planners)} planners available: {', '.join(planners)}",
            fix="Reinstall package to get all planners",
        )


def check_optimizers() -> DiagnosticResult:
    """Check optimizer availability."""
    try:
        import apex_autopilot_optimization.optimization.minimum_snap  # noqa: F401

        return DiagnosticResult(
            name="optimizers",
            status=DiagnosticStatus.PASS,
            message="Minimum snap optimizer is available",
        )
    except ImportError:
        return DiagnosticResult(
            name="optimizers",
            status=DiagnosticStatus.FAIL,
            message="Minimum snap optimizer is not available",
            fix="Reinstall package: pip install -e .",
        )


def check_estimators() -> DiagnosticResult:
    """Check estimator availability."""
    try:
        import apex_autopilot_optimization.estimation.ekf  # noqa: F401

        return DiagnosticResult(
            name="estimators",
            status=DiagnosticStatus.PASS,
            message="EKF estimator is available",
        )
    except ImportError:
        return DiagnosticResult(
            name="estimators",
            status=DiagnosticStatus.FAIL,
            message="EKF estimator is not available",
            fix="Reinstall package: pip install -e .",
        )


def check_safety() -> DiagnosticResult:
    """Check safety module availability."""
    try:
        import apex_autopilot_optimization.safety.cbf  # noqa: F401

        return DiagnosticResult(
            name="safety",
            status=DiagnosticStatus.PASS,
            message="CBF safety filter is available",
        )
    except ImportError:
        return DiagnosticResult(
            name="safety",
            status=DiagnosticStatus.WARN,
            message="CBF safety filter is not available",
            fix="Reinstall package: pip install -e .",
        )


def check_control() -> DiagnosticResult:
    """Check control module availability."""
    try:
        import apex_autopilot_optimization.control.mpc  # noqa: F401

        return DiagnosticResult(
            name="control",
            status=DiagnosticStatus.PASS,
            message="MPC controller is available",
        )
    except ImportError:
        return DiagnosticResult(
            name="control",
            status=DiagnosticStatus.WARN,
            message="MPC controller is not available",
            fix="Reinstall package: pip install -e .",
        )


def check_swarm() -> DiagnosticResult:
    """Check swarm module availability."""
    try:
        import apex_autopilot_optimization.swarm.formation  # noqa: F401
        import apex_autopilot_optimization.swarm.task_allocation  # noqa: F401

        return DiagnosticResult(
            name="swarm",
            status=DiagnosticStatus.PASS,
            message="Swarm modules (task allocation, formation) are available",
        )
    except ImportError:
        return DiagnosticResult(
            name="swarm",
            status=DiagnosticStatus.WARN,
            message="Swarm modules are not available",
            fix="Reinstall package: pip install -e .",
        )


def run_diagnostics() -> DiagnosticReport:
    """Run all diagnostic checks and return a report."""
    from datetime import datetime

    checks = [
        check_python_version(),
        check_numpy(),
        check_scipy(),
        check_pydantic(),
        check_modules(),
        check_planners(),
        check_optimizers(),
        check_estimators(),
        check_safety(),
        check_control(),
        check_swarm(),
    ]

    return DiagnosticReport(
        results=tuple(checks),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.platform(),
        timestamp=datetime.now(UTC).isoformat(),
    )


def format_report(report: DiagnosticReport) -> str:
    """Format a diagnostic report as a human-readable string."""
    lines = [
        "=" * 60,
        "Apex Autopilot Optimization - Diagnostic Report",
        "=" * 60,
        f"Python: {report.python_version}",
        f"Platform: {report.platform}",
        f"Timestamp: {report.timestamp}",
        "-" * 60,
        f"Summary: {report.passed} passed, {report.warnings} warnings, {report.failed} failed",
        f"Status: {'HEALTHY' if report.healthy else 'ISSUES DETECTED'}",
        "-" * 60,
        "",
    ]

    for result in report.results:
        icon = {
            DiagnosticStatus.PASS: "✓",
            DiagnosticStatus.WARN: "⚠",
            DiagnosticStatus.FAIL: "✗",
            DiagnosticStatus.SKIP: "○",
        }.get(result.status, "?")

        lines.append(f"{icon} {result.name}: {result.message}")
        if result.fix:
            lines.append(f"  Fix: {result.fix}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
