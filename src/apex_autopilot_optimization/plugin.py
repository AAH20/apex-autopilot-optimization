"""Plugin system for apex-autopilot-optimization.

Provides an abstract Plugin base class, a PluginRegistry that discovers
plugins via importlib.metadata entry points (group
``apex_autopilot_plugins``), and built-in plugins for benchmarking,
evaluation, and diagnostics.
"""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from importlib.metadata import entry_points
from typing import Any, Dict, List, Optional, Type

from apex_autopilot_optimization.benchmark import (
    BenchmarkConfig,
    BenchmarkRunner,
)
from apex_autopilot_optimization.diagnostics import run_diagnostics
from apex_autopilot_optimization.evaluation import (
    EvaluationConfig,
    EvaluationRunner,
)

ENTRY_POINT_GROUP = "apex_autopilot_plugins"


class Plugin(ABC):
    """Abstract base class for apex-autopilot-optimization plugins."""

    name: str = ""
    version: str = "0.1.0"

    @abstractmethod
    def run(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the plugin with the given configuration.

        Args:
            config: Plugin-specific configuration dictionary.

        Returns:
            A dictionary containing the plugin's results.
        """
        raise NotImplementedError


class BenchmarkPlugin(Plugin):
    """Plugin that runs a benchmark via BenchmarkRunner."""

    name = "benchmark"
    version = "1.0.0"

    def run(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run a benchmark and return the result as a dict."""
        benchmark_config = BenchmarkConfig(
            name=config.get("name", "benchmark"),
            iterations=config.get("iterations", 100),
            warmup_iterations=config.get("warmup_iterations", 10),
            description=config.get("description", ""),
        )
        runner = BenchmarkRunner(benchmark_config)
        result = runner.run()
        return result.to_dict()


class EvaluationPlugin(Plugin):
    """Plugin that runs an evaluation via EvaluationRunner."""

    name = "evaluation"
    version = "1.0.0"

    def run(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run an evaluation and return the result as a dict."""
        evaluation_config = EvaluationConfig(
            name=config.get("name", "evaluation"),
            metrics=config.get("metrics", []),
            weights=config.get("weights", {}),
            targets=config.get("targets", {}),
        )
        runner = EvaluationRunner(evaluation_config)
        result = runner.run()
        return result.to_dict()


class DiagnosticsPlugin(Plugin):
    """Plugin that runs system diagnostics."""

    name = "diagnostics"
    version = "1.0.0"

    def run(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run diagnostics and return the report as a dict."""
        report = run_diagnostics()
        return report.to_dict()


class PluginRegistry:
    """Registry for discovering, listing, and executing plugins."""

    def __init__(self) -> None:
        self._plugins: Dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance by its name.

        Args:
            plugin: The plugin instance to register.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        if plugin.name in self._plugins:
            raise ValueError(
                f"Plugin '{plugin.name}' is already registered"
            )
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        """Unregister a plugin by name.

        Args:
            name: The name of the plugin to remove.

        Raises:
            KeyError: If no plugin with the given name is registered.
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' is not registered")
        del self._plugins[name]

    def get(self, name: str) -> Plugin:
        """Get a registered plugin by name.

        Args:
            name: The name of the plugin to retrieve.

        Returns:
            The registered plugin instance.

        Raises:
            KeyError: If no plugin with the given name is registered.
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' is not registered")
        return self._plugins[name]

    def list_plugins(self) -> List[str]:
        """List the names of all registered plugins.

        Returns:
            A sorted list of registered plugin names.
        """
        return sorted(self._plugins.keys())

    def execute(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a registered plugin by name.

        Args:
            name: The name of the plugin to execute.
            config: Optional configuration dictionary for the plugin.

        Returns:
            The plugin's result dictionary.

        Raises:
            KeyError: If no plugin with the given name is registered.
        """
        plugin = self.get(name)
        return plugin.run(config or {})

    def discover(self) -> List[str]:
        """Discover plugins via importlib.metadata entry points.

        Looks up entry points in the ``apex_autopilot_plugins`` group,
        loads each one, and registers valid Plugin instances.

        Returns:
            A sorted list of names of newly discovered and registered plugins.
        """
        discovered: List[str] = []
        try:
            eps = entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:
            # Python < 3.10 fallback
            all_eps = entry_points()  # type: ignore[call-arg]
            eps = all_eps.get(ENTRY_POINT_GROUP, [])

        for ep in eps:
            try:
                plugin_class = ep.load()
                plugin = plugin_class()
                if isinstance(plugin, Plugin):
                    if plugin.name not in self._plugins:
                        self._plugins[plugin.name] = plugin
                        discovered.append(plugin.name)
            except Exception:
                continue

        return sorted(discovered)

    def register_builtin(self) -> None:
        """Register all built-in plugins."""
        self.register(BenchmarkPlugin())
        self.register(EvaluationPlugin())
        self.register(DiagnosticsPlugin())
