"""Tests for the plugin system."""

import sys
import unittest
from unittest import mock

import pytest

from apex_autopilot_optimization import plugin as plugin_module
from apex_autopilot_optimization.plugin import (
    ENTRY_POINT_GROUP,
    BenchmarkPlugin,
    DiagnosticsPlugin,
    EvaluationPlugin,
    Plugin,
    PluginRegistry,
)


class DummyPlugin(Plugin):
    """A minimal concrete plugin for testing."""

    name = "dummy"
    version = "0.0.1"

    def run(self, config):
        return {"ran": True, "config": config}


class OtherPlugin(Plugin):
    """A second minimal concrete plugin for testing."""

    name = "other"
    version = "2.0.0"

    def run(self, config):
        return {"other": True}


class TestPluginBase(unittest.TestCase):
    """Tests for the Plugin abstract base class."""

    def test_cannot_instantiate_abstract_plugin(self):
        """Plugin is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Plugin()

    def test_dummy_plugin_attributes(self):
        """Concrete plugin exposes name and version."""
        p = DummyPlugin()
        assert p.name == "dummy"
        assert p.version == "0.0.1"

    def test_dummy_plugin_run_returns_dict(self):
        """Concrete plugin run returns its result dict."""
        p = DummyPlugin()
        result = p.run({"key": "value"})
        assert result == {"ran": True, "config": {"key": "value"}}

    def test_plugin_instantiated_via_subclass_only(self):
        """Subclass without run() still cannot be instantiated."""

        class IncompletePlugin(Plugin):
            name = "incomplete"

        with pytest.raises(TypeError):
            IncompletePlugin()


class TestPluginRegistry(unittest.TestCase):
    """Tests for PluginRegistry registration, listing, retrieval, execution."""

    def setUp(self):
        self.registry = PluginRegistry()

    def test_register_plugin(self):
        """Registering a plugin makes it listed."""
        self.registry.register(DummyPlugin())
        assert "dummy" in self.registry.list_plugins()

    def test_list_plugins_empty(self):
        """A fresh registry lists no plugins."""
        assert self.registry.list_plugins() == []

    def test_list_plugins_sorted(self):
        """list_plugins returns sorted names."""
        self.registry.register(OtherPlugin())
        self.registry.register(DummyPlugin())
        assert self.registry.list_plugins() == ["dummy", "other"]

    def test_get_plugin(self):
        """get returns the registered instance."""
        p = DummyPlugin()
        self.registry.register(p)
        assert self.registry.get("dummy") is p

    def test_get_unknown_plugin_raises(self):
        """get raises KeyError for an unregistered name."""
        with pytest.raises(KeyError):
            self.registry.get("nonexistent")

    def test_run_plugin_via_execute(self):
        """execute runs the named plugin and returns its result."""
        self.registry.register(DummyPlugin())
        result = self.registry.execute("dummy", {"x": 1})
        assert result == {"ran": True, "config": {"x": 1}}

    def test_execute_without_config(self):
        """execute defaults to an empty config dict."""
        self.registry.register(DummyPlugin())
        result = self.registry.execute("dummy")
        assert result["config"] == {}

    def test_execute_unknown_plugin_raises(self):
        """execute raises KeyError for an unregistered name."""
        with pytest.raises(KeyError):
            self.registry.execute("ghost")

    def test_duplicate_registration_raises(self):
        """Registering the same name twice raises ValueError."""
        self.registry.register(DummyPlugin())
        with pytest.raises(ValueError):
            self.registry.register(DummyPlugin())

    def test_unregister_plugin(self):
        """unregister removes the plugin from the registry."""
        self.registry.register(DummyPlugin())
        self.registry.unregister("dummy")
        assert self.registry.list_plugins() == []

    def test_unregister_unknown_plugin_raises(self):
        """unregister raises KeyError for an unregistered name."""
        with pytest.raises(KeyError):
            self.registry.unregister("ghost")

    def test_reregister_after_unregister(self):
        """A name can be re-registered after being unregistered."""
        self.registry.register(DummyPlugin())
        self.registry.unregister("dummy")
        self.registry.register(DummyPlugin())
        assert "dummy" in self.registry.list_plugins()


class TestBuiltinPlugins(unittest.TestCase):
    """Tests for the built-in plugins."""

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register_builtin()

    def test_register_builtin_registers_all(self):
        """register_builtin registers benchmark, evaluation, diagnostics."""
        assert self.registry.list_plugins() == [
            "benchmark",
            "diagnostics",
            "evaluation",
        ]

    def test_builtin_plugin_names_and_versions(self):
        """Built-in plugins expose expected names and versions."""
        assert BenchmarkPlugin.name == "benchmark"
        assert EvaluationPlugin.name == "evaluation"
        assert DiagnosticsPlugin.name == "diagnostics"
        assert BenchmarkPlugin.version == "1.0.0"
        assert EvaluationPlugin.version == "1.0.0"
        assert DiagnosticsPlugin.version == "1.0.0"

    def test_benchmark_plugin_run(self):
        """BenchmarkPlugin executes a benchmark and returns metric keys."""
        result = self.registry.execute(
            "benchmark", {"name": "t", "iterations": 5, "warmup_iterations": 1}
        )
        assert result["name"] == "t"
        assert result["iterations"] == 5
        for key in ("mean_ms", "p50_ms", "p95_ms", "p99_ms", "std_dev_ms"):
            assert key in result
        assert result["mean_ms"] > 0

    def test_evaluation_plugin_run(self):
        """EvaluationPlugin executes an evaluation and returns metrics."""
        result = self.registry.execute(
            "evaluation",
            {"name": "eval", "metrics": ["accuracy", "safety"]},
        )
        assert result["name"] == "eval"
        assert result["overall_score"] > 0
        assert result["passed"] is True
        names = [m["name"] for m in result["metrics"]]
        assert names == ["accuracy", "safety"]

    def test_diagnostics_plugin_run(self):
        """DiagnosticsPlugin runs checks and returns a report dict."""
        result = self.registry.execute("diagnostics")
        assert "summary" in result
        assert "environment" in result
        assert "results" in result
        assert result["summary"]["total"] > 0
        assert result["summary"]["passed"] > 0

    def test_benchmark_plugin_run_with_defaults(self):
        """BenchmarkPlugin works with an empty config (uses defaults)."""
        result = self.registry.execute("benchmark", {})
        assert result["name"] == "benchmark"
        assert result["iterations"] == 100


class _FakeEntryPoint:
    """Fake importlib.metadata entry point for discovery tests."""

    def __init__(self, name, plugin_class):
        self.name = name
        self._plugin_class = plugin_class

    def load(self):
        return self._plugin_class


class TestPluginDiscovery(unittest.TestCase):
    """Tests for entry-point-based plugin discovery."""

    def setUp(self):
        self.registry = PluginRegistry()

    def _patch_entry_points(self, eps):
        return mock.patch.object(plugin_module, "entry_points", return_value=eps)

    def test_discover_registers_entry_point_plugins(self):
        """discover loads and registers plugins from entry points."""
        eps = [_FakeEntryPoint("dummy", DummyPlugin)]
        with self._patch_entry_points(eps):
            discovered = self.registry.discover()
        assert discovered == ["dummy"]
        assert "dummy" in self.registry.list_plugins()

    def test_discover_returns_empty_without_entry_points(self):
        """discover with no entry points registers nothing."""
        with self._patch_entry_points([]):
            discovered = self.registry.discover()
        assert discovered == []
        assert self.registry.list_plugins() == []

    def test_discover_skips_non_plugin_classes(self):
        """discover ignores entry points that don't yield Plugin instances."""

        class NotAPlugin:
            pass

        eps = [
            _FakeEntryPoint("dummy", DummyPlugin),
            _FakeEntryPoint("not_a_plugin", NotAPlugin),
        ]
        with self._patch_entry_points(eps):
            discovered = self.registry.discover()
        assert discovered == ["dummy"]
        assert "not_a_plugin" not in self.registry.list_plugins()

    def test_discover_skips_broken_entry_points(self):
        """discover tolerates entry points that fail to load."""

        class BrokenEntryPoint:
            name = "broken"

            def load(self):
                raise RuntimeError("boom")

        eps = [
            _FakeEntryPoint("dummy", DummyPlugin),
            BrokenEntryPoint(),
        ]
        with self._patch_entry_points(eps):
            discovered = self.registry.discover()
        assert discovered == ["dummy"]

    def test_discover_does_not_override_registered(self):
        """discover keeps an already-registered plugin of the same name."""

        class DummyPluginV2(Plugin):
            name = "dummy"
            version = "0.0.2"

            def run(self, config):
                return {"v2": True}

        self.registry.register(DummyPlugin())
        eps = [_FakeEntryPoint("dummy", DummyPluginV2)]
        with self._patch_entry_points(eps):
            discovered = self.registry.discover()
        assert discovered == []
        assert isinstance(self.registry.get("dummy"), DummyPlugin)

    def test_discover_runs_discovered_plugin(self):
        """A discovered plugin is executable via the registry."""
        eps = [_FakeEntryPoint("dummy", DummyPlugin)]
        with self._patch_entry_points(eps):
            self.registry.discover()
        result = self.registry.execute("dummy", {"a": 2})
        assert result == {"ran": True, "config": {"a": 2}}

    def test_entry_point_group_constant(self):
        """The entry point group name matches the spec."""
        assert ENTRY_POINT_GROUP == "apex_autopilot_plugins"

    @pytest.mark.skipif(sys.version_info < (3, 10), reason="requires Python 3.10+ entry_points API")
    def test_discover_uses_group_keyword(self):
        """discover queries entry points with the plugin group."""
        with mock.patch.object(plugin_module, "entry_points", return_value=[]) as mock_ep:
            self.registry.discover()
        mock_ep.assert_called_once_with(group=ENTRY_POINT_GROUP)


if __name__ == "__main__":
    unittest.main()
