"""Perception package: YOLO detections -> WTA target inputs.

Implements the Option B perception pipeline (see
docs/architecture/perception-pipeline-spec.md):

- ``YoloIngestor``: ingest ``YoloDetectionArray`` messages, apply confidence
  gating, emit ``RawDetection`` objects.
- ``DetectionTracker``: per-track EWMA smoothing, min-detections promotion,
  association gate, staleness TTL.
- ``ClassMapper``: COCO class -> vendor-agnostic WTA target type mapping.
- ``LatencyTracker``: per-stage timing against the 100 ms budget.
- ``TargetTransform``: bearing + drone EKF state + extrinsics -> ENU Pose3D
  (StateVector-compatible target inputs for the WTA solver).

All types are vendor-agnostic (no V-BAT / Shield AI nomenclature).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

__all__ = [
    "TargetType",
    "SizeClass",
    "ConfidenceTier",
    "ClassMapEntry",
    "RawDetection",
    "PerceptionTarget",
    "PerceptionTargetArray",
    "YoloDetection",
    "YoloDetectionArray",
    "Extrinsics",
]


class TargetType(Enum):
    """Vendor-agnostic WTA target types (COCO class -> target type)."""

    PERSONNEL = "personnel"
    GROUND_VEHICLE = "ground_vehicle"
    LIGHT_GROUND_VEHICLE = "light_ground_vehicle"
    MARITIME_VESSEL = "maritime_vessel"
    FIXED_WING_AIRCRAFT = "fixed_wing_aircraft"
    AERIAL_CLUTTER = "aerial_clutter"
    INFRASTRUCTURE = "infrastructure"
    UNCLASSIFIED_TARGET = "unclassified_target"


class SizeClass(Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ConfidenceTier(Enum):
    WTA_CRITICAL = "wta_critical"
    STANDARD = "standard"
    FLOOR = "floor"


@dataclass(frozen=True, slots=True)
class ClassMapEntry:
    """Single COCO-class -> WTA target mapping row."""

    coco_class: str
    target_type: TargetType
    size_class: SizeClass
    priority: float
    tier: ConfidenceTier
    wta_treatment: str = ""


# COCO class name -> ClassMapEntry (vendor-agnostic mapping table).
CLASS_MAP: dict[str, ClassMapEntry] = {
    "person": ClassMapEntry(
        "person",
        TargetType.PERSONNEL,
        SizeClass.SMALL,
        0.7,
        ConfidenceTier.WTA_CRITICAL,
        "high-value, small cross-section",
    ),
    "car": ClassMapEntry(
        "car", TargetType.GROUND_VEHICLE, SizeClass.MEDIUM, 0.6, ConfidenceTier.STANDARD
    ),
    "truck": ClassMapEntry(
        "truck", TargetType.GROUND_VEHICLE, SizeClass.LARGE, 0.7, ConfidenceTier.STANDARD
    ),
    "bus": ClassMapEntry(
        "bus", TargetType.GROUND_VEHICLE, SizeClass.LARGE, 0.7, ConfidenceTier.STANDARD
    ),
    "motorcycle": ClassMapEntry(
        "motorcycle",
        TargetType.LIGHT_GROUND_VEHICLE,
        SizeClass.SMALL,
        0.5,
        ConfidenceTier.STANDARD,
    ),
    "bicycle": ClassMapEntry(
        "bicycle",
        TargetType.LIGHT_GROUND_VEHICLE,
        SizeClass.SMALL,
        0.4,
        ConfidenceTier.STANDARD,
    ),
    "boat": ClassMapEntry(
        "boat", TargetType.MARITIME_VESSEL, SizeClass.MEDIUM, 0.6, ConfidenceTier.STANDARD
    ),
    "airplane": ClassMapEntry(
        "airplane",
        TargetType.FIXED_WING_AIRCRAFT,
        SizeClass.LARGE,
        0.8,
        ConfidenceTier.STANDARD,
        "air-priority",
    ),
    "bird": ClassMapEntry(
        "bird",
        TargetType.AERIAL_CLUTTER,
        SizeClass.SMALL,
        0.1,
        ConfidenceTier.WTA_CRITICAL,
        "suppressed unless include_clutter=true",
    ),
    "traffic light": ClassMapEntry(
        "traffic light",
        TargetType.INFRASTRUCTURE,
        SizeClass.SMALL,
        0.2,
        ConfidenceTier.WTA_CRITICAL,
    ),
    "stop sign": ClassMapEntry(
        "stop sign", TargetType.INFRASTRUCTURE, SizeClass.SMALL, 0.2, ConfidenceTier.STANDARD
    ),
}

# Per-tier minimum confidence (detection floor never bypassed).
TIER_MIN_CONFIDENCE: dict[ConfidenceTier, float] = {
    ConfidenceTier.WTA_CRITICAL: 0.60,
    ConfidenceTier.STANDARD: 0.45,
    ConfidenceTier.FLOOR: 0.25,
}

# Typical physical size (m) per size class, used for range-from-angular-width.
TYPICAL_SIZE_M: dict[SizeClass, float] = {
    SizeClass.SMALL: 0.5,
    SizeClass.MEDIUM: 2.0,
    SizeClass.LARGE: 6.0,
}

# Default mapping for any COCO class not listed above.
DEFAULT_ENTRY = ClassMapEntry(
    coco_class="<other>",
    target_type=TargetType.UNCLASSIFIED_TARGET,
    size_class=SizeClass.MEDIUM,
    priority=0.3,
    tier=ConfidenceTier.STANDARD,
)


@dataclass(frozen=True, slots=True)
class YoloDetection:
    """Wire-compatible mirror of apex_telemetry_msgs/msg/YoloDetection.msg."""

    header_stamp: float  # epoch seconds
    header_frame_id: str
    drone_id: int
    class_id: str
    score: float  # 0..1 confidence
    center_x: float  # normalized 0..1
    center_y: float  # normalized 0..1
    size_x: float  # normalized 0..1
    size_y: float  # normalized 0..1
    azimuth_deg: float  # deg, bearing
    elevation_deg: float  # deg
    depth_m: float  # m, NaN when unavailable


@dataclass(frozen=True, slots=True)
class YoloDetectionArray:
    """Wire-compatible mirror of apex_telemetry_msgs/msg/YoloDetectionArray.msg."""

    detections: tuple[YoloDetection, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RawDetection:
    """Normalised output of the ingestion adapter (Section 3 of the spec)."""

    camera_id: int
    drone_id: int
    class_name: str
    confidence: float
    bbox_px: tuple[float, float, float, float]  # (cx, cy, w, h) pixels
    bearing_deg: float
    elevation_deg: float
    angular_width_deg: float
    stamp: float  # epoch seconds
    frame_id: str


@dataclass(slots=True)
class Track:
    """Internal per-track EWMA state (Section 4 of the spec)."""

    track_id: int
    drone_id: int
    camera_id: int
    class_name: str
    detections: list[RawDetection] = field(default_factory=list)
    # EWMA-smoothed state.
    cx_hat: float = 0.0
    cy_hat: float = 0.0
    bearing_hat: float = 0.0
    elevation_hat: float = 0.0
    angular_width_hat: float = 0.0
    conf_hat: float = 0.0
    alpha: float = 0.35
    confirmed: bool = False
    last_seen: float = 0.0
    first_seen: float = 0.0

    def associated_with(self, detection: RawDetection, config: dict[str, Any]) -> bool:
        """Association gate: same class + bearing/elevation/width within gate."""
        if self.class_name != detection.class_name:
            return False
        bearing_gate = float(config.get("bearing_gate_deg", 5.0))
        elevation_gate = float(config.get("elevation_gate_deg", 5.0))
        width_gate_pct = float(config.get("angular_width_gate_pct", 0.30))
        if abs(self.bearing_hat - detection.bearing_deg) > bearing_gate:
            return False
        if abs(self.elevation_hat - detection.elevation_deg) > elevation_gate:
            return False
        ref = abs(self.angular_width_hat)
        width_gate = width_gate_pct * ref
        return not (
            ref > 0.0 and abs(self.angular_width_hat - detection.angular_width_deg) > width_gate
        )

    def update(self, detection: RawDetection) -> None:
        """EWMA update: xhat = alpha*z + (1-alpha)*xhat_prev.

        The first detection seeds the smoothed state directly; subsequent
        detections apply the EWMA recursion.
        """
        a = self.alpha
        if not self.detections:
            # Seed with the first detection.
            self.cx_hat = float(detection.bbox_px[0])
            self.cy_hat = float(detection.bbox_px[1])
            self.bearing_hat = float(detection.bearing_deg)
            self.elevation_hat = float(detection.elevation_deg)
            self.angular_width_hat = float(detection.angular_width_deg)
            self.conf_hat = float(detection.confidence)
        else:
            self.cx_hat = a * detection.bbox_px[0] + (1.0 - a) * self.cx_hat
            self.cy_hat = a * detection.bbox_px[1] + (1.0 - a) * self.cy_hat
            self.bearing_hat = a * detection.bearing_deg + (1.0 - a) * self.bearing_hat
            self.elevation_hat = a * detection.elevation_deg + (1.0 - a) * self.elevation_hat
            self.angular_width_hat = (
                a * detection.angular_width_deg + (1.0 - a) * self.angular_width_hat
            )
            self.conf_hat = a * detection.confidence + (1.0 - a) * self.conf_hat
        self.detections.append(detection)
        self.last_seen = detection.stamp
        if self.first_seen == 0.0:
            self.first_seen = detection.stamp

    def jitter_m(self) -> float:
        """EWMA position change first->last detection (proxy in pixel space)."""
        if len(self.detections) < 2:
            return 0.0
        first = self.detections[0]
        last = self.detections[-1]
        return float(
            np.hypot(last.bbox_px[0] - first.bbox_px[0], last.bbox_px[1] - first.bbox_px[1])
        )

    def detection_count_in_window(self, now: float, window_s: float) -> int:
        return sum(1 for d in self.detections if now - d.stamp <= window_s)

    def is_stale(self, now: float, ttl_s: float) -> bool:
        return now - self.last_seen > ttl_s


@dataclass(frozen=True, slots=True)
class PerceptionTarget:
    """Confirmed track converted to a WTA target input (Section 8 of the spec)."""

    target_id: str
    source_drone_id: int
    source_camera_ids: tuple[int, ...]
    pose: Any  # Pose3D (ENU)
    target_type: TargetType
    confidence: float
    stamp: float
    bearing_deg: float
    elevation_deg: float
    angular_width_deg: float
    position_cov_m: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]


@dataclass(frozen=True, slots=True)
class PerceptionTargetArray:
    targets: tuple[PerceptionTarget, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Extrinsics:
    """Camera mount extrinsics (drone body -> camera optical frame)."""

    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    tx_m: float = 0.0
    ty_m: float = 0.0
    tz_m: float = 0.0


# Submodule imports (placed after all type definitions to avoid import cycles).
from apex_autopilot_optimization.perception.ingestor import YoloIngestor  # noqa: E402
from apex_autopilot_optimization.perception.latency import LatencyTracker  # noqa: E402
from apex_autopilot_optimization.perception.mapper import ClassMapper  # noqa: E402
from apex_autopilot_optimization.perception.tracker import DetectionTracker  # noqa: E402
from apex_autopilot_optimization.perception.transform import TargetTransform  # noqa: E402

__all__ = [
    "TargetType",
    "SizeClass",
    "ConfidenceTier",
    "ClassMapEntry",
    "RawDetection",
    "PerceptionTarget",
    "PerceptionTargetArray",
    "YoloDetection",
    "YoloDetectionArray",
    "Extrinsics",
    "Track",
    "YoloIngestor",
    "DetectionTracker",
    "ClassMapper",
    "LatencyTracker",
    "TargetTransform",
    "CLASS_MAP",
    "TIER_MIN_CONFIDENCE",
    "DEFAULT_ENTRY",
    "TYPICAL_SIZE_M",
]
