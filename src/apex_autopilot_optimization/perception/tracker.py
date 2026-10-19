"""DetectionTracker: per-track EWMA smoothing, promotion, association, staleness.

Implements Section 4 of the perception pipeline spec:

- Per-track EWMA smoothing: ``xhat = alpha * z + (1 - alpha) * xhat_prev``,
  alpha = 0.35, applied to bearing/elevation/width/confidence.
- Min-detections promotion: a track is tentative until >= MIN_DETECTIONS (3)
  detections of the same class are associated within PROMOTION_WINDOW_S (500 ms)
  and EWMA position change is within MAX_JITTER_M (2.0 m).
- Association gate: same class + |Δbearing| <= 5 deg + |Δelevation| <= 5 deg +
  |Δangular_width| <= 30% of tracked width.
- Staleness: track dropped after STALE_TTL_S (200 ms) without a detection.
"""

from __future__ import annotations

from typing import Any

from apex_autopilot_optimization.perception import (
    RawDetection,
    Track,
)


class DetectionTracker:
    """Maintains per-track chains and promotes confirmed tracks to WTA."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config) if config is not None else {}
        filtering = self.config.get("filtering", {})
        self.min_detections = int(filtering.get("min_detections", 3))
        self.promotion_window_s = float(filtering.get("promotion_window_s", 0.5))
        self.max_jitter_m = float(filtering.get("max_jitter_m", 2.0))
        self.stale_ttl_s = float(filtering.get("stale_ttl_s", 0.2))
        self.ewma_alpha = float(filtering.get("ewma_alpha", 0.35))
        self.bearing_gate_deg = float(filtering.get("bearing_gate_deg", 5.0))
        self.elevation_gate_deg = float(filtering.get("elevation_gate_deg", 5.0))
        self.angular_width_gate_pct = float(filtering.get("angular_width_gate_pct", 0.30))
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> DetectionTracker:
        return cls(config)

    # ------------------------------------------------------------------ public
    def update(self, detections: list[RawDetection], now: float) -> list[Track]:
        """Associate detections to tracks (or spawn new ones), prune stale.

        Returns the list of currently confirmed tracks.
        """
        # Associate each detection to the best existing track, else spawn.
        for det in detections:
            track = self._find_associated_track(det)
            if track is None:
                track = Track(
                    track_id=self._next_id,
                    drone_id=det.drone_id,
                    camera_id=det.camera_id,
                    class_name=det.class_name,
                    alpha=self.ewma_alpha,
                )
                self._next_id += 1
                self._tracks[track.track_id] = track
            track.update(det)

        # Prune stale tracks.
        stale = [tid for tid, t in self._tracks.items() if t.is_stale(now, self.stale_ttl_s)]
        for tid in stale:
            del self._tracks[tid]

        return self.confirmed_tracks(now)

    def confirmed_tracks(self, now: float) -> list[Track]:
        """Tracks promoted to confirmed (min-detections + jitter gate met)."""
        confirmed: list[Track] = []
        for track in self._tracks.values():
            if self._should_promote(track, now):
                track.confirmed = True
                confirmed.append(track)
        return confirmed

    def all_tracks(self) -> list[Track]:
        return list(self._tracks.values())

    def clear(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    # ------------------------------------------------------------------ internals
    def _find_associated_track(self, det: RawDetection) -> Track | None:
        best: Track | None = None
        for track in self._tracks.values():
            if not track.associated_with(det, self._gate_config()):
                continue
            best = track
            break  # first match wins (per-camera chains are short)
        return best

    def _gate_config(self) -> dict[str, Any]:
        return {
            "bearing_gate_deg": self.bearing_gate_deg,
            "elevation_gate_deg": self.elevation_gate_deg,
            "angular_width_gate_pct": self.angular_width_gate_pct,
        }

    def _should_promote(self, track: Track, now: float) -> bool:
        if track.confirmed:
            return True
        if track.detection_count_in_window(now, self.promotion_window_s) < self.min_detections:
            return False
        return not track.jitter_m() > self.max_jitter_m
