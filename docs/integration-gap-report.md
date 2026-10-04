# External System Integration Gap Report

**Project:** apex-autopilot-optimization  
**Date:** 2026-10-04  
**Scope:** ROS2 bridge, MAVLink bridge, DDS integration, HIL support  
**Current State:** 20 modules implemented (planning, control, estimation, swarm, safety, optimization). Zero external system integrations.

---

## 1. Executive Summary

The project has a complete algorithmic core but **no interface layer** to communicate with any external system. The architecture diagrams in `unified_architecture.md` and `README.md` reference PX4 Adapter, ArduPilot Adapter, ROS2 Bridge, and DDS Bridge — but none are implemented. The project currently operates as a pure computational library with no I/O boundary to the outside world.

**Critical finding:** The `ControlInput` and `StateVector` types are the *only* data that would cross a bridge boundary, yet there is no abstraction for how these types are serialized, transported, or synchronized with an external autopilot.

---

## 2. Gap Analysis

### 2.1 Missing External System Integrations

| # | Missing Integration | Priority | Impact | Current Status |
|---|---------------------|----------|--------|----------------|
| 1 | **MAVLink Bridge** | P0 | Cannot communicate with any real autopilot (PX4, ArduPilot) | Not started |
| 2 | **ROS2 Bridge** | P0 | Cannot participate in ROS2 robotics ecosystem | Not started |
| 3 | **DDS Integration** | P1 | Cannot interoperate with DDS-based systems | Not started |
| 4 | **PX4 uORB Bridge** | P1 | Cannot send/receive PX4 microRTPS messages | Not started |
| 5 | **ArduPilot MAVLink Bridge** | P1 | Cannot communicate with ArduPilot vehicles | Not started |
| 6 | **SITL Simulator Interface** | P1 | Cannot test in simulation before hardware | Not started |
| 7 | **HITL Simulator Interface** | P2 | Cannot test with real FC + simulated physics | Not started |
| 8 | **Digital Twin Interface** | P2 | No real-time sync with virtual vehicle | Not started |
| 9 | **Ground Station Interface** | P2 | No QGroundControl / Mission Planner integration | Not started |
| 10 | **Sensor Data Ingestion** | P0 | No way to feed real sensor data into EKF | Not started |

### 2.2 Interface Boundary Analysis

The project's current data flow is entirely internal:

```
[Internal] PlanningProblem → Planner → Waypoints → Optimizer → Trajectory → CBF → MPC → ControlInput
                                                                                              ↓
                                                                                    (dead end — no output)
```

**What exists:**
- `StateVector` (12-state: position, orientation, velocity) — the natural telemetry unit
- `ControlInput` (throttle, roll_rate, pitch_rate, yaw_rate) — the natural command unit
- `Waypoint` (pose, speed, arrival_time, tolerance) — the natural mission unit
- `Trajectory` (states[], controls[], timestamps) — the natural path-following unit

**What's missing:**
- No serialization layer (how `StateVector` → bytes on the wire)
- No transport abstraction (UDP, serial, DDS, shared memory)
- No protocol encoding (MAVLink framing, ROS2 message types, DDS CDR)
- No time synchronization (how timestamps map between host and autopilot)
- No command lifecycle (how a `ControlInput` becomes a tracked command with ack/failure)

---

## 3. ROS2 Bridge Implementation

### 3.1 Architecture Pattern

The ROS2 bridge should follow the **Adapter Pattern** with a clean separation between the project's domain types and ROS2 message types:

```
┌─────────────────────────────────────────────────────────┐
│                  apex-autopilot-optimization              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ Planner │→│Optimizer│→│  CBF    │→│   MPC   │    │
│  └─────────┘  └─────────┘  └─────────┘  └────┬────┘    │
│                                               │          │
│  ┌────────────────────────────────────────────▼────────┐ │
│  │              VehicleInterface (ABC)                  │ │
│  │  - get_state() → StateVector                        │ │
│  │  - send_control(ControlInput) → CommandAck          │ │
│  │  - send_waypoint(Waypoint) → CommandAck             │ │
│  │  - get_trajectory() → Trajectory                    │ │
│  └─────────────────────┬───────────────────────────────┘ │
└────────────────────────┼──────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
   ┌──────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
   │ ROS2Adapter │ │MAVLink   │ │  DDS       │
   │ (rclpy)     │ │Adapter   │ │  Adapter   │
   │             │ │(pymavlink)│ │(pycyclonedds)│
   └─────────────┘ └──────────┘ └────────────┘
```

