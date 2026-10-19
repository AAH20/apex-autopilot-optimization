"""Unit tests for the perception package (TDD: RED->GREEN->REFACTOR).

Covers YoloIngestor, DetectionTracker, ClassMapper, LatencyTracker, and
TargetTransform against the perception pipeline spec.
"""

from __future__ import annotations

import time

import pytest

from apex_autopilot_optimization.core.types import Pose3D, StateVector, Velocity3D
from apex_autopilot_optimization.perception import (
    ClassMapper,
    ConfidenceTier,
    DetectionTracker,
    Extrinsics,
    LatencyTracker,
    PerceptionTarget,
    RawDetection,
    TargetTransform,
    TargetType,
    Track,
    YoloDetection,
    YoloDetectionArray,
    YoloIngestor,
)

# --------------------------------------------------------------------------- helpers


def _det(
    drone_id=1,
    class_id="car",
    score=0.8,
    cx=0.5,
    cy=0.5,
    sx=0.1,
    sy=0.1,
    azimuth=10.0,
    elevation=5.0,
    depth=0.0,
    stamp=1000.0,
    frame_id="cam0",
):
    return YoloDetection(
        header_stamp=stamp,
        header_frame_id=frame_id,
        drone_id=drone_id,
        class_id=class_id,
        score=score,
        center_x=cx,
        center_y=cy,
        size_x=sx,
        size_y=sy,
        azimuth_deg=azimuth,
        elevation_deg=elevation,
        depth_m=depth,
    )


def _array(*dets):
    return YoloDetectionArray(detections=tuple(dets))


def _ingest(
    ing: YoloIngestor, *dets, now: float = 2000.0, drone_id: int = 1, camera_id: int = 0
) -> list[RawDetection]:
    return ing.ingest(_array(*dets), drone_id, camera_id, now=now)


def _track(
    track_id=1,
    drone_id=1,
    camera_id=0,
    class_name="car",
    bearing=0.0,
    elevation=0.0,
    width=0.0,
    confidence=0.8,
    stamp=1000.0,
):
    from apex_autopilot_optimization.perception import Track

    return Track(
        track_id=track_id,
        drone_id=drone_id,
        camera_id=camera_id,
        class_name=class_name,
        bearing_hat=bearing,
        elevation_hat=elevation,
        angular_width_hat=width,
        conf_hat=confidence,
        last_seen=stamp,
    )


def _raw(
    drone_id=1,
    camera_id=0,
    class_name="car",
    confidence=0.8,
    stamp=1000.0,
    bearing=10.0,
    elevation=5.0,
    width=0.0,
    cx=0.5,
    cy=0.5,
    w=0.1,
    h=0.1,
    frame_id="cam0",
):
    return RawDetection(
        camera_id=camera_id,
        drone_id=drone_id,
        class_name=class_name,
        confidence=confidence,
        bbox_px=(cx, cy, w, h),
        bearing_deg=bearing,
        elevation_deg=elevation,
        angular_width_deg=width,
        stamp=stamp,
        frame_id=frame_id,
    )


def _state(x=0.0, y=0.0, z=10.0, yaw=0.0, stamp=None):
    if stamp is None:
        stamp = time.time()
    return StateVector(
        pose=Pose3D(x=x, y=y, z=z, yaw=yaw),
        velocity=Velocity3D(0, 0, 0),
        timestamp=stamp,
    )


# --------------------------------------------------------------------------- YoloIngestor


