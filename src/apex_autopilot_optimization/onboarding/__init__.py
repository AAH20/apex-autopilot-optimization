"""Onboarding and sizing system for apex-autopilot-optimization."""

from apex_autopilot_optimization.onboarding.sizing import (
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

__all__ = [
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
]
