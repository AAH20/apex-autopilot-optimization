"""Unit tests for the external system integration package.

Covers VehicleInterface ABC, MAVLinkBridge, ROS2Bridge, DDSBridge, and
HITLAdapter. All tests use simulation mode to avoid requiring physical
vehicles or external middleware.
"""

import time

import pytest

from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
    Velocity3D,
)
from apex_autopilot_optimization.hitl.config import HITLConfig
from apex_autopilot_optimization.hitl.status import ApprovalStatus
from apex_autopilot_optimization.integration import (
    DDSBridge,
    HITLAdapter,
    MAVLinkBridge,
    ROS2Bridge,
    VehicleInterface,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_state(**overrides) -> StateVector:
    """Create a StateVector with optional overrides."""
    defaults = {
        "pose": Pose3D(x=1.0, y=2.0, z=3.0, roll=0.1, pitch=0.2, yaw=0.3),
        "velocity": Velocity3D(vx=4.0, vy=5.0, vz=6.0),
        "timestamp": time.time(),
    }
    defaults.update(overrides)
    return StateVector(**defaults)


def make_control(**overrides) -> ControlInput:
    """Create a ControlInput with optional overrides."""
    defaults = {
        "throttle": 0.5,
        "roll_rate": 0.1,
        "pitch_rate": 0.2,
        "yaw_rate": 0.3,
        "timestamp": time.time(),
    }
    defaults.update(overrides)
    return ControlInput(**defaults)


# ---------------------------------------------------------------------------
# VehicleInterface ABC
# ---------------------------------------------------------------------------


class TestVehicleInterface:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            VehicleInterface()  # type: ignore[abstract]

    def test_is_abstract_base_class(self):
        assert hasattr(VehicleInterface, "__abstractmethods__")
        assert len(VehicleInterface.__abstractmethods__) > 0

    def test_all_bridges_inherit_from_abc(self):
        assert issubclass(MAVLinkBridge, VehicleInterface)
        assert issubclass(ROS2Bridge, VehicleInterface)
        assert issubclass(DDSBridge, VehicleInterface)
        assert issubclass(HITLAdapter, MAVLinkBridge)


# ---------------------------------------------------------------------------
# MAVLinkBridge
# ---------------------------------------------------------------------------


class TestMAVLinkBridge:
    def test_init_defaults(self):
        bridge = MAVLinkBridge()
        assert bridge.connection_string == ""
        assert bridge.simulation_mode is True
        assert bridge.system_id == 1
        assert bridge.component_id == 1
        assert bridge.is_connected() is False

    def test_connect_simulation(self):
        bridge = MAVLinkBridge(simulation=True)
        result = bridge.connect("udp:127.0.0.1:14550")
        assert result is True
        assert bridge.is_connected() is True

    def test_connect_invalid_string_raises(self):
        bridge = MAVLinkBridge(simulation=True)
        with pytest.raises(ConnectionError):
            bridge.connect("invalid://bad")

    def test_disconnect(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        result = bridge.disconnect()
        assert result is True
        assert bridge.is_connected() is False

    def test_get_state_simulation(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        state = bridge.get_state()
        assert isinstance(state, StateVector)
        assert state.pose.x == 0.0
        assert state.pose.y == 0.0
        assert state.pose.z == 0.0

    def test_get_state_not_connected_raises(self):
        bridge = MAVLinkBridge(simulation=True)
        with pytest.raises(RuntimeError):
            bridge.get_state()

    def test_send_control_simulation(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        control = make_control(throttle=0.7)
        result = bridge.send_control(control)
        assert result is True

    def test_send_control_updates_state(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        initial_state = bridge.get_state()
        bridge.send_control(make_control(throttle=1.0))
        new_state = bridge.get_state()
        assert new_state.pose.x > initial_state.pose.x

    def test_arm_simulation(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        result = bridge.arm()
        assert result is True

    def test_set_mode_simulation(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        result = bridge.set_mode("GUIDED")
        assert result is True

    def test_set_mode_invalid_raises(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        with pytest.raises(ValueError):
            bridge.set_mode("INVALID_MODE_XYZ")

    def test_get_telemetry_simulation(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        telemetry = bridge.get_telemetry()
        assert isinstance(telemetry, dict)
        assert "battery_voltage" in telemetry
        assert "battery_remaining" in telemetry
        assert "gps_satellites" in telemetry

    def test_get_telemetry_not_connected_raises(self):
        bridge = MAVLinkBridge(simulation=True)
        with pytest.raises(RuntimeError):
            bridge.get_telemetry()

    def test_disconnect_resets_state(self):
        bridge = MAVLinkBridge(simulation=True)
        bridge.connect("udp:127.0.0.1:14550")
        bridge.arm()
        bridge.disconnect()
        assert bridge.is_connected() is False


# ---------------------------------------------------------------------------
# ROS2Bridge
# ---------------------------------------------------------------------------


class TestROS2Bridge:
    def test_init_defaults(self):
        bridge = ROS2Bridge()
        assert bridge.namespace == "/vehicle"
        assert bridge.node_name == "apex_bridge"
        assert bridge.simulation_mode is True
        assert bridge.is_connected() is False

    def test_connect_simulation(self):
        bridge = ROS2Bridge(simulation=True)
        result = bridge.connect("ros2://vehicle/quad_01")
        assert result is True
        assert bridge.is_connected() is True

    def test_connect_invalid_string_raises(self):
        bridge = ROS2Bridge(simulation=True)
        with pytest.raises(ConnectionError):
            bridge.connect("invalid://bad")

    def test_disconnect(self):
        bridge = ROS2Bridge(simulation=True)
        bridge.connect("ros2://vehicle/quad_01")
        result = bridge.disconnect()
        assert result is True
        assert bridge.is_connected() is False

    def test_get_state_simulation(self):
        bridge = ROS2Bridge(simulation=True)
        bridge.connect("ros2://vehicle/quad_01")
        state = bridge.get_state()
        assert isinstance(state, StateVector)

    def test_get_state_not_connected_raises(self):
        bridge = ROS2Bridge(simulation=True)
        with pytest.raises(RuntimeError):
            bridge.get_state()

    def test_send_control_simulation(self):
        bridge = ROS2Bridge(simulation=True)
        bridge.connect("ros2://vehicle/quad_01")
        control = make_control(throttle=0.5)
        result = bridge.send_control(control)
        assert result is True

    def test_arm_simulation(self):
        bridge = ROS2Bridge(simulation=True)
        bridge.connect("ros2://vehicle/quad_01")
        result = bridge.arm()
        assert result is True

    def test_set_mode_simulation(self):
        bridge = ROS2Bridge(simulation=True)
        bridge.connect("ros2://vehicle/quad_01")
        result = bridge.set_mode("auto")
        assert result is True

    def test_set_mode_empty_raises(self):
        bridge = ROS2Bridge(simulation=True)
        bridge.connect("ros2://vehicle/quad_01")
        with pytest.raises(ValueError):
            bridge.set_mode("")

    def test_get_telemetry_simulation(self):
        bridge = ROS2Bridge(simulation=True)
        bridge.connect("ros2://vehicle/quad_01")
        telemetry = bridge.get_telemetry()
        assert isinstance(telemetry, dict)
        assert "battery_voltage" in telemetry
        assert "gps_latitude" in telemetry

    def test_get_telemetry_not_connected_raises(self):
        bridge = ROS2Bridge(simulation=True)
        with pytest.raises(RuntimeError):
            bridge.get_telemetry()


# ---------------------------------------------------------------------------
# DDSBridge
# ---------------------------------------------------------------------------


class TestDDSBridge:
    def test_init_defaults(self):
        bridge = DDSBridge()
        assert bridge.domain_id == 0
        assert bridge.participant_name == "apex_bridge"
        assert bridge.simulation_mode is True
        assert bridge.is_connected() is False

    def test_connect_simulation(self):
        bridge = DDSBridge(simulation=True)
        result = bridge.connect("dds://0/vehicle_01")
        assert result is True
        assert bridge.is_connected() is True

    def test_connect_invalid_string_raises(self):
        bridge = DDSBridge(simulation=True)
        with pytest.raises(ConnectionError):
            bridge.connect("invalid://bad")

    def test_connect_invalid_domain_id_raises(self):
        bridge = DDSBridge(simulation=True)
        with pytest.raises(ConnectionError):
            bridge.connect("dds://not_a_number/vehicle")

    def test_disconnect(self):
        bridge = DDSBridge(simulation=True)
        bridge.connect("dds://0/vehicle_01")
        result = bridge.disconnect()
        assert result is True
        assert bridge.is_connected() is False

    def test_get_state_simulation(self):
        bridge = DDSBridge(simulation=True)
        bridge.connect("dds://0/vehicle_01")
        state = bridge.get_state()
        assert isinstance(state, StateVector)

    def test_get_state_not_connected_raises(self):
        bridge = DDSBridge(simulation=True)
        with pytest.raises(RuntimeError):
            bridge.get_state()

    def test_send_control_simulation(self):
        bridge = DDSBridge(simulation=True)
        bridge.connect("dds://0/vehicle_01")
        control = make_control(throttle=0.5)
        result = bridge.send_control(control)
        assert result is True

    def test_arm_simulation(self):
        bridge = DDSBridge(simulation=True)
        bridge.connect("dds://0/vehicle_01")
        result = bridge.arm()
        assert result is True

    def test_set_mode_simulation(self):
        bridge = DDSBridge(simulation=True)
        bridge.connect("dds://0/vehicle_01")
        result = bridge.set_mode("guided")
        assert result is True

    def test_set_mode_empty_raises(self):
        bridge = DDSBridge(simulation=True)
        bridge.connect("dds://0/vehicle_01")
        with pytest.raises(ValueError):
            bridge.set_mode("")

    def test_get_telemetry_simulation(self):
        bridge = DDSBridge(simulation=True)
        bridge.connect("dds://0/vehicle_01")
        telemetry = bridge.get_telemetry()
        assert isinstance(telemetry, dict)
        assert "battery_voltage" in telemetry
        assert "cpu_usage" in telemetry

    def test_get_telemetry_not_connected_raises(self):
        bridge = DDSBridge(simulation=True)
        with pytest.raises(RuntimeError):
            bridge.get_telemetry()


# ---------------------------------------------------------------------------
# HITLAdapter
# ---------------------------------------------------------------------------


class TestHITLAdapter:
    def test_init_defaults(self):
        adapter = HITLAdapter(simulation=True)
        assert adapter.simulation_mode is True
        assert adapter.is_connected() is False
        assert adapter.workflow is not None
        assert adapter.hitl_config is not None

    def test_inherits_mavlink_bridge(self):
        adapter = HITLAdapter(simulation=True)
        assert isinstance(adapter, MAVLinkBridge)

    def test_connect_simulation(self):
        adapter = HITLAdapter(simulation=True)
        result = adapter.connect("udp:127.0.0.1:14550")
        assert result is True
        assert adapter.is_connected() is True

    def test_arm_requires_approval_when_enabled(self):
        config = HITLConfig(enabled=True)
        adapter = HITLAdapter(simulation=True, hitl_config=config)
        adapter.connect("udp:127.0.0.1:14550")
        result = adapter.arm()
        assert result is False  # Pending approval
        pending = adapter.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].action == "arm"

    def test_arm_auto_approves_when_disabled(self):
        config = HITLConfig(enabled=False)
        adapter = HITLAdapter(simulation=True, hitl_config=config)
        adapter.connect("udp:127.0.0.1:14550")
        result = adapter.arm()
        assert result is True

    def test_approve_action_executes(self):
        config = HITLConfig(enabled=True)
        adapter = HITLAdapter(simulation=True, hitl_config=config)
        adapter.connect("udp:127.0.0.1:14550")
        adapter.arm()
        pending = adapter.get_pending_approvals()
        request_id = pending[0].id
        result = adapter.approve_action(request_id, "operator-1")
        assert result is True
        status = adapter.get_approval_status(request_id)
        assert status is ApprovalStatus.APPROVED

    def test_reject_action(self):
        config = HITLConfig(enabled=True)
        adapter = HITLAdapter(simulation=True, hitl_config=config)
        adapter.connect("udp:127.0.0.1:14550")
        adapter.arm()
        pending = adapter.get_pending_approvals()
        request_id = pending[0].id
        result = adapter.reject_action(request_id, "operator-1", "unsafe conditions")
        assert result is True
        status = adapter.get_approval_status(request_id)
        assert status is ApprovalStatus.REJECTED

    def test_set_mode_requires_approval(self):
        config = HITLConfig(enabled=True)
        adapter = HITLAdapter(simulation=True, hitl_config=config)
        adapter.connect("udp:127.0.0.1:14550")
        result = adapter.set_mode("GUIDED")
        assert result is False  # Pending approval
        pending = adapter.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].action == "set_mode"

    def test_low_risk_control_passes_through(self):
        config = HITLConfig(enabled=True, auto_approve_low_risk=True)
        adapter = HITLAdapter(simulation=True, hitl_config=config)
        adapter.connect("udp:127.0.0.1:14550")
        control = make_control(throttle=0.3, yaw_rate=0.1)
        result = adapter.send_control(control)
        assert result is True

    def test_high_risk_control_requires_approval(self):
        config = HITLConfig(enabled=True)
        adapter = HITLAdapter(simulation=True, hitl_config=config)
        adapter.connect("udp:127.0.0.1:14550")
        control = make_control(throttle=0.9, yaw_rate=0.1)
        result = adapter.send_control(control)
        assert result is False  # Pending approval
        pending = adapter.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].action == "send_control"

    def test_get_pending_approvals_empty(self):
        adapter = HITLAdapter(simulation=True)
        adapter.connect("udp:127.0.0.1:14550")
        assert adapter.get_pending_approvals() == []

    def test_approve_unknown_request_raises(self):
        adapter = HITLAdapter(simulation=True)
        adapter.connect("udp:127.0.0.1:14550")
        result = adapter.approve_action("nonexistent", "op")
        assert result is False

    def test_disconnect(self):
        adapter = HITLAdapter(simulation=True)
        adapter.connect("udp:127.0.0.1:14550")
        result = adapter.disconnect()
        assert result is True
        assert adapter.is_connected() is False


# ---------------------------------------------------------------------------
# Cross-bridge consistency
# ---------------------------------------------------------------------------


class TestCrossBridgeConsistency:
    def test_all_bridges_support_same_interface(self):
        bridges = [
            MAVLinkBridge(simulation=True),
            ROS2Bridge(simulation=True),
            DDSBridge(simulation=True),
        ]
        for bridge in bridges:
            assert isinstance(bridge, VehicleInterface)
            assert hasattr(bridge, "connect")
            assert hasattr(bridge, "disconnect")
            assert hasattr(bridge, "get_state")
            assert hasattr(bridge, "send_control")
            assert hasattr(bridge, "arm")
            assert hasattr(bridge, "set_mode")
            assert hasattr(bridge, "get_telemetry")
            assert hasattr(bridge, "is_connected")

    def test_all_bridges_reject_invalid_connection_strings(self):
        bridges = [
            MAVLinkBridge(simulation=True),
            ROS2Bridge(simulation=True),
            DDSBridge(simulation=True),
        ]
        for bridge in bridges:
            with pytest.raises(ConnectionError):
                bridge.connect("bad://invalid")

    def test_all_bridges_raise_when_not_connected(self):
        bridges = [
            MAVLinkBridge(simulation=True),
            ROS2Bridge(simulation=True),
            DDSBridge(simulation=True),
        ]
        for bridge in bridges:
            with pytest.raises(RuntimeError):
                bridge.get_state()
            with pytest.raises(RuntimeError):
                bridge.get_telemetry()
