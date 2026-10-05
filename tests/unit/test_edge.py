"""Tests for the edge computing package: EdgeNode, EdgeConfig, EdgeAI,
FogNode, and EdgeCloudSync."""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.edge import (
    EdgeAI,
    EdgeCloudSync,
    EdgeConfig,
    EdgeNode,
    FogNode,
)


def make_config(**overrides) -> EdgeConfig:
    defaults = dict(
        node_id="edge-1",
        cloud_url="https://cloud.example.com",
        sync_interval_seconds=30.0,
        max_buffer_size=10,
        offline_mode=False,
        power_profile="balanced",
    )
    defaults.update(overrides)
    return EdgeConfig(**defaults)


# ---------------------------------------------------------------------------
# EdgeConfig
# ---------------------------------------------------------------------------


class TestEdgeConfig:
    def test_defaults(self):
        cfg = EdgeConfig(node_id="n1")
        assert cfg.node_id == "n1"
        assert cfg.cloud_url == "https://cloud.example.com"
        assert cfg.sync_interval_seconds == 60.0
        assert cfg.max_buffer_size == 1000
        assert cfg.offline_mode is False
        assert cfg.power_profile == "balanced"

    def test_custom_values(self):
        cfg = make_config(
            node_id="n2",
            cloud_url="https://x.io",
            sync_interval_seconds=5.0,
            max_buffer_size=50,
            offline_mode=True,
            power_profile="low_power",
        )
        assert cfg.node_id == "n2"
        assert cfg.cloud_url == "https://x.io"
        assert cfg.sync_interval_seconds == 5.0
        assert cfg.max_buffer_size == 50
        assert cfg.offline_mode is True
        assert cfg.power_profile == "low_power"

    def test_empty_node_id_raises(self):
        with pytest.raises(ValueError):
            EdgeConfig(node_id="")

    def test_blank_node_id_raises(self):
        with pytest.raises(ValueError):
            EdgeConfig(node_id="   ")

    def test_empty_cloud_url_raises(self):
        with pytest.raises(ValueError):
            EdgeConfig(node_id="n", cloud_url="")

    def test_non_positive_sync_interval_raises(self):
        with pytest.raises(ValueError):
            EdgeConfig(node_id="n", sync_interval_seconds=0)

    def test_non_positive_max_buffer_raises(self):
        with pytest.raises(ValueError):
            EdgeConfig(node_id="n", max_buffer_size=0)

    def test_invalid_power_profile_raises(self):
        with pytest.raises(ValueError):
            EdgeConfig(node_id="n", power_profile="turbo")


# ---------------------------------------------------------------------------
# EdgeAI
# ---------------------------------------------------------------------------


class TestEdgeAI:
    def test_load_and_is_loaded(self):
        ai = EdgeAI()
        assert ai.is_model_loaded() is False
        assert ai.load_model("/models/detection.onnx") is True
        assert ai.is_model_loaded() is True

    def test_load_empty_path_raises(self):
        ai = EdgeAI()
        with pytest.raises(ValueError):
            ai.load_model("")

    def test_get_model_info(self):
        ai = EdgeAI()
        assert ai.get_model_info() is None
        ai.load_model("/models/a.onnx")
        info = ai.get_model_info()
        assert info is not None
        assert info["path"] == "/models/a.onnx"
        assert info["inference_count"] == 0

    def test_run_inference_without_model_raises(self):
        ai = EdgeAI()
        with pytest.raises(RuntimeError):
            ai.run_inference({"x": 1})

    def test_run_inference_numeric_dict(self):
        ai = EdgeAI()
        ai.load_model("/models/a.onnx")
        result = ai.run_inference({"temp": 20.0, "humidity": 40.0})
        assert result["prediction"] == pytest.approx(30.0)
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["model"] == "/models/a.onnx"

    def test_run_inference_numeric_list(self):
        ai = EdgeAI()
        ai.load_model("/models/a.onnx")
        result = ai.run_inference([1.0, 2.0, 3.0])
        assert result["prediction"] == pytest.approx(2.0)

    def test_run_inference_non_numeric(self):
        ai = EdgeAI()
        ai.load_model("/models/a.onnx")
        result = ai.run_inference("some text")
        assert 0.0 <= result["prediction"] <= 1.0
        assert 0.0 <= result["confidence"] <= 1.0

    def test_inference_count_increments(self):
        ai = EdgeAI()
        ai.load_model("/models/a.onnx")
        ai.run_inference([1])
        ai.run_inference([2])
        assert ai.get_model_info()["inference_count"] == 2

    def test_unload_model(self):
        ai = EdgeAI()
        assert ai.unload_model() is False
        ai.load_model("/models/a.onnx")
        assert ai.unload_model() is True
        assert ai.is_model_loaded() is False

    def test_reload_model(self):
        ai = EdgeAI()
        ai.load_model("/models/a.onnx")
        ai.load_model("/models/b.onnx")
        assert ai.get_model_info()["path"] == "/models/b.onnx"
        assert ai.get_model_info()["inference_count"] == 0


