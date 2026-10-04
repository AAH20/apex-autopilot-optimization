"""Tests for diagnostic and health check system."""

import sys

from apex_autopilot_optimization.diagnostics import (
    DiagnosticReport,
    DiagnosticResult,
    DiagnosticStatus,
    check_control,
    check_estimators,
    check_modules,
    check_numpy,
    check_optimizers,
    check_planners,
    check_python_version,
    check_pydantic,
    check_safety,
    check_scipy,
    check_swarm,
    format_report,
    run_diagnostics,
)


class TestDiagnosticStatus:
    """Tests for DiagnosticStatus enum."""

    def test_status_values(self):
        assert DiagnosticStatus.PASS.value == "pass"
        assert DiagnosticStatus.WARN.value == "warn"
        assert DiagnosticStatus.FAIL.value == "fail"
        assert DiagnosticStatus.SKIP.value == "skip"


class TestDiagnosticResult:
    """Tests for DiagnosticResult dataclass."""

    def test_result_creation(self):
        result = DiagnosticResult(
            name="test",
            status=DiagnosticStatus.PASS,
            message="Test passed",
        )
        assert result.name == "test"
        assert result.status == DiagnosticStatus.PASS
        assert result.message == "Test passed"
        assert result.fix is None

    def test_result_with_fix(self):
        result = DiagnosticResult(
            name="test",
            status=DiagnosticStatus.FAIL,
            message="Test failed",
            fix="Try this fix",
        )
        assert result.fix == "Try this fix"


class TestDiagnosticReport:
    """Tests for DiagnosticReport dataclass."""

    def test_report_creation(self):
        results = (
            DiagnosticResult("a", DiagnosticStatus.PASS, "ok"),
            DiagnosticResult("b", DiagnosticStatus.WARN, "warn"),
            DiagnosticResult("c", DiagnosticStatus.FAIL, "fail"),
        )
        report = DiagnosticReport(
            results=results,
            python_version="3.11.0",
            platform="Linux",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert report.total == 3
        assert report.passed == 1
        assert report.warnings == 1
        assert report.failed == 1
        assert report.healthy is False

    def test_healthy_report(self):
        results = (
            DiagnosticResult("a", DiagnosticStatus.PASS, "ok"),
            DiagnosticResult("b", DiagnosticStatus.PASS, "ok"),
        )
        report = DiagnosticReport(
            results=results,
            python_version="3.11.0",
            platform="Linux",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert report.healthy is True

    def test_to_dict(self):
        results = (
            DiagnosticResult("a", DiagnosticStatus.PASS, "ok"),
        )
        report = DiagnosticReport(
            results=results,
            python_version="3.11.0",
            platform="Linux",
            timestamp="2026-01-01T00:00:00Z",
        )
        d = report.to_dict()
        assert d["summary"]["total"] == 1
        assert d["summary"]["passed"] == 1
        assert d["environment"]["python_version"] == "3.11.0"
        assert len(d["results"]) == 1


class TestCheckPythonVersion:
    """Tests for check_python_version function."""

    def test_python_version_check(self):
        result = check_python_version()
        assert result.name == "python_version"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckNumpy:
    """Tests for check_numpy function."""

    def test_numpy_check(self):
        result = check_numpy()
        assert result.name == "numpy"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckScipy:
    """Tests for check_scipy function."""

    def test_scipy_check(self):
        result = check_scipy()
        assert result.name == "scipy"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckPydantic:
    """Tests for check_pydantic function."""

    def test_pydantic_check(self):
        result = check_pydantic()
        assert result.name == "pydantic"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckModules:
    """Tests for check_modules function."""

    def test_modules_check(self):
        result = check_modules()
        assert result.name == "modules"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckPlanners:
    """Tests for check_planners function."""

    def test_planners_check(self):
        result = check_planners()
        assert result.name == "planners"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckOptimizers:
    """Tests for check_optimizers function."""

    def test_optimizers_check(self):
        result = check_optimizers()
        assert result.name == "optimizers"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckEstimators:
    """Tests for check_estimators function."""

    def test_estimators_check(self):
        result = check_estimators()
        assert result.name == "estimators"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckSafety:
    """Tests for check_safety function."""

    def test_safety_check(self):
        result = check_safety()
        assert result.name == "safety"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckControl:
    """Tests for check_control function."""

    def test_control_check(self):
        result = check_control()
        assert result.name == "control"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestCheckSwarm:
    """Tests for check_swarm function."""

    def test_swarm_check(self):
        result = check_swarm()
        assert result.name == "swarm"
        assert result.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.FAIL)


class TestRunDiagnostics:
    """Tests for run_diagnostics function."""

    def test_run_diagnostics(self):
        report = run_diagnostics()
        assert isinstance(report, DiagnosticReport)
        assert report.total >= 10
        assert report.python_version is not None
        assert report.platform is not None
        assert report.timestamp is not None

    def test_run_diagnostics_has_all_checks(self):
        report = run_diagnostics()
        names = {r.name for r in report.results}
        expected = {
            "python_version", "numpy", "scipy", "pydantic", "modules",
            "planners", "optimizers", "estimators", "safety", "control", "swarm",
        }
        assert expected.issubset(names)


class TestFormatReport:
    """Tests for format_report function."""

    def test_format_report(self):
        report = run_diagnostics()
        formatted = format_report(report)
        assert "Diagnostic Report" in formatted
        assert "Summary:" in formatted
        assert "Status:" in formatted

    def test_format_report_shows_status(self):
        report = run_diagnostics()
        formatted = format_report(report)
        if report.healthy:
            assert "HEALTHY" in formatted
        else:
            assert "ISSUES DETECTED" in formatted