### 3.2 Proposed Module Structure

```
src/apex_autopilot_optimization/
├── interfaces/
│   ├── __init__.py
│   ├── base.py              # VehicleInterface ABC
│   ├── command.py           # CommandAck, CommandStatus enums
│   └── transport.py         # Transport ABC (UDP, Serial, DDS, SharedMemory)
├── bridges/
│   ├── __init__.py
│   ├── ros2/
│   │   ├── __init__.py
│   │   ├── adapter.py       # ROS2Adapter(VehicleInterface)
│   │   ├── messages.py      # ROS2 ↔ domain type converters
│   │   ├── node.py          # rclpy node wrapper
│   │   └── config.py        # ROS2 QoS, topic names, RMW selection
│   ├── mavlink/
│   │   ├── __init__.py
│   │   ├── adapter.py       # MAVLinkAdapter(VehicleInterface)
│   │   ├── protocol.py      # MAVLink message encoding/decoding
│   │   ├── connection.py    # Serial/UDP connection management
│   │   └── config.py        # MAVLink dialect, stream rates
│   └── dds/
│       ├── __init__.py
│       ├── adapter.py       # DDSAdapter(VehicleInterface)
│       ├── types.py         # DDS topic type definitions
│       ├── participant.py   # DDS domain participant management
│       └── config.py        # DDS QoS, domain ID, RMW selection
```

### 3.3 VehicleInterface ABC

```python
# interfaces/base.py
from abc import ABC, abstractmethod
from enum import Enum, auto
from core.types import StateVector, ControlInput, Waypoint, Trajectory

class CommandStatus(Enum):
    ACCEPTED = auto()
    REJECTED = auto()
    TIMEOUT = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()

@dataclass(frozen=True)
class CommandAck:
    command_id: str
    status: CommandStatus
    timestamp: float
    message: str = ""

class VehicleInterface(ABC):
    """Abstract boundary between apex-autopilot-optimization and any external system."""

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_state(self) -> StateVector:
        """Get current vehicle state from external system."""
        ...

    @abstractmethod
    def send_control(self, control: ControlInput) -> CommandAck:
        """Send control input to external system."""
        ...

    @abstractmethod
    def send_waypoint(self, waypoint: Waypoint) -> CommandAck:
        """Send waypoint to external system."""
        ...

    @abstractmethod
    def arm(self) -> CommandAck: ...

    @abstractmethod
    def set_mode(self, mode: str) -> CommandAck: ...

    @abstractmethod
    def is_connected(self) -> bool: ...
```

### 3.4 ROS2-Specific Implementation Notes

Based on research of PX4-ROS2 integration patterns:

1. **Message mapping:** ROS2 uses `px4_msgs` (matching PX4 firmware version). The bridge must convert between `StateVector` and `VehicleOdometry`, and between `ControlInput` and `TrajectorySetpoint` + `OffboardControlMode`.

2. **Offboard control heartbeat:** PX4 requires `OffboardControlMode` streamed at >2 Hz before and during offboard mode. The ROS2 adapter must implement this heartbeat.

3. **Topic naming convention:**
   - Subscribe: `/fmu/out/vehicle_odometry`, `/fmu/out/vehicle_status`
   - Publish: `/fmu/in/offboard_control_mode`, `/fmu/in/trajectory_setpoint`, `/fmu/in/vehicle_command`

4. **QoS configuration:**
   - Sensor data: `BEST_EFFORT` + `VOLATILE` (high-rate, drop OK)
   - Commands: `RELIABLE` + `VOLATILE` (must arrive, no late-joiner)
   - Mode changes: `RELIABLE` + `TRANSIENT_LOCAL` (late-joiners need last state)

5. **RMW selection:** Support `rmw_fastrtps_cpp` (default), `rmw_cyclonedds_cpp` (embedded), `rmw_zenoh_cpp` (fleet/WAN).

6. **Version matching:** `px4_msgs` must match PX4 firmware version — the #1 cause of silent serialization failures.

### 3.5 MAVLink Adapter Design