# ---------------------------------------------------------------------------
# EdgeNode
# ---------------------------------------------------------------------------


class TestEdgeNode:
    def test_connect_disconnect(self):
        node = EdgeNode(make_config())
        assert node.is_connected() is False
        assert node.connect() is True
        assert node.is_connected() is True
        assert node.disconnect() is True
        assert node.is_connected() is False

    def test_disconnect_when_not_connected(self):
        node = EdgeNode(make_config())
        assert node.disconnect() is False

    def test_get_status(self):
        node = EdgeNode(make_config(node_id="edge-9"))
        status = node.get_status()
        assert status["node_id"] == "edge-9"
        assert status["connected"] is False
        assert status["buffer_size"] == 0
        assert status["max_buffer_size"] == 10
        assert status["model_loaded"] is False

    def test_process_sensor_data(self):
        node = EdgeNode(make_config())
        record = node.process_sensor_data({"temp": 22.5})
        assert record["temp"] == 22.5
        assert record["node_id"] == "edge-1"
        assert record["sequence"] == 1
        assert "timestamp" in record

    def test_process_sensor_data_increments_sequence(self):
        node = EdgeNode(make_config())
        r1 = node.process_sensor_data({"v": 1})
        r2 = node.process_sensor_data({"v": 2})
        assert r1["sequence"] == 1
        assert r2["sequence"] == 2

    def test_process_sensor_data_invalid_raises(self):
        node = EdgeNode(make_config())
        with pytest.raises(ValueError):
            node.process_sensor_data([1, 2, 3])

    def test_get_pending_data(self):
        node = EdgeNode(make_config())
        node.process_sensor_data({"v": 1})
        node.process_sensor_data({"v": 2})
        pending = node.get_pending_data()
        assert len(pending) == 2
        assert pending[0]["v"] == 1
        assert pending[1]["v"] == 2

    def test_get_pending_data_returns_copy(self):
        node = EdgeNode(make_config())
        node.process_sensor_data({"v": 1})
        pending = node.get_pending_data()
        pending.clear()
        assert len(node.get_pending_data()) == 1

    def test_buffer_overflow_drops_oldest(self):
        node = EdgeNode(make_config(max_buffer_size=3))
        for i in range(5):
            node.process_sensor_data({"v": i})
        pending = node.get_pending_data()
        assert len(pending) == 3
        assert [r["v"] for r in pending] == [2, 3, 4]
        assert node.get_status()["dropped_records"] == 2

    def test_run_inference(self):
        node = EdgeNode(make_config())
        node._ai.load_model("/models/a.onnx")
        result = node.run_inference("/models/a.onnx", [10.0, 20.0])
        assert result["prediction"] == pytest.approx(15.0)

    def test_run_inference_wrong_model_raises(self):
        node = EdgeNode(make_config())
        node._ai.load_model("/models/a.onnx")
        with pytest.raises(RuntimeError):
            node.run_inference("/models/b.onnx", [1])

    def test_run_inference_no_model_raises(self):
        node = EdgeNode(make_config())
        with pytest.raises(RuntimeError):
            node.run_inference("/models/a.onnx", [1])

    def test_store_and_forward_connected(self):
        node = EdgeNode(make_config())
        node.connect()
        forwarded = node.store_and_forward({"v": 1})
        assert forwarded == 1
        assert node.get_pending_data() == []
        assert node.get_status()["forwarded_records"] == 1

    def test_store_and_forward_disconnected_buffers(self):
        node = EdgeNode(make_config())
        forwarded = node.store_and_forward({"v": 1})
        assert forwarded == 0
        assert len(node.get_pending_data()) == 1

    def test_store_and_forward_offline_mode(self):
        node = EdgeNode(make_config(offline_mode=True))
        node.connect()
        forwarded = node.store_and_forward({"v": 1})
        assert forwarded == 0
        assert len(node.get_pending_data()) == 1

    def test_store_and_forward_multiple(self):
        node = EdgeNode(make_config())
        node.connect()
        node.store_and_forward({"v": 1})
        node.store_and_forward({"v": 2})
        node.store_and_forward({"v": 3})
        assert node.get_status()["forwarded_records"] == 3
        assert node.get_pending_data() == []


