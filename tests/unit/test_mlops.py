"""Tests for the MLOps module: registry, serving, versioning, experiments, drift."""

from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pytest

from apex_autopilot_optimization.mlops import (
    DriftDetector,
    ExperimentTracker,
    ModelRegistry,
    ModelServer,
    ModelStage,
    ModelVersion,
)

# ── Module-level helper artifacts (picklable) ────────────────────────────────


def _double(x):
    """A trivial 'model' callable used to exercise the serving path."""
    return x * 2


class _Predictor:
    """A minimal model object exposing a ``predict`` method."""

    def predict(self, x):
        return [v + 1 for v in x]


def _write_pickle(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(obj, fh)
    return str(path)


# ── ModelVersion / ModelStage ────────────────────────────────────────────────


class TestModelVersion:
    """Tests for the ModelVersion dataclass and ModelStage enum."""

    def test_model_version_creation(self) -> None:
        mv = ModelVersion(
            name="planner",
            version="1.0.0",
            path="/tmp/planner.bin",
            stage=ModelStage.STAGING,
            metadata={"algo": "astar"},
            created_at=123.0,
        )
        assert mv.name == "planner"
        assert mv.version == "1.0.0"
        assert mv.path == "/tmp/planner.bin"
        assert mv.stage == ModelStage.STAGING
        assert mv.metadata == {"algo": "astar"}
        assert mv.created_at == 123.0

    def test_model_version_defaults(self) -> None:
        before = time.time()
        mv = ModelVersion(name="m", version="1", path="/tmp/m")
        after = time.time()
        assert mv.stage == ModelStage.STAGING
        assert mv.metadata == {}
        assert before <= mv.created_at <= after

    def test_model_stage_members(self) -> None:
        assert {s.name for s in ModelStage} == {"STAGING", "PRODUCTION", "ARCHIVED"}

    def test_model_stage_is_str_compatible(self) -> None:
        # str-Enum so it serializes cleanly to JSON.
        assert ModelStage.PRODUCTION == "production"
        assert json.loads(json.dumps(ModelStage.PRODUCTION)) == "production"


# ── ModelRegistry ────────────────────────────────────────────────────────────


class TestModelRegistry:
    """Tests for model registry CRUD and version management."""

    def _registry(self, tmp_path: Path) -> ModelRegistry:
        return ModelRegistry(root=str(tmp_path / "registry"))

    def test_register_model_returns_version(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        mv = reg.register_model("planner", "1.0.0", "/models/planner-1.bin")
        assert isinstance(mv, ModelVersion)
        assert mv.name == "planner"
        assert mv.version == "1.0.0"
        assert mv.stage == ModelStage.STAGING

    def test_register_model_with_metadata(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/models/p.bin", {"algo": "rrt", "iters": 500})
        meta = reg.get_model_metadata("planner", "1.0.0")
        assert meta == {"algo": "rrt", "iters": 500}

    def test_register_duplicate_raises(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/models/p.bin")
        with pytest.raises(ValueError, match="already registered"):
            reg.register_model("planner", "1.0.0", "/models/p2.bin")

    def test_get_model(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "2.0.0", "/models/p2.bin")
        mv = reg.get_model("planner", "2.0.0")
        assert mv.version == "2.0.0"
        assert mv.path == "/models/p2.bin"

    def test_get_model_missing_raises(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        with pytest.raises(KeyError):
            reg.get_model("nope", "0.0.1")

    def test_get_model_metadata_missing_raises(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        with pytest.raises(KeyError):
            reg.get_model_metadata("nope", "0.0.1")

    def test_list_models(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/a")
        reg.register_model("controller", "1.0.0", "/b")
        reg.register_model("planner", "2.0.0", "/c")
        assert sorted(reg.list_models()) == ["controller", "planner"]

    def test_list_models_empty(self, tmp_path: Path) -> None:
        assert self._registry(tmp_path).list_models() == []

    def test_list_versions(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/a")
        reg.register_model("planner", "2.0.0", "/b")
        versions = reg.list_versions("planner")
        assert {v.version for v in versions} == {"1.0.0", "2.0.0"}

    def test_list_versions_unknown_name_is_empty(self, tmp_path: Path) -> None:
        assert self._registry(tmp_path).list_versions("ghost") == []

    def test_delete_model(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/a")
        assert reg.delete_model("planner", "1.0.0") is True
        assert reg.list_versions("planner") == []

    def test_delete_model_missing_returns_false(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        assert reg.delete_model("ghost", "1.0.0") is False

    def test_delete_one_version_keeps_other(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/a")
        reg.register_model("planner", "2.0.0", "/b")
        reg.delete_model("planner", "1.0.0")
        assert [v.version for v in reg.list_versions("planner")] == ["2.0.0"]

    def test_promote_model_to_production(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/a")
        mv = reg.promote_model("planner", "1.0.0", ModelStage.PRODUCTION)
        assert mv.stage == ModelStage.PRODUCTION
        assert reg.get_model("planner", "1.0.0").stage == ModelStage.PRODUCTION

    def test_promote_model_accepts_string_stage(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/a")
        mv = reg.promote_model("planner", "1.0.0", "archived")
        assert mv.stage == ModelStage.ARCHIVED

    def test_promote_model_invalid_stage_raises(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        reg.register_model("planner", "1.0.0", "/a")
        with pytest.raises(ValueError):
            reg.promote_model("planner", "1.0.0", "bogus")

    def test_promote_missing_model_raises(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        with pytest.raises(KeyError):
            reg.promote_model("ghost", "1.0.0", ModelStage.PRODUCTION)

    def test_registry_persists_across_instances(self, tmp_path: Path) -> None:
        root = str(tmp_path / "registry")
        reg = ModelRegistry(root=root)
        reg.register_model("planner", "1.0.0", "/a", {"algo": "astar"})
        reg.promote_model("planner", "1.0.0", ModelStage.PRODUCTION)

        reg2 = ModelRegistry(root=root)
        mv = reg2.get_model("planner", "1.0.0")
        assert mv.stage == ModelStage.PRODUCTION
        assert reg2.get_model_metadata("planner", "1.0.0") == {"algo": "astar"}


# ── ModelServer ──────────────────────────────────────────────────────────────


class TestModelServer:
    """Tests for model server load/serve/unload and serving stats."""

    def _server(self, tmp_path: Path) -> tuple[ModelServer, ModelRegistry, Path]:
        reg = ModelRegistry(root=str(tmp_path / "registry"))
        server = ModelServer(registry=reg)
        return server, reg, tmp_path / "artifacts"

    def test_load_model(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        path = _write_pickle(arts / "m.bin", _double)
        reg.register_model("doubler", "1.0.0", path)
        server.load_model("doubler", "1.0.0")
        assert server.is_model_loaded("doubler", "1.0.0") is True

    def test_load_missing_model_raises(self, tmp_path: Path) -> None:
        server, _reg, _arts = self._server(tmp_path)
        with pytest.raises(KeyError):
            server.load_model("ghost", "1.0.0")

    def test_load_missing_artifact_raises(self, tmp_path: Path) -> None:
        server, reg, _arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", str(tmp_path / "does_not_exist.bin"))
        with pytest.raises(FileNotFoundError):
            server.load_model("doubler", "1.0.0")

    def test_serve_uses_loaded_callable(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", _write_pickle(arts / "m.bin", _double))
        server.load_model("doubler", "1.0.0")
        assert server.serve(21) == 42

    def test_serve_uses_predict_method(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("adder", "1.0.0", _write_pickle(arts / "m.bin", _Predictor()))
        server.load_model("adder", "1.0.0")
        assert server.serve([1, 2, 3]) == [2, 3, 4]

    def test_serve_without_loaded_model_raises(self, tmp_path: Path) -> None:
        server, _reg, _arts = self._server(tmp_path)
        with pytest.raises(RuntimeError):
            server.serve(1)

    def test_is_model_loaded_false_before_load(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", _write_pickle(arts / "m.bin", _double))
        assert server.is_model_loaded("doubler", "1.0.0") is False

    def test_unload_model(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", _write_pickle(arts / "m.bin", _double))
        server.load_model("doubler", "1.0.0")
        assert server.unload_model("doubler", "1.0.0") is True
        assert server.is_model_loaded("doubler", "1.0.0") is False

    def test_unload_missing_returns_false(self, tmp_path: Path) -> None:
        server, _reg, _arts = self._server(tmp_path)
        assert server.unload_model("ghost", "1.0.0") is False

    def test_serve_after_unload_raises(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", _write_pickle(arts / "m.bin", _double))
        server.load_model("doubler", "1.0.0")
        server.unload_model("doubler", "1.0.0")
        with pytest.raises(RuntimeError):
            server.serve(1)

    def test_get_model_info(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", _write_pickle(arts / "m.bin", _double), {"k": "v"})
        server.load_model("doubler", "1.0.0")
        info = server.get_model_info("doubler", "1.0.0")
        assert info["name"] == "doubler"
        assert info["version"] == "1.0.0"
        assert info["loaded"] is True
        assert info["metadata"] == {"k": "v"}

    def test_get_serving_stats_counts_requests(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", _write_pickle(arts / "m.bin", _double))
        server.load_model("doubler", "1.0.0")
        server.serve(1)
        server.serve(2)
        server.serve(3)
        stats = server.get_serving_stats()
        assert stats["total_requests"] == 3
        assert stats["successful_requests"] == 3
        assert stats["models_loaded"] == 1

    def test_get_serving_stats_counts_failures(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("bad", "1.0.0", _write_pickle(arts / "m.bin", object()))
        server.load_model("bad", "1.0.0")
        with pytest.raises(RuntimeError):
            server.serve(1)
        stats = server.get_serving_stats()
        assert stats["total_requests"] == 1
        assert stats["failed_requests"] == 1
        assert stats["successful_requests"] == 0

    def test_get_serving_stats_empty(self, tmp_path: Path) -> None:
        server, _reg, _arts = self._server(tmp_path)
        stats = server.get_serving_stats()
        assert stats["total_requests"] == 0
        assert stats["models_loaded"] == 0
        assert stats["active_model"] is None

    def test_get_serving_stats_per_model(self, tmp_path: Path) -> None:
        server, reg, arts = self._server(tmp_path)
        reg.register_model("doubler", "1.0.0", _write_pickle(arts / "m.bin", _double))
        server.load_model("doubler", "1.0.0")
        server.serve(5)
        server.serve(6)
        stats = server.get_serving_stats()
        assert stats["per_model_requests"]["doubler:1.0.0"] == 2


# ── ExperimentTracker ────────────────────────────────────────────────────────


class TestExperimentTracker:
    """Tests for the experiment tracking lifecycle and comparison."""

    def test_start_experiment_returns_id(self) -> None:
        tracker = ExperimentTracker()
        exp_id = tracker.start_experiment("tune-lr", {"lr": 0.01})
        assert isinstance(exp_id, str)
        assert exp_id

    def test_start_experiment_ids_are_unique(self) -> None:
        tracker = ExperimentTracker()
        assert tracker.start_experiment("a", {}) != tracker.start_experiment("a", {})

    def test_get_experiment(self) -> None:
        tracker = ExperimentTracker()
        exp_id = tracker.start_experiment("tune-lr", {"lr": 0.01})
        exp = tracker.get_experiment(exp_id)
        assert exp.name == "tune-lr"
        assert exp.config == {"lr": 0.01}
        assert exp.status == "running"

    def test_get_missing_experiment_raises(self) -> None:
        tracker = ExperimentTracker()
        with pytest.raises(KeyError):
            tracker.get_experiment("nope")

    def test_log_metric(self) -> None:
        tracker = ExperimentTracker()
        exp_id = tracker.start_experiment("tune", {})
        tracker.log_metric(exp_id, "loss", 0.5)
        tracker.log_metric(exp_id, "loss", 0.3)
        exp = tracker.get_experiment(exp_id)
        assert exp.metrics["loss"] == [0.5, 0.3]

    def test_log_metric_missing_experiment_raises(self) -> None:
        tracker = ExperimentTracker()
        with pytest.raises(KeyError):
            tracker.log_metric("nope", "loss", 1.0)

    def test_log_metric_after_end_raises(self) -> None:
        tracker = ExperimentTracker()
        exp_id = tracker.start_experiment("tune", {})
        tracker.end_experiment(exp_id, {"accuracy": 0.9})
        with pytest.raises(RuntimeError):
            tracker.log_metric(exp_id, "loss", 0.1)

    def test_end_experiment_sets_result_and_status(self) -> None:
        tracker = ExperimentTracker()
        exp_id = tracker.start_experiment("tune", {})
        exp = tracker.end_experiment(exp_id, {"accuracy": 0.95})
        assert exp.status == "completed"
        assert exp.result == {"accuracy": 0.95}
        assert exp.ended_at >= exp.started_at

    def test_end_experiment_twice_raises(self) -> None:
        tracker = ExperimentTracker()
        exp_id = tracker.start_experiment("tune", {})
        tracker.end_experiment(exp_id, {})
        with pytest.raises(RuntimeError):
            tracker.end_experiment(exp_id, {})

    def test_list_experiments(self) -> None:
        tracker = ExperimentTracker()
        tracker.start_experiment("a", {})
        tracker.start_experiment("b", {})
        tracker.start_experiment("c", {})
        assert len(tracker.list_experiments()) == 3

    def test_list_experiments_empty(self) -> None:
        assert ExperimentTracker().list_experiments() == []

    def test_compare_experiments_metrics_diff(self) -> None:
        tracker = ExperimentTracker()
        a = tracker.start_experiment("tune", {})
        tracker.log_metric(a, "accuracy", 0.8)
        tracker.end_experiment(a, {"accuracy": 0.8})
        b = tracker.start_experiment("tune", {})
        tracker.log_metric(b, "accuracy", 0.9)
        tracker.end_experiment(b, {"accuracy": 0.9})
        cmp = tracker.compare_experiments(a, b)
        assert cmp["metrics_diff"]["accuracy"] == pytest.approx(0.1)

    def test_compare_experiments_missing_raises(self) -> None:
        tracker = ExperimentTracker()
        a = tracker.start_experiment("tune", {})
        with pytest.raises(KeyError):
            tracker.compare_experiments(a, "nope")


# ── DriftDetector ────────────────────────────────────────────────────────────


class TestDriftDetector:
    """Tests for data drift detection, score, report, and threshold."""

    def test_no_drift_for_same_distribution(self) -> None:
        rng = np.random.default_rng(42)
        ref = rng.normal(0.0, 1.0, 2000)
        cur = rng.normal(0.0, 1.0, 2000)
        det = DriftDetector(threshold=0.1)
        report = det.detect_drift(ref, cur)
        assert report["drift_detected"] is False
        assert det.is_drift_detected() is False

    def test_drift_detected_for_shifted_distribution(self) -> None:
        rng = np.random.default_rng(42)
        ref = rng.normal(0.0, 1.0, 2000)
        cur = rng.normal(5.0, 1.0, 2000)
        det = DriftDetector(threshold=0.1)
        det.detect_drift(ref, cur)
        assert det.is_drift_detected() is True
        assert det.get_drift_score() > 0.1

    def test_get_drift_score_before_detection(self) -> None:
        det = DriftDetector()
        assert det.get_drift_score() == 0.0

    def test_get_drift_report_before_detection(self) -> None:
        det = DriftDetector(threshold=0.2)
        report = det.get_drift_report()
        assert report["drift_detected"] is False
        assert report["threshold"] == 0.2

    def test_get_drift_report_after_detection(self) -> None:
        rng = np.random.default_rng(0)
        det = DriftDetector()
        det.detect_drift(rng.normal(0, 1, 500), rng.normal(2, 1, 500))
        report = det.get_drift_report()
        assert "drift_score" in report
        assert report["n_reference"] == 500
        assert report["n_current"] == 500

    def test_set_threshold_changes_decision(self) -> None:
        rng = np.random.default_rng(1)
        ref = rng.normal(0.0, 1.0, 2000)
        cur = rng.normal(0.4, 1.0, 2000)
        det = DriftDetector(threshold=100.0)
        det.detect_drift(ref, cur)
        assert det.is_drift_detected() is False
        det.set_threshold(0.0)
        assert det.is_drift_detected() is True

    def test_set_threshold_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            DriftDetector().set_threshold(-1.0)

    def test_detect_drift_empty_raises(self) -> None:
        det = DriftDetector()
        with pytest.raises(ValueError):
            det.detect_drift([], [1.0, 2.0])

    def test_detect_drift_identical_data_no_drift(self) -> None:
        det = DriftDetector(threshold=0.1)
        det.detect_drift([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
        assert det.get_drift_score() == pytest.approx(0.0, abs=1e-9)
        assert det.is_drift_detected() is False


# ── Package exports ──────────────────────────────────────────────────────────


class TestPackageExports:
    """Tests that all required symbols are exported from the package."""

    def test_model_registry_exported(self) -> None:
        from apex_autopilot_optimization.mlops import ModelRegistry as R

        assert R is ModelRegistry

    def test_model_server_exported(self) -> None:
        from apex_autopilot_optimization.mlops import ModelServer as S

        assert S is ModelServer

    def test_model_version_exported(self) -> None:
        from apex_autopilot_optimization.mlops import ModelVersion as V

        assert V is ModelVersion

    def test_experiment_tracker_exported(self) -> None:
        from apex_autopilot_optimization.mlops import ExperimentTracker as T

        assert T is ExperimentTracker

    def test_drift_detector_exported(self) -> None:
        from apex_autopilot_optimization.mlops import DriftDetector as D

        assert D is DriftDetector

    def test_all_declares_required_symbols(self) -> None:
        import apex_autopilot_optimization.mlops as mlops

        assert {
            "ModelRegistry",
            "ModelServer",
            "ModelVersion",
            "ExperimentTracker",
            "DriftDetector",
        } <= set(mlops.__all__)
