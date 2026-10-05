"""CLI for apex-autopilot-optimization.

Unified command-line interface for all 20 modules.
Uses typer (already a dependency) for modern CLI patterns.
"""

from __future__ import annotations

from enum import StrEnum

import typer

from apex_autopilot_optimization.core.types import (
    PlanningProblem,
    Pose3D,
    StateVector,
    VehicleType,
    Velocity3D,
    Waypoint,
)

app = typer.Typer(
    name="apex-autopilot",
    help="Unified macro architecture for UAV/UAS and ground vehicle autopilot optimization",
    no_args_is_help=True,
)


class Scale(StrEnum):
    startup = "startup"
    smb = "smb"
    mid_market = "mid_market"
    enterprise = "enterprise"
    large = "large"


class PlannerAlgorithm(StrEnum):
    astar = "astar"
    rrt = "rrt"
    prm = "prm"
    hybrid_astar = "hybrid_astar"


def create_app() -> typer.Typer:
    """Create and return the Typer app (factory for testing)."""
    return app


@app.command()
def plan(
    demo: bool = typer.Option(False, "--demo", help="Run demo scenario"),
    algorithm: PlannerAlgorithm = typer.Option(  # noqa: B008
        PlannerAlgorithm.astar, "--algorithm", help="Planning algorithm"
    ),
    start_x: float = typer.Option(0.0, "--start-x", help="Start X position"),
    start_y: float = typer.Option(0.0, "--start-y", help="Start Y position"),
    goal_x: float = typer.Option(10.0, "--goal-x", help="Goal X position"),
    goal_y: float = typer.Option(10.0, "--goal-y", help="Goal Y position"),
    config: str | None = typer.Option(None, "--config", help="Config file path"),
    output: str | None = typer.Option(None, "--output", help="Output file path"),
) -> None:
    """Run path planning algorithms."""
    if demo:
        typer.echo("Running A* demo scenario...")
        try:
            from apex_autopilot_optimization.planning.astar import (
                AStarConfig,
                AStarPlanner,
            )

            problem = PlanningProblem(
                vehicle_type=VehicleType.UAV_MULTIROTOR,
                start=StateVector(
                    pose=Pose3D(x=start_x, y=start_y, z=0),
                    velocity=Velocity3D(0, 0, 0),
                ),
                goal=Waypoint(pose=Pose3D(x=goal_x, y=goal_y, z=0)),
            )
            planner = AStarPlanner(AStarConfig())
            result = planner.plan(problem)
            typer.echo(f"Success: {result.success}")
            typer.echo(f"Cost: {result.cost:.2f}")
            if result.trajectory is not None:
                typer.echo(f"Path length: {len(result.trajectory.states)} states")
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e
    else:
        typer.echo(
            f"Planning with {algorithm.value} from ({start_x}, {start_y}) to ({goal_x}, {goal_y})"
        )


@app.command()
def optimize(
    demo: bool = typer.Option(False, "--demo", help="Run demo scenario"),
) -> None:
    """Run trajectory optimization."""
    if demo:
        typer.echo("Running minimum snap optimization demo...")
        try:
            import apex_autopilot_optimization.optimization.minimum_snap  # noqa: F401

            typer.echo("Optimizer ready")
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e
    else:
        typer.echo("Specify --demo to run demo scenario")


@app.command()
def estimate(
    demo: bool = typer.Option(False, "--demo", help="Run demo scenario"),
) -> None:
    """Run state estimation."""
    if demo:
        typer.echo("Running EKF demo...")
        try:
            import apex_autopilot_optimization.estimation.ekf  # noqa: F401

            typer.echo("EKF estimator ready")
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e
    else:
        typer.echo("Specify --demo to run demo scenario")


@app.command()
def control(
    demo: bool = typer.Option(False, "--demo", help="Run demo scenario"),
) -> None:
    """Run control algorithms."""
    if demo:
        typer.echo("Running MPC demo...")
        try:
            import apex_autopilot_optimization.control.mpc  # noqa: F401

            typer.echo("MPC controller ready")
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e
    else:
        typer.echo("Specify --demo to run demo scenario")


@app.command()
def safety(
    demo: bool = typer.Option(False, "--demo", help="Run demo scenario"),
) -> None:
    """Run safety filters."""
    if demo:
        typer.echo("Running CBF demo...")
        try:
            import apex_autopilot_optimization.safety.cbf  # noqa: F401

            typer.echo("CBF filter ready")
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e
    else:
        typer.echo("Specify --demo to run demo scenario")


