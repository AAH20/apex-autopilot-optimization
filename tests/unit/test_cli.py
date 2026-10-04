"""Tests for CLI module."""

from typer.testing import CliRunner

from apex_autopilot_optimization.cli import app, create_app, main

runner = CliRunner()


class TestCLIApp:
    """Tests for CLI application."""

    def test_create_app(self):
        """create_app returns a Typer app."""
        app = create_app()
        assert app is not None

    def test_main_callable(self):
        """Main function is callable."""
        assert callable(main)


class TestCLIVersion:
    """Tests for CLI version command."""

    def test_version(self):
        """Version command returns version string."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "apex-autopilot" in result.output


class TestCLIListModules:
    """Tests for CLI list-modules command."""

    def test_list_modules(self):
        """list-modules command returns module list."""
        result = runner.invoke(app, ["list-modules"])
        assert result.exit_code == 0
        assert "core.types" in result.output
        assert "planning.astar" in result.output


class TestCLIPlan:
    """Tests for CLI plan command."""

    def test_plan_demo(self):
        """Plan demo runs successfully."""
        result = runner.invoke(app, ["plan", "--demo"])
        assert result.exit_code == 0
        assert "Success" in result.output or "Error" in result.output

    def test_plan_with_algorithm(self):
        """Plan with algorithm flag."""
        result = runner.invoke(
            app,
            [
                "plan",
                "--algorithm",
                "astar",
                "--start-x",
                "0",
                "--start-y",
                "0",
                "--goal-x",
                "5",
                "--goal-y",
                "5",
            ],
        )
        assert result.exit_code == 0
        assert "astar" in result.output


class TestCLIOptimize:
    """Tests for CLI optimize command."""

    def test_optimize_demo(self):
        """Optimize demo runs."""
        result = runner.invoke(app, ["optimize", "--demo"])
        assert result.exit_code == 0


class TestCLIEstimate:
    """Tests for CLI estimate command."""

    def test_estimate_demo(self):
        """Estimate demo runs."""
        result = runner.invoke(app, ["estimate", "--demo"])
        assert result.exit_code == 0


class TestCLIControl:
    """Tests for CLI control command."""

    def test_control_demo(self):
        """Control demo runs."""
        result = runner.invoke(app, ["control", "--demo"])
        assert result.exit_code == 0


class TestCLISafety:
    """Tests for CLI safety command."""

    def test_safety_demo(self):
        """Safety demo runs."""
        result = runner.invoke(app, ["safety", "--demo"])
        assert result.exit_code == 0


class TestCLISwarm:
    """Tests for CLI swarm command."""

    def test_swarm_demo(self):
        """Swarm demo runs."""
        result = runner.invoke(app, ["swarm", "--demo"])
        assert result.exit_code == 0


class TestCLIQuickstart:
    """Tests for CLI quickstart command."""

    def test_quickstart_startup(self):
        """Quickstart for startup scale."""
        result = runner.invoke(app, ["quickstart", "--scale", "startup"])
        assert result.exit_code == 0
        assert "startup" in result.output


class TestCLISetup:
    """Tests for CLI setup command."""

    def test_setup(self):
        """Setup command runs."""
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0


class TestCLIDoctor:
    """Tests for CLI doctor command."""

    def test_doctor(self):
        """Doctor command runs."""
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0


class TestCLIBenchmark:
    """Tests for CLI benchmark command."""

    def test_benchmark(self):
        """Benchmark command runs."""
        result = runner.invoke(app, ["benchmark", "--iterations", "5"])
        assert result.exit_code == 0


class TestCLIEvaluate:
    """Tests for CLI evaluate command."""

    def test_evaluate(self):
        """Evaluate command runs."""
        result = runner.invoke(app, ["evaluate"])
        assert result.exit_code == 0


class TestCLIHelp:
    """Tests for CLI help."""

    def test_help(self):
        """Help command shows available commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "plan" in result.output
        assert "doctor" in result.output
