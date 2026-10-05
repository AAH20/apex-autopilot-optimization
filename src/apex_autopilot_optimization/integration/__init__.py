"""External system integration package for vehicle communication.

Provides protocol-specific bridges for connecting to autonomous vehicles
via MAVLink, ROS2, and DDS, plus a human-in-the-loop adapter for
approval-gated control.
"""

from apex_autopilot_optimization.integration.dds import DDSBridge
from apex_autopilot_optimization.integration.hitl import HITLAdapter
from apex_autopilot_optimization.integration.mavlink import MAVLinkBridge
from apex_autopilot_optimization.integration.ros2 import ROS2Bridge
from apex_autopilot_optimization.integration.vehicle import VehicleInterface

__all__ = [
    "VehicleInterface",
    "MAVLinkBridge",
    "ROS2Bridge",
    "DDSBridge",
    "HITLAdapter",
]