class TestYoloIngestor:
    def test_ingest_empty_array(self):
        ing = YoloIngestor()
        assert ing.ingest(_array(), drone_id=1, camera_id=0) == []

    def test_ingest_null_array(self):
        ing = YoloIngestor()
        assert ing.ingest(None, drone_id=1, camera_id=0) == []

    def test_ingest_converts_fields(self):
        ing = YoloIngestor()
        arr = _array(
            _det(class_id="airplane", score=0.9, cx=0.6, cy=0.4, azimuth=12.0, elevation=3.0)
        )
        outs = ing.ingest(arr, 7, 2, 2000.0)
        assert len(outs) == 1
        d = outs[0]
        assert d.drone_id == 7
        assert d.camera_id == 2
        assert d.class_name == "airplane"
        assert d.confidence == pytest.approx(0.9)
        assert d.bbox_px == pytest.approx((0.6, 0.4, 0.1, 0.1))
        assert d.bearing_deg == pytest.approx(12.0)
        assert d.elevation_deg == pytest.approx(3.0)
        assert d.stamp == pytest.approx(1000.0)
        assert d.frame_id == "cam0"

    def test_ingest_confidence_gate_standard(self):
        ing = YoloIngestor()
        # car = standard tier, min 0.45
        accepted = _ingest(ing, _det(class_id="car", score=0.5))
        assert len(accepted) == 1
        rejected = _ingest(ing, _det(class_id="car", score=0.4))
        assert rejected == []

    def test_ingest_confidence_gate_wta_critical(self):
        ing = YoloIngestor()
        # person = wta_critical tier, min 0.60
        accepted = _ingest(ing, _det(class_id="person", score=0.7))
        assert len(accepted) == 1
        rejected = _ingest(ing, _det(class_id="person", score=0.5))
        assert rejected == []

    def test_ingest_confidence_floor_never_bypassed(self):
        ing = YoloIngestor(config={"conf": {"min": 0.25}})
        rejected = _ingest(ing, _det(class_id="car", score=0.24))
        assert rejected == []

    def test_ingest_drops_future_stamp(self):
        ing = YoloIngestor()
        now = 1000.0
        # stamp 200 ms in the future > 50 ms tolerance -> dropped
        dropped = _ingest(ing, _det(stamp=now + 0.2), now=now)
        assert dropped == []
        # within tolerance -> accepted
        accepted = _ingest(ing, _det(stamp=now + 0.02), now=now)
        assert len(accepted) == 1

    def test_ingest_drops_empty_class(self):
        ing = YoloIngestor()
        det = _det(class_id="", score=0.9)
        dropped = ing.ingest(_array(det), drone_id=1, camera_id=0, now=2000.0)
        assert dropped == []

    def test_ingest_tier_config(self):
        ing = YoloIngestor(config={"conf": {"tiers": {"standard": 0.90}}})
        low = _det(class_id="car", score=0.5)
        assert ing.ingest(_array(low), drone_id=1, camera_id=0, now=2000.0) == []
        high = _det(class_id="car", score=0.95)
        assert len(ing.ingest(_array(high), drone_id=1, camera_id=0, now=2000.0)) == 1


# --------------------------------------------------------------------------- DetectionTracker


