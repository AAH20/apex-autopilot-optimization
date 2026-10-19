"""YoloIngestor: ingest /Drone{id}/yolo/detections, apply filtering rules.

Ingestion adapter contract (Section 3 of the perception pipeline spec):
Input: one ``YoloDetectionArray`` + source ``camera_id`` + source ``drone_id``.
Output: list of ``RawDetection``.

Validates the message (non-null header, stamp not in the future by more than
``CLOCK_TOLERANCE_S``, at least one hypothesis per detection), converts ROS
time -> epoch seconds, applies per-class confidence gating, and drops
malformed detections. No inference happens here by default.
"""

from __future__ import annotations

import time
from typing import Any

from apex_autopilot_optimization.perception import (
    CLASS_MAP,
    ConfidenceTier,
    RawDetection,
    YoloDetection,
    YoloDetectionArray,
)

# Clock tolerance for future-stamp rejection (epoch seconds).
CLOCK_TOLERANCE_S = 0.05
CONF_MIN = 0.25


class YoloIngestor:
    """Adapts AAS ``YoloDetectionArray`` messages into ``RawDetection``s."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config) if config is not None else {}
        self.conf_min = float(self.config.get("conf", {}).get("min", CONF_MIN))
        tiers = self.config.get("conf", {}).get("tiers", {})
        self.tier_min = {
            ConfidenceTier.WTA_CRITICAL: float(tiers.get("wta_critical", 0.60)),
            ConfidenceTier.STANDARD: float(tiers.get("standard", 0.45)),
            ConfidenceTier.FLOOR: self.conf_min,
        }
        self.clock_tolerance = float(self.config.get("clock_tolerance_s", CLOCK_TOLERANCE_S))

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> YoloIngestor:
        return cls(config)

    def _min_confidence_for(self, class_name: str) -> float:
        entry = CLASS_MAP.get(class_name.strip().lower())
        if entry is None:
            return self.tier_min[ConfidenceTier.STANDARD]
        return self.tier_min[entry.tier]

    def ingest(
        self,
        detection_array: YoloDetectionArray,
        drone_id: int,
        camera_id: int,
        now: float | None = None,
    ) -> list[RawDetection]:
        """Parse, validate, and confidence-gate a detection array.

        Returns the list of ``RawDetection``s that passed the per-class
        confidence floor (filtered, not yet tracked/promoted).
        """
        if detection_array is None:
            raw: list[RawDetection] = []
            return raw

        now = now if now is not None else time.time()
        raw = []

        for det in detection_array.detections:
            try:
                detection = self._convert(det, drone_id, camera_id)
            except ValueError:
                continue

            # Clock sync: drop stamps in the future by more than tolerance.
            if detection.stamp > now + self.clock_tolerance:
                continue

            # Per-class confidence gating (detection floor never bypassed).
            min_conf = self._min_confidence_for(detection.class_name)
            if detection.confidence < min_conf:
                continue

            raw.append(detection)

        return raw

    @staticmethod
    def _convert(det: YoloDetection, drone_id: int, camera_id: int) -> RawDetection:
        if not det.class_id:
            raise ValueError("empty class_id")
        # Bounding box: normalized 0..1 center/size -> (cx, cy, w, h).
        cx = det.center_x
        cy = det.center_y
        w = det.size_x
        h = det.size_y
        if det.score < 0.0 or det.score > 1.0:
            raise ValueError(f"score out of range: {det.score}")
        return RawDetection(
            camera_id=camera_id,
            drone_id=drone_id,
            class_name=det.class_id,
            confidence=float(det.score),
            bbox_px=(cx, cy, w, h),
            bearing_deg=float(det.azimuth_deg),
            elevation_deg=float(det.elevation_deg),
            angular_width_deg=float(det.depth_m) if det.depth_m and det.depth_m > 0 else 0.0,
            stamp=float(det.header_stamp),
            frame_id=det.header_frame_id,
        )
