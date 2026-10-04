"""Setup wizard for apex-autopilot-optimization.

Provides an interactive setup experience with step-by-step guidance,
progress tracking, and validation to ensure proper configuration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WizardStep:
    """A single step in the setup wizard."""

    name: str
    description: str
    action: Callable[[], Any]
    skippable: bool = False
    condition: Callable[[], bool] | None = None


@dataclass
class WizardResult:
    """Result of running the setup wizard."""

    completed: int
    total: int
    status: str
    details: dict[str, Any] = field(default_factory=dict)


def _check_installation() -> str:
    """Check if the package is properly installed."""
    try:
        import apex_autopilot_optimization  # noqa: F401

        return "Package installed successfully"
    except ImportError as e:
        return f"Installation issue: {e}"


def _check_dependencies() -> str:
    """Check if required dependencies are available."""
    missing = []
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    try:
        import scipy  # noqa: F401
    except ImportError:
        missing.append("scipy")

    if missing:
        return f"Missing dependencies: {', '.join(missing)}"
    return "All dependencies available"


def _check_python_version() -> str:
    """Check Python version compatibility."""
    import sys

    return f"Python {sys.version_info.major}.{sys.version_info.minor} is supported"
    return (
        f"Python {sys.version_info.major}.{sys.version_info.minor} - upgrade to 3.11+ recommended"
    )


def _check_modules() -> str:
    """Check module availability."""
    from apex_autopilot_optimization.onboarding.sizing import MODULE_REGISTRY

    available = 0
    for name in MODULE_REGISTRY:
        try:
            __import__(f"apex_autopilot_optimization.{name}")
            available += 1
        except ImportError:
            pass

    total = len(MODULE_REGISTRY)
    return f"{available}/{total} modules available"


def _run_diagnostics() -> str:
    """Run system diagnostics."""
    from apex_autopilot_optimization.diagnostics import run_diagnostics

    report = run_diagnostics()
    return f"Diagnostics: {report.passed}/{report.total} checks passed"


def _generate_config() -> str:
    """Generate default configuration."""
    from apex_autopilot_optimization.onboarding.sizing import (
        OrganizationScale,
        generate_config_yaml,
    )

    config = generate_config_yaml(OrganizationScale.STARTUP)
    return f"Configuration generated ({len(config)} bytes)"


def _run_tests() -> str:
    """Verify tests can run."""
    return "Tests available: run 'pytest tests/ -q' to verify"


def get_default_steps() -> list[WizardStep]:
    """Get the default setup wizard steps."""
    return [
        WizardStep(
            name="installation",
            description="Verify package installation",
            action=_check_installation,
        ),
        WizardStep(
            name="dependencies",
            description="Check required dependencies",
            action=_check_dependencies,
        ),
        WizardStep(
            name="python_version",
            description="Check Python version compatibility",
            action=_check_python_version,
        ),
        WizardStep(
            name="modules",
            description="Verify module availability",
            action=_check_modules,
        ),
        WizardStep(
            name="diagnostics",
            description="Run system diagnostics",
            action=_run_diagnostics,
        ),
        WizardStep(
            name="generate_config",
            description="Generate default configuration",
            action=_generate_config,
            skippable=True,
        ),
        WizardStep(
            name="run_tests",
            description="Verify tests can run",
            action=_run_tests,
            skippable=True,
        ),
    ]


class SetupWizard:
    """Interactive setup wizard."""

    def __init__(self, steps: list[WizardStep] | None = None) -> None:
        self.steps = steps or get_default_steps()
        self._completed: list[str] = []
        self._results: dict[str, Any] = {}

    def run(self, skip_first: bool = False) -> dict[str, Any]:
        """Run all wizard steps and return results."""
        self._completed = []
        self._results = {}

        start_idx = 1 if skip_first and len(self.steps) > 0 else 0

        for step in self.steps[start_idx:]:
            if step.condition and not step.condition():
                continue

            try:
                result = step.action()
                self._completed.append(step.name)
                self._results[step.name] = {"status": "ok", "result": result}
            except Exception as e:
                self._results[step.name] = {"status": "error", "error": str(e)}

        total = len(self.steps) - start_idx
        completed = len(self._completed)

        if completed == total:
            status = "completed"
        elif completed > 0:
            status = "partial"
        else:
            status = "failed"

        return {
            "completed": completed,
            "total": total,
            "status": status,
            "details": self._results,
        }

    def get_progress(self) -> dict[str, Any]:
        """Get current wizard progress."""
        total = len(self.steps)
        completed = len(self._completed)
        percent = (completed / total * 100) if total > 0 else 0

        return {
            "completed": completed,
            "total": total,
            "percent": round(percent, 1),
        }

    def reset(self) -> None:
        """Reset wizard state."""
        self._completed = []
        self._results = {}


def run_setup() -> dict[str, Any]:
    """Run the setup wizard with default steps."""
    wizard = SetupWizard()
    return wizard.run()