class TestDetectionTracker:
    def _make_tracker(self):
        return DetectionTracker(
            config={
                "filtering": {
                    "min_detections": 3,
                    "promotion_window_s": 0.5,
                    "max_jitter_m": 2.0,
                    "stale_ttl_s": 0.2,
                    "ewma_alpha": 0.35,
                    "bearing_gate_deg": 5.0,
                    "elevation_gate_deg": 5.0,
                    "angular_width_gate_pct": 0.30,
                }
            }
        )

    def test_ewma_matches_hand_computed(self):
        alpha = 0.35
        # Test the EWMA recursion directly on a Track (bypass association gate).
        t = Track(track_id=1, drone_id=1, camera_id=0, class_name="car", alpha=alpha)
        d1 = _raw(bearing=10.0, elevation=5.0, width=1.0, confidence=0.8, stamp=1000.0)
        t.update(d1)
        # First detection seeds the state directly.
        assert t.bearing_hat == pytest.approx(10.0)
        assert t.conf_hat == pytest.approx(0.8)

        # Second detection: xhat = alpha*z + (1-alpha)*xhat_prev
        d2 = _raw(bearing=20.0, elevation=5.0, width=1.0, confidence=0.8, stamp=1000.1)
        t.update(d2)
        expected = alpha * 20.0 + (1.0 - alpha) * 10.0
        assert t.bearing_hat == pytest.approx(expected)

    def test_promotion_requires_three_within_500ms(self):
        trk = self._make_tracker()
        now = 1000.0
        # Two detections -> tentative, not confirmed.
        trk.update([_raw(bearing=10.0, stamp=now)], now)
        trk.update([_raw(bearing=10.0, stamp=now + 0.1)], now + 0.1)
        assert trk.confirmed_tracks(now + 0.2) == []

        # Third detection within 500 ms window -> confirmed.
        trk.update([_raw(bearing=10.0, stamp=now + 0.2)], now + 0.2)
        confirmed = trk.confirmed_tracks(now + 0.3)
        assert len(confirmed) == 1
        assert confirmed[0].confirmed is True

    def test_two_of_three_stays_tentative(self):
        trk = self._make_tracker()
        now = 1000.0
        trk.update([_raw(bearing=10.0, stamp=now)], now)
        trk.update([_raw(bearing=10.0, stamp=now + 0.1)], now + 0.1)
        # Window advances past 500 ms with only 2 detections -> never promoted.
        assert trk.confirmed_tracks(now + 0.6) == []

    def test_staleness_drops_track(self):
        trk = self._make_tracker()
        now = 1000.0
        trk.update([_raw(bearing=10.0, stamp=now)], now)
        # Advance beyond stale_ttl_s (200 ms) with no new detection.
        assert trk.update([], now + 0.3) == []
        assert trk.all_tracks() == []

    def test_association_gate_merges_close_detections(self):
        trk = self._make_tracker()
        now = 1000.0
        trk.update([_raw(bearing=10.0, stamp=now)], now)
        track_id = trk.all_tracks()[0].track_id
        # Close detection -> same track (within bearing/elevation gate).
        trk.update([_raw(bearing=12.0, stamp=now + 0.05)], now + 0.05)
        assert len(trk.all_tracks()) == 1
        assert trk.all_tracks()[0].track_id == track_id

    def test_association_gate_splits_far_detections(self):
        trk = self._make_tracker()
        now = 1000.0
        trk.update([_raw(bearing=10.0, stamp=now)], now)
        # Far detection (>5 deg bearing) -> new track spawned.
        trk.update([_raw(bearing=50.0, stamp=now + 0.05)], now + 0.05)
        assert len(trk.all_tracks()) == 2

    def test_class_change_resets_track(self):
        trk = self._make_tracker()
        now = 1000.0
        trk.update([_raw(class_name="car", bearing=10.0, stamp=now)], now)
        # Same track but different class -> should spawn new track (gate rejects).
        trk.update([_raw(class_name="airplane", bearing=10.0, stamp=now + 0.05)], now + 0.05)
        assert len(trk.all_tracks()) == 2

    def test_jitter_above_threshold_blocks_promotion(self):
        trk = self._make_tracker()
        now = 1000.0
        # 3 detections within window but large position jump -> jitter > 2.0 m.
        trk.update([_raw(bearing=10.0, cx=0.5, cy=0.5, stamp=now)], now)
        trk.update([_raw(bearing=10.0, cx=0.51, cy=0.51, stamp=now + 0.1)], now + 0.1)
        trk.update([_raw(bearing=10.0, cx=2.0, cy=2.0, stamp=now + 0.2)], now + 0.2)
        assert trk.confirmed_tracks(now + 0.3) == []

    def test_defaults_from_config(self):
        trk = DetectionTracker.from_config({"filtering": {"min_detections": 3, "ewma_alpha": 0.35}})
        assert trk.min_detections == 3
        assert trk.ewma_alpha == pytest.approx(0.35)


# --------------------------------------------------------------------------- ClassMapper


