"""Tests for configuration management package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex_autopilot_optimization.config import (
    ConfigLayer,
    ConfigManager,
    ConfigProfile,
    deep_merge,
    load_config,
    save_config,
)
from apex_autopilot_optimization.config.env import env_var_to_config_key, load_env_config
from apex_autopilot_optimization.config.merger import resolve_config
from apex_autopilot_optimization.config.profiles import get_profile, list_profiles

# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_yaml(path: Path, data: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data))


def _write_toml(path: Path, data: dict) -> None:
    import tomli_w

    path.write_text(tomli_w.dumps(data))


# ── YAML Loading ─────────────────────────────────────────────────────────────


class TestYamlLoading:
    """Tests for YAML config loading."""

    def test_load_simple_yaml(self, tmp_path: Path):
        p = tmp_path / "config.yaml"
        _write_yaml(p, {"scale": "startup", "planner": "astar"})
        result = load_config(str(p))
        assert result["scale"] == "startup"
        assert result["planner"] == "astar"

    def test_load_nested_yaml(self, tmp_path: Path):
        p = tmp_path / "config.yaml"
        _write_yaml(p, {"planner": {"resolution_m": 1.0, "max_iterations": 100}})
        result = load_config(str(p))
        assert result["planner"]["resolution_m"] == 1.0
        assert result["planner"]["max_iterations"] == 100

    def test_load_yaml_with_list(self, tmp_path: Path):
        p = tmp_path / "config.yaml"
        _write_yaml(p, {"modules": ["astar", "rrt", "prm"]})
        result = load_config(str(p))
        assert result["modules"] == ["astar", "rrt", "prm"]

    def test_load_empty_yaml(self, tmp_path: Path):
        p = tmp_path / "config.yaml"
        p.write_text("")
        result = load_config(str(p))
        assert result == {}

    def test_load_yaml_yml_extension(self, tmp_path: Path):
        p = tmp_path / "config.yml"
        _write_yaml(p, {"key": "value"})
        result = load_config(str(p))
        assert result["key"] == "value"


# ── JSON Loading ─────────────────────────────────────────────────────────────


class TestJsonLoading:
    """Tests for JSON config loading."""

    def test_load_simple_json(self, tmp_path: Path):
        p = tmp_path / "config.json"
        _write_json(p, {"scale": "enterprise", "log_level": "DEBUG"})
        result = load_config(str(p))
        assert result["scale"] == "enterprise"
        assert result["log_level"] == "DEBUG"

    def test_load_nested_json(self, tmp_path: Path):
        p = tmp_path / "config.json"
        _write_json(p, {"optimizer": {"num_waypoints": 20, "time_horizon": 30.0}})
        result = load_config(str(p))
        assert result["optimizer"]["num_waypoints"] == 20

    def test_load_empty_json(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text("{}")
        result = load_config(str(p))
        assert result == {}


# ── TOML Loading ─────────────────────────────────────────────────────────────


class TestTomlLoading:
    """Tests for TOML config loading."""

    def test_load_simple_toml(self, tmp_path: Path):
        p = tmp_path / "config.toml"
        _write_toml(p, {"scale": "smb", "planner": "rrt"})
        result = load_config(str(p))
        assert result["scale"] == "smb"
        assert result["planner"] == "rrt"

    def test_load_nested_toml(self, tmp_path: Path):
        p = tmp_path / "config.toml"
        _write_toml(p, {"planner": {"step_size": 0.5, "max_iterations": 5000}})
        result = load_config(str(p))
        assert result["planner"]["step_size"] == 0.5
        assert result["planner"]["max_iterations"] == 5000


# ── Deep Merge ───────────────────────────────────────────────────────────────


class TestDeepMerge:
    """Tests for deep_merge function."""

    def test_merge_disjoint_keys(self):
        base = {"a": 1}
        override = {"b": 2}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_merge_override_scalar(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_merge_nested_dicts(self):
        base = {"planner": {"resolution_m": 1.0, "max_iterations": 100}}
        override = {"planner": {"max_iterations": 200}}
        result = deep_merge(base, override)
        assert result["planner"]["resolution_m"] == 1.0
        assert result["planner"]["max_iterations"] == 200

    def test_merge_nested_override(self):
        base = {"planner": {"resolution_m": 1.0}}
        override = {"planner": {"resolution_m": 0.5}}
        result = deep_merge(base, override)
        assert result["planner"]["resolution_m"] == 0.5

    def test_merge_lists_replaced(self):
        base = {"modules": ["astar", "rrt"]}
        override = {"modules": ["prm"]}
        result = deep_merge(base, override)
        assert result["modules"] == ["prm"]

    def test_merge_does_not_mutate_base(self):
        base = {"planner": {"resolution_m": 1.0}}
        override = {"planner": {"max_iterations": 200}}
        deep_merge(base, override)
        assert "max_iterations" not in base["planner"]

    def test_merge_deeply_nested(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 10}}}
        result = deep_merge(base, override)
        assert result["a"]["b"]["c"] == 10
        assert result["a"]["b"]["d"] == 2

    def test_merge_empty_override(self):
        base = {"a": 1, "b": {"c": 2}}
        result = deep_merge(base, {})
        assert result == {"a": 1, "b": {"c": 2}}

    def test_merge_empty_base(self):
        override = {"a": 1, "b": {"c": 2}}
        result = deep_merge({}, override)
        assert result == {"a": 1, "b": {"c": 2}}


# ── Config Precedence Chain ─────────────────────────────────────────────────


class TestResolveConfig:
    """Tests for resolve_config precedence chain."""

    def test_single_layer(self):
        layers = [{"a": 1}]
        result = resolve_config(layers)
        assert result == {"a": 1}

    def test_two_layers_override(self):
        layers = [{"a": 1, "b": 2}, {"b": 3}]
        result = resolve_config(layers)
        assert result == {"a": 1, "b": 3}

    def test_later_layer_wins(self):
        layers = [{"x": "first"}, {"x": "second"}, {"x": "third"}]
        result = resolve_config(layers)
        assert result["x"] == "third"

    def test_empty_layers(self):
        result = resolve_config([])
        assert result == {}

    def test_precedence_order(self):
        """DEFAULTS < USER < PROJECT < ENV < CLI."""
        layers = [
            {"scale": "startup", "log_level": "INFO", "max_iterations": 1000},
            {"scale": "smb", "max_iterations": 5000},
            {"scale": "enterprise"},
            {"log_level": "DEBUG"},
            {"max_iterations": 99999},
        ]
        result = resolve_config(layers)
        assert result["scale"] == "enterprise"
        assert result["log_level"] == "DEBUG"
        assert result["max_iterations"] == 99999

    def test_nested_precedence(self):
        layers = [
            {"planner": {"resolution_m": 1.0, "max_iterations": 100}},
            {"planner": {"resolution_m": 0.5}},
        ]
        result = resolve_config(layers)
        assert result["planner"]["resolution_m"] == 0.5
        assert result["planner"]["max_iterations"] == 100


# ── Env Var Loading ──────────────────────────────────────────────────────────


class TestEnvVarLoading:
    """Tests for environment variable config loading."""

    def test_load_env_config_basic(self, monkeypatch):
        monkeypatch.setenv("APEX_SCALE", "startup")
        monkeypatch.setenv("APEX_PLANNER", "astar")
        result = load_env_config()
        assert result["scale"] == "startup"
        assert result["planner"] == "astar"

    def test_load_env_config_custom_prefix(self, monkeypatch):
        monkeypatch.setenv("MYAPP_SCALE", "enterprise")
        result = load_env_config(prefix="MYAPP_")
        assert result["scale"] == "enterprise"

    def test_load_env_config_nested_key(self, monkeypatch):
        monkeypatch.setenv("APEX_PLANNER__RESOLUTION_M", "0.5")
        result = load_env_config()
        assert result["planner"]["resolution_m"] == 0.5

    def test_load_env_config_no_matching_vars(self, monkeypatch):
        monkeypatch.delenv("APEX_SCALE", raising=False)
        result = load_env_config()
        assert "scale" not in result

    def test_load_env_config_type_conversion_int(self, monkeypatch):
        monkeypatch.setenv("APEX_MAX_ITERATIONS", "5000")
        result = load_env_config()
        assert result["max_iterations"] == 5000

    def test_load_env_config_type_conversion_float(self, monkeypatch):
        monkeypatch.setenv("APEX_RESOLUTION_M", "0.5")
        result = load_env_config()
        assert result["resolution_m"] == 0.5

    def test_load_env_config_type_conversion_bool(self, monkeypatch):
        monkeypatch.setenv("APEX_ENABLED", "true")
        result = load_env_config()
        assert result["enabled"] is True

    def test_load_env_config_ignores_non_prefix(self, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("APEX_SCALE", "startup")
        result = load_env_config()
        assert "PATH" not in result
        assert "path" not in result


# ── Env Var to Config Key Conversion ─────────────────────────────────────────


class TestEnvVarToConfigKey:
    """Tests for env_var_to_config_key function."""

    def test_simple_key(self):
        assert env_var_to_config_key("APEX_SCALE") == "scale"

    def test_nested_key(self):
        assert env_var_to_config_key("APEX_PLANNER__RESOLUTION_M") == "planner.resolution_m"

    def test_deeply_nested(self):
        assert env_var_to_config_key("APEX_A__B__C__D") == "a.b.c.d"

    def test_strips_prefix(self):
        assert env_var_to_config_key("APEX_LOG_LEVEL", prefix="APEX_") == "log_level"

    def test_custom_prefix(self):
        assert env_var_to_config_key("MYAPP_SCALE", prefix="MYAPP_") == "scale"


# ── Config Layer Enum ────────────────────────────────────────────────────────


class TestConfigLayer:
    """Tests for ConfigLayer enum."""

    def test_layer_values(self):
        assert ConfigLayer.DEFAULTS.value == "defaults"
        assert ConfigLayer.USER.value == "user"
        assert ConfigLayer.PROJECT.value == "project"
        assert ConfigLayer.ENV.value == "env"
        assert ConfigLayer.CLI.value == "cli"

    def test_layer_ordering(self):
        layers = list(ConfigLayer)
        assert layers == [
            ConfigLayer.DEFAULTS,
            ConfigLayer.USER,
            ConfigLayer.PROJECT,
            ConfigLayer.ENV,
            ConfigLayer.CLI,
        ]


# ── Config Profile ───────────────────────────────────────────────────────────


class TestConfigProfile:
    """Tests for ConfigProfile dataclass."""

    def test_profile_creation(self):
        p = ConfigProfile(name="test", inherits=None, values={"a": 1})
        assert p.name == "test"
        assert p.inherits is None
        assert p.values == {"a": 1}

    def test_profile_with_inheritance(self):
        p = ConfigProfile(name="child", inherits="parent", values={"b": 2})
        assert p.inherits == "parent"


# ── Profile Registry ─────────────────────────────────────────────────────────


class TestProfileRegistry:
    """Tests for get_profile and list_profiles."""

    def test_get_profile_returns_profile(self):
        p = get_profile("startup")
        assert isinstance(p, ConfigProfile)
        assert p.name == "startup"

    def test_get_profile_values(self):
        p = get_profile("startup")
        assert "scale" in p.values
        assert p.values["scale"] == "startup"

    def test_get_profile_enterprise(self):
        p = get_profile("enterprise")
        assert p.values["scale"] == "enterprise"

    def test_list_profiles(self):
        profiles = list_profiles()
        assert "startup" in profiles
        assert "enterprise" in profiles

    def test_profile_inheritance(self):
        p = get_profile("enterprise")
        assert p.inherits is None or isinstance(p.inherits, str)


# ── ConfigManager ────────────────────────────────────────────────────────────


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_manager_creation(self):
        mgr = ConfigManager()
        assert mgr is not None

    def test_load(self, tmp_path: Path):
        p = tmp_path / "config.yaml"
        _write_yaml(p, {"scale": "startup", "planner": "astar"})
        mgr = ConfigManager()
        mgr.load(str(p))
        assert mgr.get("scale") == "startup"
        assert mgr.get("planner") == "astar"

    def test_save_yaml(self, tmp_path: Path):
        mgr = ConfigManager()
        mgr.set("scale", "smb")
        mgr.set("planner", "rrt")
        out = tmp_path / "out.yaml"
        mgr.save(str(out))
        assert out.exists()
        loaded = load_config(str(out))
        assert loaded["scale"] == "smb"
        assert loaded["planner"] == "rrt"

    def test_save_json(self, tmp_path: Path):
        mgr = ConfigManager()
        mgr.set("scale", "enterprise")
        out = tmp_path / "out.json"
        mgr.save(str(out))
        loaded = load_config(str(out))
        assert loaded["scale"] == "enterprise"

    def test_save_toml(self, tmp_path: Path):
        mgr = ConfigManager()
        mgr.set("scale", "mid_market")
        out = tmp_path / "out.toml"
        mgr.save(str(out))
        loaded = load_config(str(out))
        assert loaded["scale"] == "mid_market"

    def test_get_existing_key(self):
        mgr = ConfigManager()
        mgr.set("planner", "astar")
        assert mgr.get("planner") == "astar"

    def test_get_missing_key_returns_default(self):
        mgr = ConfigManager()
        assert mgr.get("nonexistent") is None
        assert mgr.get("nonexistent", "fallback") == "fallback"

    def test_set_nested_key(self):
        mgr = ConfigManager()
        mgr.set("planner.resolution_m", 0.5)
        assert mgr.get("planner.resolution_m") == 0.5

    def test_set_creates_intermediate_dicts(self):
        mgr = ConfigManager()
        mgr.set("a.b.c", 42)
        assert mgr.get("a.b.c") == 42

    def test_get_nested_key(self):
        mgr = ConfigManager()
        mgr.set("planner", {"resolution_m": 1.0, "max_iterations": 100})
        assert mgr.get("planner.resolution_m") == 1.0
        assert mgr.get("planner.max_iterations") == 100

    def test_load_then_override(self, tmp_path: Path):
        p = tmp_path / "config.yaml"
        _write_yaml(p, {"scale": "startup", "planner": "astar"})
        mgr = ConfigManager()
        mgr.load(str(p))
        mgr.set("scale", "enterprise")
        assert mgr.get("scale") == "enterprise"
        assert mgr.get("planner") == "astar"

    def test_save_then_reload(self, tmp_path: Path):
        mgr = ConfigManager()
        mgr.set("scale", "smb")
        mgr.set("planner", "prm")
        out = tmp_path / "roundtrip.yaml"
        mgr.save(str(out))

        mgr2 = ConfigManager()
        mgr2.load(str(out))
        assert mgr2.get("scale") == "smb"
        assert mgr2.get("planner") == "prm"

    def test_apply_profile(self):
        mgr = ConfigManager()
        mgr.apply_profile("startup")
        assert mgr.get("scale") == "startup"

    def test_apply_profile_overrides_existing(self):
        mgr = ConfigManager()
        mgr.set("scale", "enterprise")
        mgr.apply_profile("startup")
        assert mgr.get("scale") == "startup"

    def test_apply_profile_preserves_unrelated(self):
        mgr = ConfigManager()
        mgr.set("custom_key", "custom_value")
        mgr.apply_profile("startup")
        assert mgr.get("custom_key") == "custom_value"
        assert mgr.get("scale") == "startup"

    def test_get_profile(self):
        mgr = ConfigManager()
        p = mgr.get_profile("startup")
        assert isinstance(p, ConfigProfile)
        assert p.name == "startup"

    def test_validate_returns_list(self):
        mgr = ConfigManager()
        mgr.set("scale", "startup")
        mgr.set("planner", "astar")
        issues = mgr.validate()
        assert isinstance(issues, list)

    def test_validate_detects_invalid(self):
        mgr = ConfigManager()
        mgr.set("scale", "invalid_scale")
        issues = mgr.validate()
        assert len(issues) > 0

    def test_validate_passes_valid_config(self):
        mgr = ConfigManager()
        mgr.set("scale", "startup")
        mgr.set("planner", "astar")
        mgr.set("optimizer", "minimum_snap")
        mgr.set("estimator", "ekf")
        issues = mgr.validate()
        errors = [i for i in issues if i.severity.value == "error"]
        assert len(errors) == 0

    def test_multiple_loads_merge(self, tmp_path: Path):
        p1 = tmp_path / "base.yaml"
        p2 = tmp_path / "override.yaml"
        _write_yaml(p1, {"scale": "startup", "planner": "astar"})
        _write_yaml(p2, {"planner": "rrt"})
        mgr = ConfigManager()
        mgr.load(str(p1))
        mgr.load(str(p2))
        assert mgr.get("scale") == "startup"
        assert mgr.get("planner") == "rrt"


# ── Integration: save_config / load_config round-trip ────────────────────────


class TestSaveLoadRoundTrip:
    """Integration tests for save/load round-trips."""

    def test_yaml_round_trip(self, tmp_path: Path):
        data = {"scale": "startup", "planner": {"resolution_m": 1.0}}
        p = tmp_path / "rt.yaml"
        save_config(str(p), data)
        result = load_config(str(p))
        assert result == data

    def test_json_round_trip(self, tmp_path: Path):
        data = {"scale": "smb", "modules": ["astar", "rrt"]}
        p = tmp_path / "rt.json"
        save_config(str(p), data)
        result = load_config(str(p))
        assert result == data

    def test_toml_round_trip(self, tmp_path: Path):
        data = {"scale": "enterprise", "log_level": "DEBUG"}
        p = tmp_path / "rt.toml"
        save_config(str(p), data)
        result = load_config(str(p))
        assert result == data


# ── Unsupported format ───────────────────────────────────────────────────────


class TestUnsupportedFormat:
    """Tests for unsupported file formats."""

    def test_unsupported_extension_raises(self, tmp_path: Path):
        p = tmp_path / "config.ini"
        p.write_text("[section]\nkey=value")
        with pytest.raises(ValueError, match="Unsupported config format"):
            load_config(str(p))

    def test_save_unsupported_extension_raises(self, tmp_path: Path):
        p = tmp_path / "config.ini"
        with pytest.raises(ValueError, match="Unsupported config format"):
            save_config(str(p), {"key": "value"})