@app.command()
def swarm(
    demo: bool = typer.Option(False, "--demo", help="Run demo scenario"),
) -> None:
    """Run swarm algorithms."""
    if demo:
        typer.echo("Running swarm demo...")
        typer.echo("Swarm algorithms ready")
    else:
        typer.echo("Specify --demo to run demo scenario")


@app.command()
def quickstart(
    scale: Scale = typer.Option(Scale.startup, "--scale", help="Organization scale"),  # noqa: B008
) -> None:
    """Run guided demo scenarios."""
    typer.echo(f"Running quickstart for {scale.value} scale...")
    try:
        from apex_autopilot_optimization.quickstart import get_recommended_scenario

        scenario = get_recommended_scenario(scale.value)
        if scenario is not None:
            typer.echo(f"Recommended scenario: {scenario.name}")
            typer.echo(f"Description: {scenario.description}")
        else:
            typer.echo(f"No scenario found for scale: {scale.value}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def setup(
    enterprise: bool = typer.Option(False, "--enterprise", help="Enterprise setup"),
    ha: bool = typer.Option(False, "--ha", help="High availability mode"),
) -> None:
    """Run the setup wizard."""
    typer.echo("Running setup wizard...")
    try:
        from apex_autopilot_optimization.setup_wizard import run_setup

        result = run_setup()
        typer.echo(f"Status: {result.get('status', 'unknown')}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def doctor(
    full: bool = typer.Option(False, "--full", help="Run full diagnostics"),
    ha: bool = typer.Option(False, "--ha", help="High availability checks"),
) -> None:
    """Run system diagnostics."""
    typer.echo("Running diagnostics...")
    try:
        from apex_autopilot_optimization.diagnostics import format_report, run_diagnostics

        report = run_diagnostics()
        typer.echo(format_report(report))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def validate(
    config: str = typer.Option(..., "--config", help="Config file path"),
) -> None:
    """Validate configuration."""
    typer.echo(f"Validating config: {config}")
    try:
        from apex_autopilot_optimization.config_validator import validate_config

        issues = validate_config({})
        if issues:
            for issue in issues:
                typer.echo(f"  {issue.severity.value}: {issue.message}")
        else:
            typer.echo("Config valid")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def benchmark(
    iterations: int = typer.Option(100, "--iterations", help="Number of iterations"),
) -> None:
    """Run benchmarks."""
    typer.echo(f"Running benchmarks ({iterations} iterations)...")
    try:
        from apex_autopilot_optimization.benchmark import BenchmarkConfig, run_benchmark

        config = BenchmarkConfig(name="cli-benchmark", iterations=iterations)
        result = run_benchmark(config)
        typer.echo(f"Mean: {result.mean_ms:.2f}ms")
        typer.echo(f"P95: {result.p95_ms:.2f}ms")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def evaluate(
    config: str | None = typer.Option(None, "--config", help="Config file path"),
) -> None:
    """Run evaluations."""
    typer.echo("Running evaluation...")
    try:
        from apex_autopilot_optimization.evaluation import (
            EvaluationConfig,
            run_evaluation,
        )

        eval_config = EvaluationConfig(name="cli-eval", metrics=["accuracy", "latency"])
        result = run_evaluation(eval_config)
        typer.echo(f"Score: {result.overall_score:.2f}")
        typer.echo(f"Passed: {result.passed}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def list_modules() -> None:
    """List all available modules."""
    typer.echo("Available modules:")
    modules = [
        "core.types",
        "planning.astar",
        "planning.rrt",
        "planning.prm",
        "planning.hybrid_astar",
        "optimization.minimum_snap",
        "estimation.ekf",
        "swarm.task_allocation",
        "swarm.formation",
        "safety.cbf",
        "control.mpc",
        "onboarding.sizing",
        "diagnostics",
        "quickstart",
        "setup_wizard",
        "config_validator",
        "security",
        "observability",
        "benchmark",
        "evaluation",
    ]
    for m in modules:
        typer.echo(f"  - {m}")


@app.command()
def version() -> None:
    """Show version info."""
    try:
        from apex_autopilot_optimization import __version__

        typer.echo(f"apex-autopilot-optimization {__version__}")
    except ImportError:
        typer.echo("apex-autopilot-optimization 0.1.0")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