```python
# bridges/mavlink/adapter.py
class MAVLinkAdapter(VehicleInterface):
    """MAVLink-based vehicle interface for PX4 and ArduPilot."""

    def __init__(self, connection_string: str, baud: int = 921600,
                 dialect: str = "common", target_system: int = 1):
        self._conn = mavutil.mavlink_connection(connection_string, baud=baud,
                                                dialect=dialect)
        self._target_system = target_system
        self._command_seq = 0

    def get_state(self) -> StateVector:
        msg = self._conn.recv_match(type='ATTITUDE', blocking=True)
        pos_msg = self._conn.recv_match(type='GLOBAL_POSITION_INT', blocking=True)
        return self._convert_to_state_vector(msg, pos_msg)

    def send_control(self, control: ControlInput) -> CommandAck:
        self._conn.mav.set_attitude_target_send(
            int(time.time() * 1000),
            self._target_system, 1,
            0b00000111,  # type mask
            self._quaternion_from_rates(control),
            control.roll_rate, control.pitch_rate, control.yaw_rate,
            control.throttle
        )
        return CommandAck(str(self._command_seq), CommandStatus.ACCEPTED, time.time())

    def send_waypoint(self, waypoint: Waypoint) -> CommandAck:
        self._conn.mav.mission_item_send(
            self._target_system, 1, self._command_seq,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            0, 1, 0, waypoint.tolerance_m, 0, 0,
            waypoint.pose.x, waypoint.pose.y, waypoint.pose.z
        )
        return CommandAck(str(self._command_seq), CommandStatus.ACCEPTED, time.time())
```

### 3.6 DDS Adapter Design

The DDS adapter provides direct DDS communication without ROS2, useful for:
- Embedded systems where ROS2 is too heavy
- Industrial DDS deployments (RTI Connext)
- Direct PX4 microRTPS communication

```python
# bridges/dds/adapter.py
class DDSAdapter(VehicleInterface):
    """Direct DDS vehicle interface using CycloneDDS or FastDDS."""

    def __init__(self, domain_id: int = 0, qos_profile: str = "default"):
        self._domain_id = domain_id
        self._participant = None
        self._readers: dict[str, Any] = {}
        self._writers: dict[str, Any] = {}

    def connect(self) -> bool:
        # Create DDS participant, publishers, subscribers
        # Map domain types to DDS topic types
        ...

    def get_state(self) -> StateVector:
        # Read from VehicleOdometry DDS topic
        sample = self._readers["vehicle_odometry"].read_next_sample()
        return self._dds_to_state_vector(sample)
```

---

## 4. Hardware-in-the-Loop (HITL) Patterns

### 4.1 HITL Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    HITL Simulation Stack                       │
│                                                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Gazebo /   │    │   PX4 HITL   │    │   Real FC    │   │
│  │   jMAVSim    │←──→│   Firmware   │←──→│   Hardware   │   │
│  │  (physics)   │    │  (on real HW)│    │  (Pixhawk)   │   │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘   │
│         │                   │                                  │
│         │            MAVLink over USB/UART                    │
│         │                   │                                  │
│  ┌──────▼───────────────────▼──────────────────────────────┐  │
│  │              MAVLink Bridge (this project)               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │  │
│  │  │  MAVLink     │  │  State      │  │  Control    │     │  │
│  │  │  Adapter     │→ │  Machine    │→ │  Pipeline   │     │  │
│  │  │  (USB/UART)  │  │  (EKF)      │  │  (MPC+CBF)  │     │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 HITL Configuration Matrix

| Mode | Physics Engine | Flight Controller | Communication | Use Case |
|------|---------------|-------------------|---------------|----------|
| **SITL** | Gazebo/jMAVSim | Simulated PX4 | UDP loopback | Algorithm development, CI/CD |
| **HITL** | Gazebo/jMAVSim | Real Pixhawk | USB/UART MAVLink | Hardware validation, driver testing |
| **SIH** | Onboard | Real PX4 (SITL mode) | Internal | Lightweight hardware testing |
| **Real Flight** | Reality | Real Pixhawk | Radio/telemetry | Final validation |

### 4.3 HITL Implementation Pattern