class TestClassMapper:
    def test_full_coco_table(self):
        m = ClassMapper()
        expected = {
            "person": (TargetType.PERSONNEL, 0.7, ConfidenceTier.WTA_CRITICAL),
            "car": (TargetType.GROUND_VEHICLE, 0.6, ConfidenceTier.STANDARD),
            "truck": (TargetType.GROUND_VEHICLE, 0.7, ConfidenceTier.STANDARD),
            "bus": (TargetType.GROUND_VEHICLE, 0.7, ConfidenceTier.STANDARD),
            "motorcycle": (TargetType.LIGHT_GROUND_VEHICLE, 0.5, ConfidenceTier.STANDARD),
            "bicycle": (TargetType.LIGHT_GROUND_VEHICLE, 0.4, ConfidenceTier.STANDARD),
            "boat": (TargetType.MARITIME_VESSEL, 0.6, ConfidenceTier.STANDARD),
            "airplane": (TargetType.FIXED_WING_AIRCRAFT, 0.8, ConfidenceTier.STANDARD),
            "bird": (TargetType.AERIAL_CLUTTER, 0.1, ConfidenceTier.WTA_CRITICAL),
            "traffic light": (TargetType.INFRASTRUCTURE, 0.2, ConfidenceTier.WTA_CRITICAL),
            "stop sign": (TargetType.INFRASTRUCTURE, 0.2, ConfidenceTier.STANDARD),
        }
        for cls, (tt, prio, tier) in expected.items():
            entry = m.map(cls)
            assert entry.target_type is tt
            assert entry.priority == prio
            assert entry.tier is tier

    def test_unknown_class_fallback(self):
        m = ClassMapper()
        entry = m.map("weird_thermal_class")
        assert entry.target_type is TargetType.UNCLASSIFIED_TARGET
        assert entry.priority == pytest.approx(0.3)

    def test_min_confidence_per_tier(self):
        m = ClassMapper()
        assert m.min_confidence("person") == pytest.approx(0.60)
        assert m.min_confidence("car") == pytest.approx(0.45)
        assert m.min_confidence("unknown_thing") == pytest.approx(0.45)

    def test_clutter_suppressed_by_default(self):
        m = ClassMapper(include_clutter=False)
        assert m.publishable("bird") is False

    def test_clutter_published_when_enabled(self):
        m = ClassMapper(include_clutter=True)
        assert m.publishable("bird") is True

    def test_case_insensitive(self):
        m = ClassMapper()
        assert m.map("PERSON").target_type is TargetType.PERSONNEL
        assert m.map("  Airplane  ").target_type is TargetType.FIXED_WING_AIRCRAFT

    def test_from_config(self):
        m = ClassMapper.from_config({"include_clutter": True})
        assert m.include_clutter is True

    def test_map_is_total(self):
        m = ClassMapper()
        for cls in ["", "   ", "person", "car", "totally made up"]:
            entry = m.map(cls)
            assert entry.target_type is not None
            assert 0.0 <= entry.priority <= 1.0


# --------------------------------------------------------------------------- LatencyTracker


class TestLatencyTracker:
    def test_stage_budgets_total_100(self):
        lt = LatencyTracker()
        total = sum(lt.budgets.values())
        assert total == pytest.approx(100.0)

    def test_per_stage_p95_within_budget(self):
        lt = LatencyTracker()
        for _ in range(100):
            with lt.stage("inference"):
                pass  # ~0 ms, well within 40 ms budget
        lt.assert_budgets()  # should not raise

    def test_p95_stage_over_budget_raises(self):
        lt = LatencyTracker()
        # Record a single slow inference sample > 40 ms budget.
        lt.record("inference", 45.0)
        with pytest.raises(AssertionError):
            lt.assert_budgets()

    def test_end_to_end_p95_target(self):
        lt = LatencyTracker()
        for name, budget in lt.budgets.items():
            lt.record(name, budget * 0.9)  # each stage at 90% of budget
        lt.assert_end_to_end()  # sum = 90 ms <= 92 ms target

    def test_end_to_end_over_target_raises(self):
        lt = LatencyTracker()
        for name in lt.budgets:
            lt.record(name, 9.5)  # 10 stages * 9.5 = 95 ms > 92 ms target
        with pytest.raises(AssertionError):
            lt.assert_end_to_end()

    def test_p95_computation(self):
        lt = LatencyTracker()
        for i in range(20):
            lt.record("ingestion", float(i))
        # p95 of 0..19 -> ceil(0.95*20)-1 = 18 -> value 18.0
        assert lt.p95("ingestion") == pytest.approx(18.0)

    def test_from_config(self):
        cfg = {"latency_budget_ms": {"inference": 30, "p95_target_ms": 90}}
        lt = LatencyTracker.from_config(cfg)
        assert lt.budgets["inference"] == pytest.approx(30.0)
        assert lt.p95_target_ms == pytest.approx(90.0)


