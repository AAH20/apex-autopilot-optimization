"""Apex Autopilot Optimization - Unified API facade."""

from apex_autopilot_optimization.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkRunner,
    EvolutionTracker,
    compare_benchmarks,
    run_benchmark,
    run_benchmark_suite,
)
from apex_autopilot_optimization.config_validator import (
    validate_config,
    validate_module_config,
)
from apex_autopilot_optimization.control import MPCConfig, MPCController
from apex_autopilot_optimization.core.types import (
    BottleneckReport,
    ComplexityClass,
    ControlInput,
    OptimizationConstraint,
    OptimizationObjective,
    PlanningProblem,
    PlanningResult,
    Pose3D,
    StateVector,
    Trajectory,
    VehicleType,
    Velocity3D,
    Waypoint,
)
from apex_autopilot_optimization.diagnostics import (
    DiagnosticReport,
    format_report,
    run_diagnostics,
)
from apex_autopilot_optimization.estimation import EKFConfig, EKFEstimator
from apex_autopilot_optimization.evaluation import (
    EvaluationConfig,
    EvaluationMetric,
    EvaluationResult,
    EvaluationRunner,
    MetricAggregator,
    aggregate_metrics,
    evaluate_all,
    evaluate_metric,
    run_evaluation,
)
from apex_autopilot_optimization.observability import (
    ObservabilityConfig,
    ObservabilityManager,
    check_health,
    collect_metrics,
    create_logger,
)
from apex_autopilot_optimization.onboarding import (
    MODULE_REGISTRY,
    SIZING_PROFILES,
    ModuleInfo,
    ModuleTier,
    OrganizationScale,
    SizingProfile,
    compare_scales,
    generate_config_yaml,
    generate_onboarding_checklist,
    get_available_modules,
    get_module_dependencies,
    get_profile,
    validate_module_selection,
)
from apex_autopilot_optimization.optimization import (
    MinimumSnapConfig,
    MinimumSnapOptimizer,
)
from apex_autopilot_optimization.planning import (
    AStarConfig,
    AStarPlanner,
    HybridAStarConfig,
    HybridAStarPlanner,
    PRMConfig,
    PRMPlanner,
    RRTConfig,
    RRTPlanner,
)
from apex_autopilot_optimization.quickstart import (
    SCENARIOS,
    DemoScenario,
    QuickstartRunner,
    get_recommended_scenario,
    list_scenarios,
    run_demo,
)
from apex_autopilot_optimization.safety import CBFConfig, CBFFilter
from apex_autopilot_optimization.security import (
    AuthenticationHelper,
    EncryptionHelper,
    SecurityAuditLog,
    SecurityPolicy,
    check_security_policy,
)
from apex_autopilot_optimization.setup_wizard import (
    SetupWizard,
    WizardResult,
    WizardStep,
    get_default_steps,
    run_setup,
)
from apex_autopilot_optimization.swarm import (
    Agent,
    FormationConfig,
    FormationController,
    Task,
    TaskAllocationConfig,
    TaskAllocator,
)

__version__ = "0.1.0"

__all__ = [
    # Core types
    "BottleneckReport",
    "ComplexityClass",
    "ControlInput",
    "OptimizationConstraint",
    "OptimizationObjective",
    "PlanningProblem",
    "PlanningResult",
    "Pose3D",
    "StateVector",
    "Trajectory",
    "VehicleType",
    "Velocity3D",
    "Waypoint",
    # Planning
    "AStarConfig",
    "AStarPlanner",
    "HybridAStarConfig",
    "HybridAStarPlanner",
    "PRMConfig",
    "PRMPlanner",
    "RRTConfig",
    "RRTPlanner",
    # Optimization
    "MinimumSnapConfig",
    "MinimumSnapOptimizer",
    # Estimation
    "EKFConfig",
    "EKFEstimator",
    # Control
    "MPCConfig",
    "MPCController",
    # Safety
    "CBFConfig",
    "CBFFilter",
    # Swarm
    "Agent",
    "FormationConfig",
    "FormationController",
    "Task",
    "TaskAllocationConfig",
    "TaskAllocator",
    # Onboarding
    "MODULE_REGISTRY",
    "SIZING_PROFILES",
    "ModuleInfo",
    "ModuleTier",
    "OrganizationScale",
    "SizingProfile",
    "compare_scales",
    "generate_config_yaml",
    "generate_onboarding_checklist",
    "get_available_modules",
    "get_module_dependencies",
    "get_profile",
    "validate_module_selection",
    # Diagnostics
    "DiagnosticReport",
    "format_report",
    "run_diagnostics",
    # Config validator
    "validate_config",
    "validate_module_config",
    # Security
    "AuthenticationHelper",
    "EncryptionHelper",
    "SecurityAuditLog",
    "SecurityPolicy",
    "check_security_policy",
    # Observability
    "ObservabilityConfig",
    "ObservabilityManager",
    "check_health",
    "collect_metrics",
    "create_logger",
    # Benchmark
    "BenchmarkConfig",
    "BenchmarkResult",
    "BenchmarkRunner",
    "EvolutionTracker",
    "compare_benchmarks",
    "run_benchmark",
    "run_benchmark_suite",
    # Evaluation
    "EvaluationConfig",
    "EvaluationMetric",
    "EvaluationResult",
    "EvaluationRunner",
    "MetricAggregator",
    "aggregate_metrics",
    "evaluate_all",
    "evaluate_metric",
    "run_evaluation",
    # Quickstart
    "DemoScenario",
    "QuickstartRunner",
    "SCENARIOS",
    "get_recommended_scenario",
    "list_scenarios",
    "run_demo",
    # Setup wizard
    "SetupWizard",
    "WizardResult",
    "WizardStep",
    "get_default_steps",
    "run_setup",
]