```python
# bridges/hitl/simulator.py
class HITLSimulator:
    """Hardware-in-the-loop simulator interface."""

    def __init__(self, sim_type: str = "gazebo", hitl_mode: bool = True):
        self._sim_type = sim_type
        self._hitl_mode = hitl_mode
        self._vehicle_interface: VehicleInterface | None = None

    def start(self) -> bool:
        """Start simulator and connect vehicle interface."""
        if self._hitl_mode:
            # HITL: Connect to real flight controller via MAVLink
            self._vehicle_interface = MAVLinkAdapter(
                connection_string="/dev/ttyACM0:921600",
                dialect="common"
            )
        else:
            # SITL: Connect to simulated PX4 via UDP
            self._vehicle_interface = MAVLinkAdapter(
                connection_string="udp:127.0.0.1:14550",
                dialect="common"
            )
        return self._vehicle_interface.connect()

    def run_control_loop(self, planner, optimizer, controller, cbf):
        """Run the full planning-control loop against the simulator."""
        while True:
            # 1. Get state from vehicle
            state = self._vehicle_interface.get_state()

            # 2. Plan path
            problem = PlanningProblem(
                start=state,
                goal=self._current_goal,
                vehicle_type=VehicleType.UAV_MULTIROTOR,
                obstacles=self._obstacles
            )
            result = planner.plan(problem)

            # 3. Optimize trajectory
            trajectory = optimizer.optimize(result.waypoints)

            # 4. Compute control
            target = trajectory.get_target_at(time.time())
            control = controller.compute_control(state, target)

            # 5. Safety filter
            safe_control = cbf.filter(state, control, self._obstacles)

            # 6. Send to vehicle
            ack = self._vehicle_interface.send_control(safe_control)
            if ack.status != CommandStatus.ACCEPTED:
                self._handle_command_failure(ack)

            time.sleep(0.02)  # 50 Hz control loop
```

### 4.4 SITL vs HITL Decision Tree

```
Start
  │
  ├─ Need to test algorithms only? → SITL (Gazebo + simulated PX4)
  │
  ├─ Need to test sensor drivers? → HITL (Gazebo + real Pixhawk)
  │
  ├─ Need to test real-time performance? → HITL with RT kernel
  │
  ├─ Need to test communication? → HITL with telemetry radio
  │
  └─ Need final validation? → Real flight test
```

---

## 5. Loose Coupling Strategy

### 5.1 Design Principles

1. **Dependency Inversion:** All bridge implementations depend on `VehicleInterface` ABC, not the reverse. The core modules (planner, optimizer, controller) never import bridge code.

2. **Interface Segregation:** `VehicleInterface` is minimal — only the methods needed to read state and send commands. No bridge-specific types leak into the core.

3. **Type Isolation:** Each bridge has its own message types. Conversion happens only at the bridge boundary:
   ```
   StateVector ←→ VehicleOdometry (ROS2)
   StateVector ←→ ATTITUDE + GLOBAL_POSITION_INT (MAVLink)
   StateVector ←→ VehicleOdometry (DDS)
   ```

4. **Transport Abstraction:** The `Transport` ABC separates connection management from protocol encoding:
   ```python
   class Transport(ABC):
       @abstractmethod
       def connect(self) -> bool: ...
       @abstractmethod
       def disconnect(self) -> None: ...
       @abstractmethod
       def send(self, data: bytes) -> bool: ...
       @abstractmethod
       def receive(self) -> bytes | None: ...
   ```

5. **Configuration-Driven:** Bridge selection via configuration, not code changes:
   ```yaml
   # config.yaml
   vehicle_interface:
     type: ros2  # or mavlink, dds, sitl, hitl
     connection:
       transport: udp
       host: 127.0.0.1
       port: 14550
     qos:
       sensor_data: best_effort
       commands: reliable
   ```

### 5.2 Dependency Graph (Desired)

```
core/types.py ← interfaces/base.py ← bridges/ros2/adapter.py
                                ← bridges/mavlink/adapter.py
                                ← bridges/dds/adapter.py
                                ← bridges/hitl/simulator.py

planning/ ← core/types.py (only)
control/ ← core/types.py (only)
estimation/ ← core/types.py (only)
```

**No bridge module should ever be imported by a core module.**

### 5.3 Testing Strategy for Loose Coupling

```python
# tests/unit/test_vehicle_interface.py
class MockVehicleInterface(VehicleInterface):
    """Test double that implements VehicleInterface without any real I/O."""

    def __init__(self):
        self._state = StateVector(...)
        self._commands: list[ControlInput] = []
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def get_state(self) -> StateVector:
        return self._state

    def send_control(self, control: ControlInput) -> CommandAck:
        self._commands.append(control)
        return CommandAck("test-1", CommandStatus.ACCEPTED, time.time())

    # ... implement remaining methods

def test_mpl_with_mock_interface():
    """Test that MPC controller works with any VehicleInterface implementation."""
    mock_vehicle = MockVehicleInterface()
    controller = MPCController()

    state = mock_vehicle.get_state()
    control = controller.compute_control(state, target_state)
    ack = mock_vehicle.send_control(control)

    assert ack.status == CommandStatus.ACCEPTED
    assert len(mock_vehicle._commands) == 1
```

