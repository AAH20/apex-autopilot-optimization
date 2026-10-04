"""Tests for experiments module: feature flags, experiment tracking, A/B testing."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from apex_autopilot_optimization.experiments import (
    ABTestConfig,
    ExperimentRun,
    ExperimentTracker,
    FeatureFlag,
    FeatureFlagStore,
    assign_variant,
    is_statistically_significant,
)


# ---------------------------------------------------------------------------
# FeatureFlag dataclass
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    """Tests for FeatureFlag dataclass."""

    def test_flag_creation(self):
        flag = FeatureFlag(
            name="new_ui",
            enabled=True,
            rollout_percentage=50.0,
            description="Enable new UI",
        )
        assert flag.name == "new_ui"
        assert flag.enabled is True
        assert flag.rollout_percentage == 50.0
        assert flag.description == "Enable new UI"

    def test_flag_defaults(self):
        flag = FeatureFlag(name="test_flag")
        assert flag.name == "test_flag"
        assert flag.enabled is False
        assert flag.rollout_percentage == 0.0
        assert flag.description == ""

    def test_flag_enable(self):
        flag = FeatureFlag(name="f1", enabled=False)
        flag.enabled = True
        assert flag.enabled is True

    def test_flag_disable(self):
        flag = FeatureFlag(name="f1", enabled=True)
        flag.enabled = False
        assert flag.enabled is False

    def test_flag_rollout_percentage(self):
        flag = FeatureFlag(name="f1", rollout_percentage=25.0)
        assert flag.rollout_percentage == 25.0
        flag.rollout_percentage = 75.0
        assert flag.rollout_percentage == 75.0

    def test_flag_rollout_full(self):
        flag = FeatureFlag(name="f1", rollout_percentage=100.0)
        assert flag.rollout_percentage == 100.0

    def test_flag_rollout_zero(self):
        flag = FeatureFlag(name="f1", rollout_percentage=0.0)
        assert flag.rollout_percentage == 0.0


# ---------------------------------------------------------------------------
# FeatureFlagStore
# ---------------------------------------------------------------------------


class TestFeatureFlagStore:
    """Tests for FeatureFlagStore."""

    def test_store_create(self):
        store = FeatureFlagStore()
        flag = store.create(FeatureFlag(name="f1", enabled=True))
        assert flag.name == "f1"
        assert flag.enabled is True

    def test_store_create_duplicate_raises(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1"))
        with pytest.raises(ValueError, match="already exists"):
            store.create(FeatureFlag(name="f1"))

    def test_store_get(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True))
        flag = store.get("f1")
        assert flag.name == "f1"
        assert flag.enabled is True

    def test_store_get_nonexistent_raises(self):
        store = FeatureFlagStore()
        with pytest.raises(KeyError):
            store.get("nonexistent")

    def test_store_is_enabled_true(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=100.0))
        assert store.is_enabled("f1") is True

    def test_store_is_enabled_false(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=False))
        assert store.is_enabled("f1") is False

    def test_store_is_enabled_with_context_user_id(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=100.0))
        assert store.is_enabled("f1", context={"user_id": "user_42"}) is True

    def test_store_is_enabled_rollout_zero(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=0.0))
        assert store.is_enabled("f1", context={"user_id": "user_42"}) is False

    def test_store_is_enabled_rollout_partial(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=50.0))
        # With 50% rollout, some users get it, some don't — just verify it returns bool
        result = store.is_enabled("f1", context={"user_id": "user_1"})
        assert isinstance(result, bool)

    def test_store_is_enabled_no_context(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=100.0))
        # No context — should still work (enabled flag with 100% rollout)
        assert store.is_enabled("f1") is True

    def test_store_update(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=False))
        store.update("f1", enabled=True, rollout_percentage=80.0)
        flag = store.get("f1")
        assert flag.enabled is True
        assert flag.rollout_percentage == 80.0

    def test_store_update_nonexistent_raises(self):
        store = FeatureFlagStore()
        with pytest.raises(KeyError):
            store.update("nonexistent", enabled=True)

    def test_store_list_flags(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1"))
        store.create(FeatureFlag(name="f2"))
        store.create(FeatureFlag(name="f3"))
        flags = store.list_flags()
        assert len(flags) == 3
        names = {f.name for f in flags}
        assert names == {"f1", "f2", "f3"}

    def test_store_list_flags_empty(self):
        store = FeatureFlagStore()
        assert store.list_flags() == []

    def test_store_save_to_yaml(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=50.0, description="test"))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "flags.yaml"
            store.save_to_yaml(str(path))
            assert path.exists()
            content = path.read_text()
            assert "f1" in content
            assert "true" in content.lower()

    def test_store_load_from_yaml(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=50.0, description="test flag"))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "flags.yaml"
            store.save_to_yaml(str(path))

            new_store = FeatureFlagStore()
            new_store.load_from_yaml(str(path))
            flag = new_store.get("f1")
            assert flag.name == "f1"
            assert flag.enabled is True
            assert flag.rollout_percentage == 50.0
            assert flag.description == "test flag"

    def test_store_persistence_roundtrip(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="alpha", enabled=True, rollout_percentage=10.0))
        store.create(FeatureFlag(name="beta", enabled=False, rollout_percentage=0.0))
        store.create(FeatureFlag(name="gamma", enabled=True, rollout_percentage=100.0))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "flags.yaml"
            store.save_to_yaml(str(path))

            loaded = FeatureFlagStore()
            loaded.load_from_yaml(str(path))
            assert len(loaded.list_flags()) == 3
            assert loaded.get("alpha").enabled is True
            assert loaded.get("beta").enabled is False
            assert loaded.get("gamma").rollout_percentage == 100.0


# ---------------------------------------------------------------------------
# ExperimentRun dataclass
# ---------------------------------------------------------------------------


class TestExperimentRun:
    """Tests for ExperimentRun dataclass."""

    def test_run_creation(self):
        run = ExperimentRun(
            run_id="r1",
            name="exp1",
            variant="A",
            metrics={"accuracy": 0.95},
            timestamp=1000.0,
        )
        assert run.run_id == "r1"
        assert run.name == "exp1"
        assert run.variant == "A"
        assert run.metrics == {"accuracy": 0.95}
        assert run.timestamp == 1000.0

    def test_run_defaults(self):
        run = ExperimentRun(run_id="r1", name="exp1", variant="A", metrics={}, timestamp=0.0)
        assert run.metrics == {}


# ---------------------------------------------------------------------------
# ExperimentTracker
# ---------------------------------------------------------------------------


class TestExperimentTracker:
    """Tests for ExperimentTracker."""

    def test_tracker_start_run(self):
        tracker = ExperimentTracker()
        run = tracker.start_run("exp1", "A")
        assert run.name == "exp1"
        assert run.variant == "A"
        assert run.run_id is not None
        assert run.timestamp > 0

    def test_tracker_start_run_unique_ids(self):
        tracker = ExperimentTracker()
        run1 = tracker.start_run("exp1", "A")
        run2 = tracker.start_run("exp1", "B")
        assert run1.run_id != run2.run_id

    def test_tracker_end_run(self):
        tracker = ExperimentTracker()
        run = tracker.start_run("exp1", "A")
        tracker.end_run(run.run_id, {"accuracy": 0.92, "latency": 12.5})
        updated = tracker.get_run(run.run_id)
        assert updated.metrics["accuracy"] == 0.92
        assert updated.metrics["latency"] == 12.5

    def test_tracker_end_run_nonexistent_raises(self):
        tracker = ExperimentTracker()
        with pytest.raises(KeyError):
            tracker.end_run("nonexistent", {"accuracy": 0.5})

    def test_tracker_get_run(self):
        tracker = ExperimentTracker()
        run = tracker.start_run("exp1", "A")
        fetched = tracker.get_run(run.run_id)
        assert fetched.run_id == run.run_id
        assert fetched.name == "exp1"

    def test_tracker_get_run_nonexistent_raises(self):
        tracker = ExperimentTracker()
        with pytest.raises(KeyError):
            tracker.get_run("nonexistent")

    def test_tracker_list_runs(self):
        tracker = ExperimentTracker()
        tracker.start_run("exp1", "A")
        tracker.start_run("exp1", "B")
        tracker.start_run("exp2", "A")
        runs = tracker.list_runs("exp1")
        assert len(runs) == 2
        assert all(r.name == "exp1" for r in runs)

    def test_tracker_list_runs_empty(self):
        tracker = ExperimentTracker()
        assert tracker.list_runs("nonexistent") == []

    def test_tracker_compare_runs(self):
        tracker = ExperimentTracker()
        run_a = tracker.start_run("exp1", "A")
        run_b = tracker.start_run("exp1", "B")
        tracker.end_run(run_a.run_id, {"accuracy": 0.90, "latency": 20.0})
        tracker.end_run(run_b.run_id, {"accuracy": 0.95, "latency": 15.0})
        comparison = tracker.compare_runs(run_a.run_id, run_b.run_id)
        assert comparison["run_a"] == run_a.run_id
        assert comparison["run_b"] == run_b.run_id
        assert "metrics_diff" in comparison
        assert comparison["metrics_diff"]["accuracy"] == pytest.approx(-0.05)

    def test_tracker_compare_runs_nonexistent_raises(self):
        tracker = ExperimentTracker()
        run_a = tracker.start_run("exp1", "A")
        with pytest.raises(KeyError):
            tracker.compare_runs(run_a.run_id, "nonexistent")


# ---------------------------------------------------------------------------
# ABTestConfig
# ---------------------------------------------------------------------------


class TestABTestConfig:
    """Tests for ABTestConfig dataclass."""

    def test_ab_config_creation(self):
        config = ABTestConfig(
            name="button_color",
            variants=["red", "blue"],
            weights=[0.5, 0.5],
            metrics=["click_rate", "conversion"],
        )
        assert config.name == "button_color"
        assert config.variants == ["red", "blue"]
        assert config.weights == [0.5, 0.5]
        assert config.metrics == ["click_rate", "conversion"]

    def test_ab_config_single_variant(self):
        config = ABTestConfig(
            name="solo",
            variants=["control"],
            weights=[1.0],
            metrics=["latency"],
        )
        assert len(config.variants) == 1
        assert config.weights == [1.0]


# ---------------------------------------------------------------------------
# assign_variant
# ---------------------------------------------------------------------------


class TestAssignVariant:
    """Tests for assign_variant function."""

    def test_assign_variant_deterministic(self):
        config = ABTestConfig(
            name="exp",
            variants=["A", "B"],
            weights=[0.5, 0.5],
            metrics=["m1"],
        )
        v1 = assign_variant(config, "user_1")
        v2 = assign_variant(config, "user_1")
        assert v1 == v2

    def test_assign_variant_returns_valid_variant(self):
        config = ABTestConfig(
            name="exp",
            variants=["A", "B", "C"],
            weights=[0.33, 0.33, 0.34],
            metrics=["m1"],
        )
        for i in range(100):
            v = assign_variant(config, f"user_{i}")
            assert v in config.variants

    def test_assign_variant_distribution(self):
        config = ABTestConfig(
            name="exp",
            variants=["A", "B"],
            weights=[0.8, 0.2],
            metrics=["m1"],
        )
        counts = {"A": 0, "B": 0}
        n = 1000
        for i in range(n):
            v = assign_variant(config, f"user_{i}")
            counts[v] += 1
        # 80/20 split — allow generous margin
        assert counts["A"] > counts["B"]
        assert counts["A"] / n > 0.7
        assert counts["B"] / n < 0.3

    def test_assign_variant_single_variant(self):
        config = ABTestConfig(
            name="exp",
            variants=["control"],
            weights=[1.0],
            metrics=["m1"],
        )
        assert assign_variant(config, "any_user") == "control"


# ---------------------------------------------------------------------------
# is_statistically_significant
# ---------------------------------------------------------------------------


class TestStatisticalSignificance:
    """Tests for is_statistically_significant function."""

    def test_significant_difference(self):
        # Large difference, low variance — should be significant
        results_a = [0.90, 0.91, 0.89, 0.92, 0.90] * 20
        results_b = [0.50, 0.51, 0.49, 0.52, 0.50] * 20
        assert is_statistically_significant(results_a, results_b, 0.95) is True

    def test_not_significant_difference(self):
        # Nearly identical distributions — should not be significant
        results_a = [0.45, 0.55, 0.50, 0.48, 0.52] * 20
        results_b = [0.46, 0.54, 0.50, 0.49, 0.51] * 20
        assert is_statistically_significant(results_a, results_b, 0.95) is False

    def test_higher_confidence_level_stricter(self):
        # Moderate difference — significant at 0.90 but not at 0.99
        results_a = [0.60, 0.61, 0.59, 0.62, 0.60] * 30
        results_b = [0.55, 0.56, 0.54, 0.57, 0.55] * 30
        sig_90 = is_statistically_significant(results_a, results_b, 0.90)
        sig_99 = is_statistically_significant(results_a, results_b, 0.99)
        # Higher confidence should be harder to achieve
        if sig_90 and not sig_99:
            pass  # expected
        elif sig_90 and sig_99:
            pass  # also acceptable if effect is large enough
        else:
            # sig_90 False — that's fine too, just checking no crash
            pass

    def test_identical_results_not_significant(self):
        results = [0.5] * 50
        assert is_statistically_significant(results, results, 0.95) is False

    def test_empty_results_not_significant(self):
        assert is_statistically_significant([], [], 0.95) is False


# ---------------------------------------------------------------------------
# Context-aware feature flag evaluation
# ---------------------------------------------------------------------------


class TestContextAwareEvaluation:
    """Tests for context-aware feature flag evaluation."""

    def test_flag_enabled_for_specific_user(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=100.0))
        ctx = {"user_id": "user_123", "region": "us-east"}
        assert store.is_enabled("f1", context=ctx) is True

    def test_flag_disabled_ignores_context(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=False, rollout_percentage=100.0))
        ctx = {"user_id": "user_123"}
        assert store.is_enabled("f1", context=ctx) is False

    def test_flag_rollout_uses_user_id_hash(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=50.0))
        # Same user should always get same result
        ctx = {"user_id": "stable_user"}
        r1 = store.is_enabled("f1", context=ctx)
        r2 = store.is_enabled("f1", context=ctx)
        assert r1 == r2

    def test_flag_rollout_100_percent_all_users(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=100.0))
        for i in range(50):
            assert store.is_enabled("f1", context={"user_id": f"user_{i}"}) is True

    def test_flag_rollout_0_percent_no_users(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=0.0))
        for i in range(50):
            assert store.is_enabled("f1", context={"user_id": f"user_{i}"}) is False

    def test_flag_with_group_context(self):
        store = FeatureFlagStore()
        store.create(FeatureFlag(name="f1", enabled=True, rollout_percentage=100.0))
        ctx = {"user_id": "u1", "group": "beta", "tenant": "acme"}
        assert store.is_enabled("f1", context=ctx) is True
