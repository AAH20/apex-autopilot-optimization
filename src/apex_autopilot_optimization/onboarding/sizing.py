"""Onboarding and sizing system for apex-autopilot-optimization.

Provides organization-scale-aware module selection, configuration profiles,
and onboarding guidance tailored from startups to large enterprises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class OrganizationScale(str, Enum):
    """Organization scale tiers."""

    STARTUP = "startup"           # 1-3 people
    SMB = "smb"                   # 3-10 people
    MID_MARKET = "mid_market"     # 10-30 people
    ENTERPRISE = "enterprise"     # 30-100 people
    LARGE_ENTERPRISE = "large"    # 100+ people


class ModuleTier(str, Enum):
    """Module availability tiers."""

    CORE = "core"                 # Always included
    STANDARD = "standard"         # Included in most profiles
    ADVANCED = "advanced"         # Requires explicit opt-in
    ENTERPRISE = "enterprise"     # Enterprise-only
    EXPERIMENTAL = "experimental" # Early access


@dataclass(frozen=True)
class ModuleInfo:
    """Metadata for a selectable module."""

    name: str
    tier: ModuleTier
    description: str
    min_scale: OrganizationScale
    dependencies: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()
    config_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class SizingProfile:
    """Configuration profile for an organization scale."""

    scale: OrganizationScale
    label: str
    description: str
    modules: tuple[str, ...]
    config_defaults: Dict[str, Any]
    onboarding_steps: tuple[str, ...]
    estimated_setup_time_min: int
    recommended_hardware: str


# ── Module Registry ──────────────────────────────────────────────────────────

MODULE_REGISTRY: Dict[str, ModuleInfo] = {
    "core_types": ModuleInfo(
        name="core_types",
        tier=ModuleTier.CORE,
        description="Domain types, interfaces, and data structures",
        min_scale=OrganizationScale.STARTUP,
    ),
    "astar": ModuleInfo(
        name="astar",
        tier=ModuleTier.CORE,
        description="A* path planner (2D/3D, diagonal, weighted heuristic)",
        min_scale=OrganizationScale.STARTUP,
        dependencies=("core_types",),
    ),
    "rrt": ModuleInfo(
        name="rrt",
        tier=ModuleTier.STANDARD,
        description="RRT path planner (goal-biased, sphere obstacles)",
        min_scale=OrganizationScale.STARTUP,
        dependencies=("core_types",),
    ),
    "prm": ModuleInfo(
        name="prm",
        tier=ModuleTier.STANDARD,
        description="PRM path planner (Dijkstra on roadmap)",
        min_scale=OrganizationScale.SMB,
        dependencies=("core_types",),
    ),
    "hybrid_astar": ModuleInfo(
        name="hybrid_astar",
        tier=ModuleTier.ADVANCED,
        description="Hybrid A* planner (Ackermann steering, kinodynamic)",
        min_scale=OrganizationScale.MID_MARKET,
        dependencies=("core_types",),
    ),
    "minimum_snap": ModuleInfo(
        name="minimum_snap",
        tier=ModuleTier.STANDARD,
        description="Minimum snap trajectory optimizer (quintic polynomial)",
        min_scale=OrganizationScale.STARTUP,
        dependencies=("core_types",),
    ),
    "ekf": ModuleInfo(
        name="ekf",
        tier=ModuleTier.STANDARD,
        description="EKF state estimator (12-state, predict/update)",
        min_scale=OrganizationScale.STARTUP,
        dependencies=("core_types",),
    ),
    "task_allocation": ModuleInfo(
        name="task_allocation",
        tier=ModuleTier.ADVANCED,
        description="Greedy task allocator (priority-first, nearest)",
        min_scale=OrganizationScale.MID_MARKET,
        dependencies=("core_types",),
    ),
    "formation": ModuleInfo(
        name="formation",
        tier=ModuleTier.ADVANCED,
        description="Formation controller (line/wedge/hexagon)",
        min_scale=OrganizationScale.MID_MARKET,
        dependencies=("core_types",),
    ),
    "cbf": ModuleInfo(
        name="cbf",
        tier=ModuleTier.STANDARD,
        description="CBF safety filter (Control Barrier Function)",
        min_scale=OrganizationScale.SMB,
        dependencies=("core_types",),
    ),
    "mpc": ModuleInfo(
        name="mpc",
        tier=ModuleTier.ADVANCED,
        description="MPC controller (simplified QP)",
        min_scale=OrganizationScale.MID_MARKET,
        dependencies=("core_types",),
    ),
}


# ── Sizing Profiles ─────────────────────────────────────────────────────────

SIZING_PROFILES: Dict[OrganizationScale, SizingProfile] = {
    OrganizationScale.STARTUP: SizingProfile(
        scale=OrganizationScale.STARTUP,
        label="Startup (1-3 people)",
        description="Minimal, cost-effective, quick time-to-value",
        modules=("core_types", "astar", "rrt", "minimum_snap", "ekf"),
        config_defaults={
            "planner": "astar",
            "optimizer": "minimum_snap",
            "estimator": "ekf",
            "safety_filter": None,
            "max_iterations": 10_000,
            "log_level": "WARNING",
        },
        onboarding_steps=(
            "Install package: pip install apex-autopilot-optimization",
            "Run quickstart: python -m apex_autopilot_optimization.quickstart",
            "Run first plan: apex-autopilot plan --demo",
            "Run tests: pytest tests/ -q",
        ),
        estimated_setup_time_min=5,
        recommended_hardware="Raspberry Pi 4+ or equivalent",
    ),
    OrganizationScale.SMB: SizingProfile(
        scale=OrganizationScale.SMB,
        label="SMB (3-10 people)",
        description="Balanced capability and cost, with safety",
        modules=("core_types", "astar", "rrt", "prm", "minimum_snap", "ekf", "cbf"),
        config_defaults={
            "planner": "prm",
            "optimizer": "minimum_snap",
            "estimator": "ekf",
            "safety_filter": "cbf",
            "max_iterations": 50_000,
            "log_level": "INFO",
        },
        onboarding_steps=(
            "Install package: pip install apex-autopilot-optimization",
            "Run setup wizard: apex-autopilot setup",
            "Run diagnostics: apex-autopilot doctor",
            "Run quickstart: python -m apex_autopilot_optimization.quickstart",
            "Run first plan: apex-autopilot plan --demo",
            "Run tests: pytest tests/ -q",
        ),
        estimated_setup_time_min=15,
        recommended_hardware="Raspberry Pi 5 or Jetson Orin Nano",
    ),
    OrganizationScale.MID_MARKET: SizingProfile(
        scale=OrganizationScale.MID_MARKET,
        label="Mid-Market (10-30 people)",
        description="Full planning, control, and swarm capabilities",
        modules=(
            "core_types", "astar", "rrt", "prm", "hybrid_astar",
            "minimum_snap", "ekf", "task_allocation", "formation", "cbf", "mpc",
        ),
        config_defaults={
            "planner": "hybrid_astar",
            "optimizer": "minimum_snap",
            "estimator": "ekf",
            "safety_filter": "cbf",
            "controller": "mpc",
            "max_iterations": 100_000,
            "log_level": "INFO",
        },
        onboarding_steps=(
            "Install package: pip install apex-autopilot-optimization",
            "Run setup wizard: apex-autopilot setup",
            "Run diagnostics: apex-autopilot doctor",
            "Run quickstart: python -m apex_autopilot_optimization.quickstart",
            "Run first plan: apex-autopilot plan --demo",
            "Run swarm demo: apex-autopilot swarm --demo",
            "Run tests: pytest tests/ -q",
        ),
        estimated_setup_time_min=30,
        recommended_hardware="Jetson Orin NX or equivalent",
    ),
    OrganizationScale.ENTERPRISE: SizingProfile(
        scale=OrganizationScale.ENTERPRISE,
        label="Enterprise (30-100 people)",
        description="Governance, security, and scalability",
        modules=(
            "core_types", "astar", "rrt", "prm", "hybrid_astar",
            "minimum_snap", "ekf", "task_allocation", "formation", "cbf", "mpc",
        ),
        config_defaults={
            "planner": "hybrid_astar",
            "optimizer": "minimum_snap",
            "estimator": "ekf",
            "safety_filter": "cbf",
            "controller": "mpc",
            "max_iterations": 500_000,
            "log_level": "DEBUG",
            "audit_log": True,
            "metrics_enabled": True,
        },
        onboarding_steps=(
            "Install package: pip install apex-autopilot-optimization",
            "Run setup wizard: apex-autopilot setup --enterprise",
            "Run diagnostics: apex-autopilot doctor --full",
            "Run quickstart: python -m apex_autopilot_optimization.quickstart",
            "Run first plan: apex-autopilot plan --demo",
            "Run swarm demo: apex-autopilot swarm --demo",
            "Run tests: pytest tests/ -q",
            "Review governance: apex-autopilot governance --check",
        ),
        estimated_setup_time_min=60,
        recommended_hardware="Jetson Orin AGX or server-class",
    ),
    OrganizationScale.LARGE_ENTERPRISE: SizingProfile(
        scale=OrganizationScale.LARGE_ENTERPRISE,
        label="Large Enterprise (100+ people)",
        description="Full governance, distributed operations, and compliance",
        modules=(
            "core_types", "astar", "rrt", "prm", "hybrid_astar",
            "minimum_snap", "ekf", "task_allocation", "formation", "cbf", "mpc",
        ),
        config_defaults={
            "planner": "hybrid_astar",
            "optimizer": "minimum_snap",
            "estimator": "ekf",
            "safety_filter": "cbf",
            "controller": "mpc",
            "max_iterations": 1_000_000,
            "log_level": "DEBUG",
            "audit_log": True,
            "metrics_enabled": True,
            "distributed": True,
            "ha_enabled": True,
        },
        onboarding_steps=(
            "Install package: pip install apex-autopilot-optimization",
            "Run setup wizard: apex-autopilot setup --enterprise --ha",
            "Run diagnostics: apex-autopilot doctor --full --ha",
            "Run quickstart: python -m apex_autopilot_optimization.quickstart",
            "Run first plan: apex-autopilot plan --demo",
            "Run swarm demo: apex-autopilot swarm --demo",
            "Run tests: pytest tests/ -q",
            "Review governance: apex-autopilot governance --check --ha",
            "Configure monitoring: apex-autopilot monitor --setup",
        ),
        estimated_setup_time_min=120,
        recommended_hardware="Server-class with GPU acceleration",
    ),
}


def get_profile(scale: OrganizationScale) -> SizingProfile:
    """Get the sizing profile for an organization scale."""
    return SIZING_PROFILES[scale]


def get_available_modules(scale: OrganizationScale) -> List[ModuleInfo]:
    """Get modules available for an organization scale."""
    scale_order = list(OrganizationScale)
    scale_idx = scale_order.index(scale)
    available = []
    for module in MODULE_REGISTRY.values():
        module_idx = scale_order.index(module.min_scale)
        if module_idx <= scale_idx:
            available.append(module)
    return available


def get_module_dependencies(module_name: str) -> List[str]:
    """Get all dependencies for a module (transitive)."""
    if module_name not in MODULE_REGISTRY:
        return []
    module = MODULE_REGISTRY[module_name]
    deps = list(module.dependencies)
    for dep in module.dependencies:
        deps.extend(get_module_dependencies(dep))
    return list(dict.fromkeys(deps))  # dedupe preserving order


def validate_module_selection(
    scale: OrganizationScale, selected_modules: List[str]
) -> tuple[bool, List[str]]:
    """Validate a module selection for an organization scale.

    Returns (is_valid, list_of_errors).
    """
    errors: List[str] = []
    available = get_available_modules(scale)
    available_names = {m.name for m in available}

    for module_name in selected_modules:
        if module_name not in MODULE_REGISTRY:
            errors.append(f"Unknown module: {module_name}")
            continue
        if module_name not in available_names:
            module = MODULE_REGISTRY[module_name]
            errors.append(
                f"Module '{module_name}' requires scale '{module.min_scale.value}' "
                f"or higher (current: '{scale.value}')"
            )

    # Check dependencies
    for module_name in selected_modules:
        if module_name in MODULE_REGISTRY:
            for dep in MODULE_REGISTRY[module_name].dependencies:
                if dep not in selected_modules:
                    errors.append(
                        f"Module '{module_name}' depends on '{dep}' "
                        f"which is not selected"
                    )

    return (len(errors) == 0, errors)


def generate_config_yaml(scale: OrganizationScale) -> str:
    """Generate a YAML configuration for an organization scale."""
    profile = get_profile(scale)
    lines = [
        f"# Apex Autopilot Optimization - {profile.label}",
        f"# {profile.description}",
        f"# Estimated setup time: {profile.estimated_setup_time_min} minutes",
        f"# Recommended hardware: {profile.recommended_hardware}",
        "",
        "scale: " + scale.value,
        "modules:",
    ]
    for module_name in profile.modules:
        lines.append(f"  - {module_name}")
    lines.append("")
    lines.append("config:")
    for key, value in profile.config_defaults.items():
        if value is None:
            lines.append(f"  {key}: null")
        elif isinstance(value, bool):
            lines.append(f"  {key}: {str(value).lower()}")
        elif isinstance(value, str):
            lines.append(f"  {key}: {value}")
        else:
            lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("onboarding:")
    lines.append("  steps:")
    for step in profile.onboarding_steps:
        lines.append(f"    - {step}")
    lines.append("")
    return "\n".join(lines)


def generate_onboarding_checklist(scale: OrganizationScale) -> str:
    """Generate an onboarding checklist for an organization scale."""
    profile = get_profile(scale)
    lines = [
        f"# Onboarding Checklist - {profile.label}",
        f"",
        f"**Estimated time:** {profile.estimated_setup_time_min} minutes",
        f"**Recommended hardware:** {profile.recommended_hardware}",
        f"",
        f"## Setup",
        f"",
    ]
    for i, step in enumerate(profile.onboarding_steps, 1):
        lines.append(f"- [ ] {i}. {step}")
    lines.extend([
        "",
        "## Verification",
        "",
        "- [ ] All tests pass",
        "- [ ] Demo plan completes successfully",
        "- [ ] Diagnostics report no issues",
        "",
        "## Next Steps",
        "",
        "- [ ] Review API reference",
        "- [ ] Run example projects",
        "- [ ] Join community",
        "",
    ])
    return "\n".join(lines)


def compare_scales() -> Dict[str, Any]:
    """Compare all organization scales."""
    result: Dict[str, Any] = {}
    for scale in OrganizationScale:
        profile = get_profile(scale)
        modules = get_available_modules(scale)
        result[scale.value] = {
            "label": profile.label,
            "module_count": len(modules),
            "modules": [m.name for m in modules],
            "setup_time_min": profile.estimated_setup_time_min,
            "hardware": profile.recommended_hardware,
        }
    return result
