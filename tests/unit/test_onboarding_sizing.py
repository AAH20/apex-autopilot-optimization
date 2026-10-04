"""Tests for onboarding and sizing system."""

from apex_autopilot_optimization.onboarding.sizing import (
    MODULE_REGISTRY,
    SIZING_PROFILES,
    ModuleTier,
    OrganizationScale,
    compare_scales,
    generate_config_yaml,
    generate_onboarding_checklist,
    get_available_modules,
    get_module_dependencies,
    get_profile,
    validate_module_selection,
)


class TestOrganizationScale:
    """Tests for OrganizationScale enum."""

    def test_scale_values(self):
        assert OrganizationScale.STARTUP.value == "startup"
        assert OrganizationScale.SMB.value == "smb"
        assert OrganizationScale.MID_MARKET.value == "mid_market"
        assert OrganizationScale.ENTERPRISE.value == "enterprise"
        assert OrganizationScale.LARGE_ENTERPRISE.value == "large"

    def test_scale_ordering(self):
        scales = list(OrganizationScale)
        assert scales[0] == OrganizationScale.STARTUP
        assert scales[-1] == OrganizationScale.LARGE_ENTERPRISE


class TestModuleRegistry:
    """Tests for MODULE_REGISTRY."""

    def test_all_modules_present(self):
        expected = {
            "core_types",
            "astar",
            "rrt",
            "prm",
            "hybrid_astar",
            "minimum_snap",
            "ekf",
            "task_allocation",
            "formation",
            "cbf",
            "mpc",
        }
        assert set(MODULE_REGISTRY.keys()) == expected

    def test_core_types_is_core_tier(self):
        assert MODULE_REGISTRY["core_types"].tier == ModuleTier.CORE

    def test_astar_is_core_tier(self):
        assert MODULE_REGISTRY["astar"].tier == ModuleTier.CORE

    def test_hybrid_astar_is_advanced_tier(self):
        assert MODULE_REGISTRY["hybrid_astar"].tier == ModuleTier.ADVANCED

    def test_mpc_is_advanced_tier(self):
        assert MODULE_REGISTRY["mpc"].tier == ModuleTier.ADVANCED

    def test_min_scale_startup(self):
        startup_modules = [
            name for name, m in MODULE_REGISTRY.items() if m.min_scale == OrganizationScale.STARTUP
        ]
        assert "core_types" in startup_modules
        assert "astar" in startup_modules
        assert "minimum_snap" in startup_modules
        assert "ekf" in startup_modules

    def test_min_scale_smb(self):
        smb_modules = [
            name for name, m in MODULE_REGISTRY.items() if m.min_scale == OrganizationScale.SMB
        ]
        assert "prm" in smb_modules
        assert "cbf" in smb_modules

    def test_min_scale_mid_market(self):
        mm_modules = [
            name
            for name, m in MODULE_REGISTRY.items()
            if m.min_scale == OrganizationScale.MID_MARKET
        ]
        assert "hybrid_astar" in mm_modules
        assert "task_allocation" in mm_modules
        assert "formation" in mm_modules
        assert "mpc" in mm_modules

    def test_astar_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["astar"].dependencies

    def test_rrt_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["rrt"].dependencies

    def test_prm_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["prm"].dependencies

    def test_hybrid_astar_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["hybrid_astar"].dependencies

    def test_minimum_snap_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["minimum_snap"].dependencies

    def test_ekf_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["ekf"].dependencies

    def test_task_allocation_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["task_allocation"].dependencies

    def test_formation_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["formation"].dependencies

    def test_cbf_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["cbf"].dependencies

    def test_mpc_depends_on_core_types(self):
        assert "core_types" in MODULE_REGISTRY["mpc"].dependencies

    def test_core_types_has_no_dependencies(self):
        assert len(MODULE_REGISTRY["core_types"].dependencies) == 0