# ---------------------------------------------------------------------------
# FogNode
# ---------------------------------------------------------------------------


class TestFogNode:
    def test_register_and_get_nodes(self):
        fog = FogNode("fog-1")
        node = EdgeNode(make_config(node_id="e1"))
        assert fog.register_edge_node(node) is True
        assert fog.get_edge_nodes() == [node]

    def test_register_duplicate_returns_false(self):
        fog = FogNode("fog-1")
        node = EdgeNode(make_config(node_id="e1"))
        fog.register_edge_node(node)
        assert fog.register_edge_node(node) is False
        assert len(fog.get_edge_nodes()) == 1

    def test_unregister(self):
        fog = FogNode("fog-1")
        node = EdgeNode(make_config(node_id="e1"))
        fog.register_edge_node(node)
        assert fog.unregister_edge_node("e1") is True
        assert fog.get_edge_nodes() == []

    def test_unregister_unknown_returns_false(self):
        fog = FogNode("fog-1")
        assert fog.unregister_edge_node("nope") is False

    def test_empty_fog_id_raises(self):
        with pytest.raises(ValueError):
            FogNode("")

    def test_aggregate_data_empty(self):
        fog = FogNode("fog-1")
        agg = fog.aggregate_data()
        assert agg["node_count"] == 0
        assert agg["total_records"] == 0
        assert agg["mean_value"] is None

    def test_aggregate_data_with_nodes(self):
        fog = FogNode("fog-1")
        n1 = EdgeNode(make_config(node_id="e1"))
        n2 = EdgeNode(make_config(node_id="e2"))
        n1.process_sensor_data({"value": 10})
        n1.process_sensor_data({"value": 20})
        n2.process_sensor_data({"value": 30})
        fog.register_edge_node(n1)
        fog.register_edge_node(n2)
        agg = fog.aggregate_data()
        assert agg["node_count"] == 2
        assert agg["total_records"] == 3
        assert agg["per_node_records"] == {"e1": 2, "e2": 1}
        assert agg["mean_value"] == pytest.approx(20.0)

    def test_aggregate_ignores_non_numeric_values(self):
        fog = FogNode("fog-1")
        node = EdgeNode(make_config(node_id="e1"))
        node.process_sensor_data({"value": "not-a-number"})
        node.process_sensor_data({"value": 5})
        fog.register_edge_node(node)
        agg = fog.aggregate_data()
        assert agg["mean_value"] == pytest.approx(5.0)

    def test_offload_task(self):
        fog = FogNode("fog-1")
        node = EdgeNode(make_config(node_id="e1"))
        fog.register_edge_node(node)
        assignment = fog.offload_task({"id": "t1"}, "e1")
        assert assignment["task_id"] == "t1"
        assert assignment["assigned_to"] == "e1"
        assert assignment["status"] == "assigned"

    def test_offload_task_unknown_node_raises(self):
        fog = FogNode("fog-1")
        with pytest.raises(KeyError):
            fog.offload_task({"id": "t1"}, "ghost")

    def test_offload_task_invalid_task_raises(self):
        fog = FogNode("fog-1")
        node = EdgeNode(make_config(node_id="e1"))
        fog.register_edge_node(node)
        with pytest.raises(ValueError):
            fog.offload_task("not-a-dict", "e1")

    def test_get_tasks(self):
        fog = FogNode("fog-1")
        n1 = EdgeNode(make_config(node_id="e1"))
        n2 = EdgeNode(make_config(node_id="e2"))
        fog.register_edge_node(n1)
        fog.register_edge_node(n2)
        fog.offload_task({"id": "t1"}, "e1")
        fog.offload_task({"id": "t2"}, "e2")
        assert len(fog.get_tasks("e1")) == 1
        assert len(fog.get_tasks("e2")) == 1
        assert len(fog.get_tasks()) == 2