# --------------------------------------------------------------------------- TargetTransform


class TestTargetTransform:
    def test_transform_bearing_to_enu_pose(self):
        tf = TargetTransform()
        state = _state(x=0.0, y=0.0, z=10.0, yaw=0.0, stamp=1000.0)
        track = _track(
            track_id=3,
            drone_id=1,
            camera_id=0,
            bearing=0.0,
            elevation=0.0,
            width=0.0,
            confidence=0.8,
            stamp=1000.0,
        )
        out = tf.transform([track], state, now=1000.0)
        assert len(out.targets) == 1
        t = out.targets[0]
        assert isinstance(t, PerceptionTarget)
        assert t.target_id == "drone1:track3"
        assert t.source_drone_id == 1
        assert t.confidence == pytest.approx(0.8)
        assert t.stamp == pytest.approx(1000.0)
        # bearing 0 deg -> straight ahead (drone +x axis at yaw 0)
        assert t.pose.x > 0.0
        assert t.pose.z == pytest.approx(10.0)

    def test_stale_drone_state_drops_target(self):
        tf = TargetTransform()
        state = _state(stamp=1000.0)
        track = _track(
            drone_id=1, camera_id=0, bearing=0.0, elevation=0.0, confidence=0.8, stamp=1000.0
        )
        # now is 200 ms after state stamp > max_state_age_s (100 ms)
        out = tf.transform([track], state, now=1000.2)
        assert out.targets == ()

    def test_covariance_reflects_alignment_accuracy(self):
        tf = TargetTransform(config={"transform": {"alignment_accuracy_m": 0.02}})
        cov = tf._covariance_matrix()
        assert cov[0][0] == pytest.approx(0.02 * 0.02)
        assert cov[1][1] == pytest.approx(0.02 * 0.02)
        assert cov[2][2] == pytest.approx((0.04) * (0.04))

    def test_transform_uses_extrinsics(self):
        tf = TargetTransform(extrinsics=Extrinsics(yaw_deg=90.0))
        state = _state(x=0.0, y=0.0, z=10.0, yaw=0.0, stamp=1000.0)
        track = _track(
            track_id=1,
            drone_id=1,
            camera_id=0,
            bearing=0.0,
            elevation=0.0,
            width=0.0,
            confidence=0.8,
            stamp=1000.0,
        )
        out = tf.transform([track], state, now=1000.0)
        assert len(out.targets) == 1
        t = out.targets[0]
        # Camera yaw 90 deg rotates the forward bearing to +y (left) in ENU.
        assert t.pose.y > 0.0

    def test_no_drone_state_returns_empty(self):
        tf = TargetTransform()
        out = tf.transform([], None, now=1000.0)
        assert out.targets == ()

    def test_track_to_enu_position_convenience(self):
        tf = TargetTransform()
        state = _state(x=0.0, y=0.0, z=10.0, yaw=0.0, stamp=1000.0)
        pose = tf.track_to_enu_position(0.0, 0.0, 0.0, "car", state)
        assert isinstance(pose, Pose3D)
        assert pose.x > 0.0