class TestSizingProfiles:
    """Tests for SIZING_PROFILES."""

    def test_all_scales_have_profiles(self):
        for scale in OrganizationScale:
            assert scale in SIZING_PROFILES

    def test_startup_profile(self):
        profile = SIZING_PROFILES[OrganizationScale.STARTUP]
        assert profile.scale == OrganizationScale.STARTUP
        assert "core_types" in profile.modules
        assert "astar" in profile.modules
        assert "minimum_snap" in profile.modules
        assert "ekf" in profile.modules

    def test_startup_excludes_advanced(self):
        profile = SIZING_PROFILES[OrganizationScale.STARTUP]
        assert "hybrid_astar" not in profile.modules
        assert "mpc" not in profile.modules
        assert "task_allocation" not in profile.modules

    def test_smb_profile(self):
        profile = SIZING_PROFILES[OrganizationScale.SMB]
        assert "prm" in profile.modules
        assert "cbf" in profile.modules

    def test_mid_market_profile(self):
        profile = SIZING_PROFILES[OrganizationScale.MID_MARKET]
        assert "hybrid_astar" in profile.modules
        assert "mpc" in profile.modules
        assert "task_allocation" in profile.modules
        assert "formation" in profile.modules

    def test_enterprise_profile(self):
        profile = SIZING_PROFILES[OrganizationScale.ENTERPRISE]
        assert profile.config_defaults.get("audit_log") is True
        assert profile.config_defaults.get("metrics_enabled") is True

    def test_large_enterprise_profile(self):
        profile = SIZING_PROFILES[OrganizationScale.LARGE_ENTERPRISE]
        assert profile.config_defaults.get("distributed") is True
        assert profile.config_defaults.get("ha_enabled") is True

    def test_setup_time_increases_with_scale(self):
        times = [SIZING_PROFILES[scale].estimated_setup_time_min for scale in OrganizationScale]
        assert times == sorted(times)
        assert times[0] < times[-1]

    def test_startup_setup_time(self):
        assert SIZING_PROFILES[OrganizationScale.STARTUP].estimated_setup_time_min == 5

    def test_large_enterprise_setup_time(self):
        assert SIZING_PROFILES[OrganizationScale.LARGE_ENTERPRISE].estimated_setup_time_min == 120

    def test_onboarding_steps_present(self):
        for scale in OrganizationScale:
            profile = SIZING_PROFILES[scale]
            assert len(profile.onboarding_steps) > 0

    def test_config_defaults_present(self):
        for scale in OrganizationScale:
            profile = SIZING_PROFILES[scale]
            assert len(profile.config_defaults) > 0


class TestGetProfile:
    """Tests for get_profile function."""

    def test_get_startup_profile(self):
        profile = get_profile(OrganizationScale.STARTUP)
        assert profile.scale == OrganizationScale.STARTUP

    def test_get_smb_profile(self):
        profile = get_profile(OrganizationScale.SMB)
        assert profile.scale == OrganizationScale.SMB

    def test_get_mid_market_profile(self):
        profile = get_profile(OrganizationScale.MID_MARKET)
        assert profile.scale == OrganizationScale.MID_MARKET

    def test_get_enterprise_profile(self):
        profile = get_profile(OrganizationScale.ENTERPRISE)
        assert profile.scale == OrganizationScale.ENTERPRISE

    def test_get_large_enterprise_profile(self):
        profile = get_profile(OrganizationScale.LARGE_ENTERPRISE)
        assert profile.scale == OrganizationScale.LARGE_ENTERPRISE


class TestGetAvailableModules:
    """Tests for get_available_modules function."""

    def test_startup_modules(self):
        modules = get_available_modules(OrganizationScale.STARTUP)
        names = {m.name for m in modules}
        assert "core_types" in names
        assert "astar" in names
        assert "rrt" in names
        assert "minimum_snap" in names
        assert "ekf" in names

    def test_startup_excludes_advanced(self):
        modules = get_available_modules(OrganizationScale.STARTUP)
        names = {m.name for m in modules}
        assert "hybrid_astar" not in names
        assert "mpc" not in names

    def test_smb_includes_prm(self):
        modules = get_available_modules(OrganizationScale.SMB)
        names = {m.name for m in modules}
        assert "prm" in names
        assert "cbf" in names

    def test_mid_market_includes_all(self):
        modules = get_available_modules(OrganizationScale.MID_MARKET)
        names = {m.name for m in modules}
        assert "hybrid_astar" in names
        assert "mpc" in names
        assert "task_allocation" in names
        assert "formation" in names

    def test_module_count_increases_with_scale(self):
        counts = [len(get_available_modules(scale)) for scale in OrganizationScale]
        assert counts == sorted(counts)


class TestGetModuleDependencies:
    """Tests for get_module_dependencies function."""

    def test_core_types_no_dependencies(self):
        assert get_module_dependencies("core_types") == []

    def test_astar_depends_on_core_types(self):
        deps = get_module_dependencies("astar")
        assert "core_types" in deps

    def test_rrt_depends_on_core_types(self):
        deps = get_module_dependencies("rrt")
        assert "core_types" in deps

    def test_unknown_module_returns_empty(self):
        assert get_module_dependencies("unknown") == []