# ---------------------------------------------------------------------------
# EdgeCloudSync
# ---------------------------------------------------------------------------


class TestEdgeCloudSync:
    def test_sync_to_cloud_success(self):
        sync = EdgeCloudSync(make_config())
        status = sync.sync_to_cloud({"v": 1})
        assert status == "success"
        assert sync.get_last_sync_time() is not None

    def test_sync_to_cloud_offline_skips(self):
        sync = EdgeCloudSync(make_config(offline_mode=True))
        status = sync.sync_to_cloud({"v": 1})
        assert status == "skipped"
        assert sync.get_last_sync_time() is None

    def test_sync_from_cloud(self):
        sync = EdgeCloudSync(make_config())
        sync.sync_to_cloud({"v": 1})
        # default client stores under the data key; commands key is empty
        assert sync.sync_from_cloud() is None

    def test_get_sync_status(self):
        sync = EdgeCloudSync(make_config(node_id="edge-7"))
        status = sync.get_sync_status()
        assert status["node_id"] == "edge-7"
        assert status["last_status"] == "never"
        assert status["sync_count"] == 0
        assert status["offline_mode"] is False

    def test_sync_count_increments(self):
        sync = EdgeCloudSync(make_config())
        sync.sync_to_cloud({"v": 1})
        sync.sync_to_cloud({"v": 2})
        assert sync.get_sync_status()["sync_count"] == 2

    def test_resolve_conflicts_local(self):
        sync = EdgeCloudSync(make_config())
        local = {"v": 1}
        remote = {"v": 2}
        assert sync.resolve_conflicts(local, remote, "local") is local

    def test_resolve_conflicts_remote(self):
        sync = EdgeCloudSync(make_config())
        local = {"v": 1}
        remote = {"v": 2}
        assert sync.resolve_conflicts(local, remote, "remote") is remote

    def test_resolve_conflicts_timestamp(self):
        sync = EdgeCloudSync(make_config())
        local = {"v": 1, "timestamp": 100}
        remote = {"v": 2, "timestamp": 200}
        assert sync.resolve_conflicts(local, remote, "timestamp") is remote

    def test_resolve_conflicts_timestamp_tie_goes_local(self):
        sync = EdgeCloudSync(make_config())
        local = {"v": 1, "timestamp": 100}
        remote = {"v": 2, "timestamp": 100}
        assert sync.resolve_conflicts(local, remote, "timestamp") is local

    def test_resolve_conflicts_merge(self):
        sync = EdgeCloudSync(make_config())
        local = {"a": 1, "b": 2}
        remote = {"b": 3, "c": 4}
        merged = sync.resolve_conflicts(local, remote, "merge")
        assert merged == {"a": 1, "b": 2, "c": 4}

    def test_resolve_conflicts_merge_non_mapping_falls_back(self):
        sync = EdgeCloudSync(make_config())
        local = [1, 2, 3]
        remote = [4, 5, 6]
        result = sync.resolve_conflicts(local, remote, "merge")
        assert result is local

    def test_resolve_conflicts_invalid_strategy_raises(self):
        sync = EdgeCloudSync(make_config())
        with pytest.raises(ValueError):
            sync.resolve_conflicts({}, {}, "bogus")

    def test_resolve_conflicts_default_strategy(self):
        sync = EdgeCloudSync(make_config())
        local = {"v": 1, "timestamp": 1}
        remote = {"v": 2, "timestamp": 2}
        assert sync.resolve_conflicts(local, remote) is remote


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_all_exports_available(self):
        import apex_autopilot_optimization.edge as edge_pkg

        for name in ("EdgeNode", "EdgeConfig", "EdgeAI", "FogNode", "EdgeCloudSync"):
            assert hasattr(edge_pkg, name)
            assert name in edge_pkg.__all__