---

## 6. Implementation Roadmap

### Phase 1: Interface Foundation (Week 1-2)
- [ ] Create `interfaces/base.py` with `VehicleInterface` ABC
- [ ] Create `interfaces/command.py` with `CommandAck`, `CommandStatus`
- [ ] Create `interfaces/transport.py` with `Transport` ABC
- [ ] Write unit tests with `MockVehicleInterface`
- [ ] Update `pyproject.toml` with optional dependencies

### Phase 2: MAVLink Bridge (Week 3-4)
- [ ] Implement `MAVLinkAdapter` with `pymavlink`
- [ ] Implement serial and UDP connection management
- [ ] Implement state parsing (ATTITUDE, GLOBAL_POSITION_INT)
- [ ] Implement control sending (SET_ATTITUDE_TARGET)
- [ ] Implement waypoint upload (MISSION_ITEM)
- [ ] Write integration tests with MAVLink simulator

### Phase 3: ROS2 Bridge (Week 5-6)
- [ ] Implement `ROS2Adapter` with `rclpy`
- [ ] Implement ROS2 ↔ domain type converters
- [ ] Implement offboard control heartbeat
- [ ] Implement QoS configuration
- [ ] Write integration tests with ROS2 daemon

### Phase 4: DDS Bridge (Week 7-8)
- [ ] Implement `DDSAdapter` with `pycyclonedds`
- [ ] Implement DDS topic type definitions
- [ ] Implement DDS participant management
- [ ] Write integration tests with DDS loopback

### Phase 5: HITL/SITL Support (Week 9-10)
- [ ] Implement `HITLSimulator` orchestrator
- [ ] Implement SITL connection (UDP to Gazebo)
- [ ] Implement HITL connection (USB to Pixhawk)
- [ ] Implement control loop runner
- [ ] Write integration tests with simulated vehicle

---

## 7. Dependencies to Add

```toml
# pyproject.toml — new optional dependencies
[project.optional-dependencies]
mavlink = [
    "pymavlink>=2.4.0,<3.0.0",
]
ros2 = [
    # Note: rclpy is typically installed via ROS2 system packages
    # These are supporting libraries only
    "pyyaml>=6.0.1,<7.0.0",
]
dds = [
    "pycyclonedds>=0.10.0,<1.0.0",
]
sim = [
    "gymnasium>=0.29.0,<1.0.0",
    "mavsim>=0.1.0",  # MAVLink simulation toolkit
]
all = [
    "pymavlink>=2.4.0,<3.0.0",
    "pycyclonedds>=0.10.0,<1.0.0",
    "gymnasium>=0.29.0,<1.0.0",
]
```

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| ROS2 version fragmentation | High | Support Humble, Jazzy, Kilted; document version matrix |
| MAVLink dialect differences | Medium | Use `common` dialect; test against PX4 and ArduPilot |
| DDS RMW incompatibility | Medium | Abstract RMW selection; test FastDDS + CycloneDDS |
| Real-time constraints in Python | High | Document RT limitations; provide C++ bridge path |
| HITL hardware variability | Medium | Support common FCs (Pixhawk 4/6, Cube); document config |
| px4_msgs version mismatch | High | Document version matching; provide conversion utilities |

---

## 9. References

1. PX4-ROS2 Bridge: https://docs.px4.io/main/en/middleware/micrortps.html
2. PX4 Offboard Control: https://docs.px4.io/main/en/ros/ros2_offboard_control.html
3. PX4 HITL Simulation: https://docs.px4.io/main/en/simulation/hitl
4. ROS2 RMW Configuration: https://docs.ros.org/en/rolling/How-To-Guides/Working-with-multiple-RMW-implementations.html
5. CycloneDDS Python: https://github.com/eclipse-cyclonedds/cyclonedds
6. pymavlink: https://github.com/ArduPilot/pymavlink
7. PX4-Avoidance: https://github.com/PX4/PX4-Avoidance
8. micro-ROS: https://micro.ros.org/