class TestValidateModuleSelection:
    """Tests for validate_module_selection function."""

    def test_valid_startup_selection(self):
        is_valid, errors = validate_module_selection(
            OrganizationScale.STARTUP,
            ["core_types", "astar", "minimum_snap", "ekf"],
        )
        assert is_valid is True
        assert len(errors) == 0

    def test_valid_smb_selection(self):
        is_valid, errors = validate_module_selection(
            OrganizationScale.SMB,
            ["core_types", "astar", "rrt", "prm", "minimum_snap", "ekf", "cbf"],
        )
        assert is_valid is True
        assert len(errors) == 0

    def test_invalid_unknown_module(self):
        is_valid, errors = validate_module_selection(
            OrganizationScale.STARTUP,
            ["core_types", "unknown_module"],
        )
        assert is_valid is False
        assert any("Unknown module" in e for e in errors)

    def test_invalid_scale_mismatch(self):
        is_valid, errors = validate_module_selection(
            OrganizationScale.STARTUP,
            ["hybrid_astar"],
        )
        assert is_valid is False
        assert any("requires scale" in e for e in errors)

    def test_invalid_missing_dependency(self):
        is_valid, errors = validate_module_selection(
            OrganizationScale.STARTUP,
            ["astar"],  # missing core_types
        )
        assert is_valid is False
        assert any("depends on" in e for e in errors)

    def test_empty_selection_valid(self):
        is_valid, errors = validate_module_selection(
            OrganizationScale.STARTUP,
            [],
        )
        assert is_valid is True
        assert len(errors) == 0


class TestGenerateConfigYaml:
    """Tests for generate_config_yaml function."""

    def test_startup_config(self):
        yaml = generate_config_yaml(OrganizationScale.STARTUP)
        assert "scale: startup" in yaml
        assert "core_types" in yaml
        assert "astar" in yaml

    def test_smb_config(self):
        yaml = generate_config_yaml(OrganizationScale.SMB)
        assert "scale: smb" in yaml
        assert "prm" in yaml
        assert "cbf" in yaml

    def test_enterprise_config(self):
        yaml = generate_config_yaml(OrganizationScale.ENTERPRISE)
        assert "scale: enterprise" in yaml
        assert "audit_log: true" in yaml
        assert "metrics_enabled: true" in yaml

    def test_large_enterprise_config(self):
        yaml = generate_config_yaml(OrganizationScale.LARGE_ENTERPRISE)
        assert "scale: large" in yaml
        assert "distributed: true" in yaml
        assert "ha_enabled: true" in yaml

    def test_config_includes_onboarding(self):
        yaml = generate_config_yaml(OrganizationScale.STARTUP)
        assert "onboarding:" in yaml
        assert "steps:" in yaml


class TestGenerateOnboardingChecklist:
    """Tests for generate_onboarding_checklist function."""

    def test_startup_checklist(self):
        checklist = generate_onboarding_checklist(OrganizationScale.STARTUP)
        assert "Startup" in checklist
        assert "5 minutes" in checklist
        assert "[ ]" in checklist

    def test_enterprise_checklist(self):
        checklist = generate_onboarding_checklist(OrganizationScale.ENTERPRISE)
        assert "Enterprise" in checklist
        assert "60 minutes" in checklist
        assert "governance" in checklist.lower()

    def test_checklist_has_verification_section(self):
        checklist = generate_onboarding_checklist(OrganizationScale.STARTUP)
        assert "Verification" in checklist

    def test_checklist_has_next_steps_section(self):
        checklist = generate_onboarding_checklist(OrganizationScale.STARTUP)
        assert "Next Steps" in checklist


class TestCompareScales:
    """Tests for compare_scales function."""

    def test_all_scales_present(self):
        result = compare_scales()
        assert set(result.keys()) == {"startup", "smb", "mid_market", "enterprise", "large"}

    def test_startup_has_fewest_modules(self):
        result = compare_scales()
        counts = [result[s]["module_count"] for s in result]
        assert counts == sorted(counts)

    def test_setup_time_increases(self):
        result = compare_scales()
        times = [result[s]["setup_time_min"] for s in result]
        assert times == sorted(times)

    def test_hardware_recommendations_present(self):
        result = compare_scales()
        for scale_data in result.values():
            assert "hardware" in scale_data
            assert len(scale_data["hardware"]) > 0
