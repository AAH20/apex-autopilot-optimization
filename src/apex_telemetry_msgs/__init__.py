"""Python stubs for apex_telemetry_msgs ROS2 message types.

These mirror the .msg definitions in apex_telemetry_msgs/msg/ so the
apex-autopilot-optimization messaging layer can import and type-check
them without a ROS2 installation. In a ROS2 environment, the generated
message classes shadow these stubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Header:
    """std_msgs/Header stub."""

    stamp_sec: int = 0
    stamp_nanosec: int = 0
    frame_id: str = ""


@dataclass(slots=True)
class YoloDetection:
    """Single YOLO detection (mirrors YoloDetection.msg)."""

    header: Header = field(default_factory=Header)
    drone_id: int = 0
    class_id: str = ""
    score: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0
    size_x: float = 0.0
    size_y: float = 0.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    depth_m: float = float("nan")


@dataclass(slots=True)
class YoloDetectionArray:
    """Array of detections for one vehicle (mirrors YoloDetectionArray.msg)."""

    detections: list[YoloDetection] = field(default_factory=list)


@dataclass(slots=True)
class VehicleTelemetry:
    """Aggregated upstream telemetry for one vehicle (mirrors VehicleTelemetry.msg)."""

    header: Header = field(default_factory=Header)
    drone_id: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    pose_frame: int = 1
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    velocity_frame: int = 1
    battery_voltage: float = 0.0
    battery_current: float = 0.0
    battery_remaining: float = 0.0
    battery_charge_state: int = 0
    lat: float = 0.0
    lon: float = 0.0
    alt_amsl: float = 0.0
    alt_ellipsoid: float = 0.0
    gps_fix_type: int = 0
    nsat: int = 0
    eph: float = 0.0
    epv: float = 0.0
    ground_speed: float = 0.0
    nav_state: int = 0
    arming_state: int = 0
    vehicle_type: int = 0
    pre_flight_checks_pass: bool = False
    is_vtol: bool = False
    in_transition_mode: bool = False
    timestamp_us: int = 0
    source: str = ""
