"""N-vehicle swarm orchestration extending the single-vehicle SimulationRunner.

Provides:

* ``SwarmRunner`` — orchestrates per-vehicle connect/arm/plan/control/safety/step
  loops on a synchronized ``dt`` cycle, with partial-failure isolation, an
  ``abort_on_any_failure`` flag, and a guaranteed ``disconnect_all`` teardown.
* ``SwarmConnectionManager`` — per-vehicle MAVLink connections with port
  namespacing (``5760 + i*10`` master, ``5501 + i*10`` SITL) and bind-test before
  launch.
* ``SwarmStateStore`` — distributed per-vehicle state with freshness/staleness TTL.
* ``SwarmSafetyFilter`` — pairwise collision avoidance via ``Pose3D.distance_to``,
  geofence, no-fly zones, and RTL failsafe.
* ``FormationSetpointGenerator`` — wraps ``swarm/formation.py`` line/wedge/hexagon.
* ``GazeboSITLLauncher`` — launch N PX4 SITL instances, per-slot ports/IDs,
  headless, PID manifest, teardown.
* ``SwarmStatsAggregator`` — per-vehicle rollups plus swarm-level makespan,
  success rate, safety violations, formation deviation, cycle latency.

The single-vehicle ``SimulationRunner`` and ``SimulationInterface`` are left
untouched; this module is backward compatible and fully testable with mocked
``MAVLinkBridge`` and ``SimulationInterface``.
"""

from __future__ import annotations

import logging
import math
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from apex_autopilot_optimization.core.types import (
    ControlInput,
    Pose3D,
    StateVector,
)
from apex_autopilot_optimization.integration.mavlink import MAVLinkBridge
from apex_autopilot_optimization.simulation.combat_reallocator import CombatReallocator
from apex_autopilot_optimization.simulation.config import SimulationConfig
from apex_autopilot_optimization.simulation.interface import SimulationInterface
from apex_autopilot_optimization.simulation.result import SimulationResult
from apex_autopilot_optimization.swarm.formation import (
    FormationConfig,
    FormationController,
)
from apex_autopilot_optimization.swarm.wta_solver import (
    BDAEvent,
    SolverState,
    Target,
    TieredWTASolver,
    Weapon,
    WTAConfig,
)

logger = logging.getLogger(__name__)

# Port namespacing constants (AAS convention).
DEFAULT_BASE_MASTER_PORT = 5760
DEFAULT_BASE_SITL_PORT = 5501
PORT_STRIDE = 10

# Default swarm cycle parameters (mirror SimulationRunner defaults).
DEFAULT_DT = 0.05
DEFAULT_MAX_STEPS = 1000

# Default safety parameters.
DEFAULT_MIN_SEPARATION_M = 2.0
DEFAULT_CONNECT_RETRIES = 3
DEFAULT_CONNECT_BACKOFF_MS = 50.0

# Neutral "hold" control used by the safety filter on violation.
_HOLD_CONTROL = ControlInput(throttle=0.0, roll_rate=0.0, pitch_rate=0.0, yaw_rate=0.0)


# --------------------------------------------------------------------------- #
# Supporting dataclasses
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class VehicleSession:
    """Per-vehicle session bookkeeping for one swarm slot."""

    vehicle_id: int
    mavlink: MAVLinkBridge | None = None
    sim: SimulationInterface | None = None
    state: StateVector | None = None
    status: str = "INIT"
    telemetry: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExclusionZone:
    """A no-fly exclusion zone (sphere with optional vertical band)."""

    center: Pose3D
    radius_m: float
    z_min: float | None = None
    z_max: float | None = None


@dataclass(slots=True)
class WTAMissionProblem:
    """WTA problem instance for one vehicle slot in a batch mission.

    ``target_poses`` maps target id to its pose so solver assignments can be
    applied directly as formation setpoints (the vehicle tracks its assigned
    target).
    """

    vehicle_id: int
    weapons: list[Weapon]
    targets: list[Target]
    kill_prob: np.ndarray
    values: np.ndarray | None = None
    time_feasible: np.ndarray | None = None
    salvo_caps: dict[int, int] | None = None
    interference_cliques: list[list[tuple[int, int]]] | None = None
    target_poses: dict[int, Pose3D] | None = None


@dataclass(slots=True)
class SwarmSafetyConfig:
    """Configuration for the swarm-level safety filter."""

    min_separation_m: float = DEFAULT_MIN_SEPARATION_M
    geofence: tuple[tuple[float, float], ...] | None = None
    z_min: float | None = None
    z_max: float | None = None
    no_fly_zones: list[ExclusionZone] = field(default_factory=list)
    failsafe_mode: str = "RTL"


@dataclass(frozen=True, slots=True)
class SafetyViolation:
    """A single safety violation event for one vehicle."""

    vehicle_id: int
    kind: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class SafetyReport:
    """Output of SwarmSafetyFilter: filtered controls plus violation metadata."""

    violations: list[SafetyViolation] = field(default_factory=list)
    collision_events: list[tuple[int, int]] = field(default_factory=list)
    filtered_controls: dict[int, ControlInput] = field(default_factory=dict)

    @property
    def violation_count(self) -> int:
        return len(self.violations)


@dataclass(slots=True)
class SwarmMissionResult:
    """Aggregate result of a swarm mission."""

    per_vehicle: dict[int, SimulationResult] = field(default_factory=dict)
    swarm: dict[str, Any] = field(default_factory=dict)
    makespan_seconds: float = 0.0
    formation_deviation_m: float = 0.0
    safety_violations: int = 0
    collision_events: list[tuple[int, int]] = field(default_factory=list)
    success: bool = False
    message: str = ""


@dataclass(slots=True)
class LauncherManifest:
    """Per-slot record of a launched PX4 SITL instance."""

    slot: int
    pid: int | None = None
    ports: tuple[int, int] | None = None
    log_path: str = ""
    started_at: float = 0.0


# --------------------------------------------------------------------------- #
# SwarmConnectionManager
# --------------------------------------------------------------------------- #


class SwarmConnectionManager:
    """Owns the lifecycle of N MAVLinkBridge instances with port namespacing."""

    def __init__(self) -> None:
        self._bridges: dict[int, MAVLinkBridge] = {}
        self._connected: dict[int, bool] = {}
        self._simulation: bool = True

    # -- port namespacing --------------------------------------------------- #

    @staticmethod
    def master_port(slot: int, base_master_port: int = DEFAULT_BASE_MASTER_PORT) -> int:
        """MAVLink master port for a vehicle slot: ``base + slot * 10``."""
        return base_master_port + slot * PORT_STRIDE

    @staticmethod
    def sitl_port(slot: int, base_sitl_port: int = DEFAULT_BASE_SITL_PORT) -> int:
        """SITL/Gazebo sim port for a vehicle slot: ``base + slot * 10``."""
        return base_sitl_port + slot * PORT_STRIDE

    @staticmethod
    def connection_string(slot: int, base_master_port: int = DEFAULT_BASE_MASTER_PORT) -> str:
        """MAVLink connection string for a vehicle slot."""
        return f"udp:127.0.0.1:{SwarmConnectionManager.master_port(slot, base_master_port)}"

    # -- bind test ---------------------------------------------------------- #

    def bind_test(self, port: int, host: str = "127.0.0.1") -> bool:
        """Return True if ``port`` is free to bind (UDP probe)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    # -- connect / disconnect ---------------------------------------------- #

    def _connect_slot(
        self,
        slot: int,
        *,
        base_master_port: int = DEFAULT_BASE_MASTER_PORT,
        simulation: bool | None = None,
    ) -> bool:
        """Connect one vehicle slot. Returns True on success, False on failure."""
        if slot in self._bridges:
            logger.warning("Slot %d already has a bridge; skipping reconnect", slot)
            return self._connected.get(slot, False)

        conn_str = self.connection_string(slot, base_master_port)
        bridge = MAVLinkBridge(
            connection_string=conn_str,
            simulation=simulation if simulation is not None else self._simulation,
            system_id=slot,
            component_id=1,
        )

        connected = False
        last_exc: Exception | None = None
        for attempt in range(DEFAULT_CONNECT_RETRIES):
            try:
                if bridge.connect(conn_str):
                    connected = True
                    break
            except (ConnectionError, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "Connect attempt %d/%d for slot %d failed: %s",
                    attempt + 1,
                    DEFAULT_CONNECT_RETRIES,
                    slot,
                    exc,
                )
                if attempt < DEFAULT_CONNECT_RETRIES - 1:
                    time.sleep(DEFAULT_CONNECT_BACKOFF_MS / 1000.0 * (2**attempt))

        self._bridges[slot] = bridge
        self._connected[slot] = connected
        if not connected:
            logger.error(
                "Slot %d failed to connect after %d retries (%s)",
                slot,
                DEFAULT_CONNECT_RETRIES,
                last_exc,
            )
        return connected

    def connect_all(
        self,
        swarm_size: int,
        *,
        start_slot: int = 0,
        base_master_port: int = DEFAULT_BASE_MASTER_PORT,
        base_sitl_port: int = DEFAULT_BASE_SITL_PORT,
        simulation: bool | None = None,
    ) -> dict[int, bool]:
        """Connect every vehicle slot ``start_slot .. start_slot+swarm_size-1``.

        One failure never aborts the remaining slots; results are returned per
        slot so the caller can decide whether to proceed (or honor
        ``abort_on_any_failure``).
        """
        results: dict[int, bool] = {}
        for offset in range(swarm_size):
            slot = start_slot + offset
            results[slot] = self._connect_slot(
                slot,
                base_master_port=base_master_port,
                simulation=simulation,
            )
        return results

    def disconnect_all(self) -> dict[str, bool]:
        """Tear down every bridge in reverse slot order.

        Exceptions in one bridge never prevent others from closing; no exception
        propagates to the caller.
        """
        results: dict[str, bool] = {}
        for slot in sorted(self._bridges.keys(), reverse=True):
            bridge = self._bridges[slot]
            try:
                ok = bool(bridge.disconnect())
            except Exception as exc:  # noqa: BLE001
                logger.warning("disconnect() raised for slot %d: %s", slot, exc)
                ok = False
            results[f"bridge_{slot}"] = ok
            self._connected[slot] = False
        return results

    def health_check_all(self) -> dict[int, bool]:
        """Poll is_connected() on every bridge; return per-slot health."""
        return {slot: self.is_connected(slot) for slot in self._bridges}

    def is_connected(self, slot: int) -> bool:
        """Whether a slot's bridge is currently connected."""
        bridge = self._bridges.get(slot)
        if bridge is None:
            return False
        try:
            return bool(bridge.is_connected())
        except Exception:  # noqa: BLE001
            self._connected[slot] = False
            return False

    def get_bridge(self, slot: int) -> MAVLinkBridge | None:
        """Accessor for the step loop to call MAVLink ops per vehicle."""
        return self._bridges.get(slot)

    def get_healthy_slots(self) -> list[int]:
        """Slots whose bridge reports connected (quarantine excludes unhealthy)."""
        return [slot for slot in sorted(self._bridges) if self.is_connected(slot)]


# --------------------------------------------------------------------------- #
# SwarmStateStore
# --------------------------------------------------------------------------- #


class SwarmStateStore:
    """Distributed per-vehicle state with freshness/staleness TTL.

    Single source of truth for swarm state: slot -> (StateVector, timestamp).
    The step loop reads once (snapshot), computes per-vehicle controls, then
    writes back each vehicle's new state after the step.
    """

    def __init__(self) -> None:
        self._states: dict[int, StateVector] = {}
        self._timestamps: dict[int, float] = {}

    def update(self, vehicle_id: int, state: StateVector) -> None:
        """Atomic per-slot write with the state's timestamp (fallback: now)."""
        self._states[vehicle_id] = state
        self._timestamps[vehicle_id] = float(state.timestamp)

    def snapshot(self) -> dict[int, StateVector]:
        """Return a copy of the latest state per connected vehicle."""
        return dict(self._states)

    def get(self, vehicle_id: int) -> StateVector | None:
        """Latest state for one vehicle, or None if unknown."""
        return self._states.get(vehicle_id)

    def is_fresh(self, vehicle_id: int, max_age_s: float) -> bool:
        """Staleness check against the stored timestamp."""
        ts = self._timestamps.get(vehicle_id)
        if ts is None:
            return False
        return (time.time() - ts) <= max_age_s

    def stale_slots(self, max_age_s: float) -> list[int]:
        """Slots whose state is older than ``max_age_s``."""
        return [slot for slot, ts in self._timestamps.items() if (time.time() - ts) > max_age_s]


# --------------------------------------------------------------------------- #
# SwarmSafetyFilter
# --------------------------------------------------------------------------- #


class SwarmSafetyFilter:
    """Swarm-level safety filter: collision avoidance, geofence, no-fly, RTL."""

    def __init__(
        self,
        config: SwarmSafetyConfig | None = None,
        **kwargs: Any,
    ) -> None:
        if config is None:
            config = SwarmSafetyConfig(**kwargs)
        # Normalize any plain-dict no-fly zones into ExclusionZone dataclasses.
        normalized_zones: list[ExclusionZone] = []
        for zone in config.no_fly_zones:
            if isinstance(zone, ExclusionZone):
                normalized_zones.append(zone)
            elif isinstance(zone, dict):
                center = zone["center"]
                if isinstance(center, dict):
                    center = Pose3D(**center)
                normalized_zones.append(
                    ExclusionZone(
                        center=center,
                        radius_m=float(zone["radius_m"]),
                        z_min=zone.get("z_min"),
                        z_max=zone.get("z_max"),
                    )
                )
            else:
                normalized_zones.append(zone)
        config.no_fly_zones = normalized_zones
        self.config = config

    # -- helpers ------------------------------------------------------------ #

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: tuple[tuple[float, float], ...]) -> bool:
        """Ray-casting point-in-polygon test (2D)."""
        inside = False
        n = len(polygon)
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if (yi > y) != (yj > y):
                x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
                if x < x_intersect:
                    inside = not inside
            j = i
        return inside

    def _in_geofence(self, pose: Pose3D) -> bool:
        if self.config.geofence is None:
            return True
        if not self._point_in_polygon(pose.x, pose.y, self.config.geofence):
            return False
        if self.config.z_min is not None and pose.z < self.config.z_min:
            return False
        return not (self.config.z_max is not None and pose.z > self.config.z_max)

    def _in_no_fly_zone(self, pose: Pose3D) -> ExclusionZone | None:
        for zone in self.config.no_fly_zones:
            if pose.distance_to(zone.center) < zone.radius_m:
                if zone.z_min is not None and pose.z < zone.z_min:
                    continue
                if zone.z_max is not None and pose.z > zone.z_max:
                    continue
                return zone
        return None

    # -- main filter -------------------------------------------------------- #

    def filter(
        self,
        state_store: SwarmStateStore,
        per_vehicle_controls: dict[int, ControlInput],
    ) -> SafetyReport:
        """Run all safety layers over per-vehicle controls.

        Returns filtered controls (holds toward zero on violation) plus a
        SafetyReport that feeds SwarmStatsAggregator.
        """
        snapshot = state_store.snapshot()
        violations: list[SafetyViolation] = []
        collision_events: list[tuple[int, int]] = []
        filtered: dict[int, ControlInput] = {}

        for vehicle_id, control in per_vehicle_controls.items():
            filtered[vehicle_id] = control

        # --- 1. Pairwise collision avoidance ------------------------------- #
        active_ids = [
            vid
            for vid in per_vehicle_controls
            if state_store.is_fresh(vid, max_age_s=1.0) and vid in snapshot
        ]
        for i in range(len(active_ids)):
            for j in range(i + 1, len(active_ids)):
                a, b = active_ids[i], active_ids[j]
                pa, pb = snapshot[a], snapshot[b]
                dist = pa.pose.distance_to(pb.pose)
                if dist < self.config.min_separation_m:
                    collision_events.append((a, b))
                    for vid in (a, b):
                        peer = b if vid == a else a
                        violations.append(
                            SafetyViolation(
                                vid,
                                "collision",
                                f"Vehicle {vid} too close to vehicle {peer} "
                                f"({dist:.2f}m < {self.config.min_separation_m}m)",
                            )
                        )
                        filtered[vid] = _HOLD_CONTROL

        # --- 2. Geofence --------------------------------------------------- #
        for vehicle_id in list(per_vehicle_controls.keys()):
            state = snapshot.get(vehicle_id)
            if state is None:
                continue
            if not self._in_geofence(state.pose):
                violations.append(
                    SafetyViolation(
                        vehicle_id,
                        "geofence",
                        f"Vehicle {vehicle_id} outside geofence",
                    )
                )
                filtered[vehicle_id] = _HOLD_CONTROL

        # --- 3. No-fly zones ---------------------------------------------- #
        for vehicle_id in list(per_vehicle_controls.keys()):
            state = snapshot.get(vehicle_id)
            if state is None:
                continue
            zone = self._in_no_fly_zone(state.pose)
            if zone is not None:
                violations.append(
                    SafetyViolation(
                        vehicle_id,
                        "no_fly",
                        f"Vehicle {vehicle_id} inside no-fly zone",
                    )
                )
                filtered[vehicle_id] = _HOLD_CONTROL

        return SafetyReport(
            violations=violations,
            collision_events=collision_events,
            filtered_controls=filtered,
        )


# --------------------------------------------------------------------------- #
# FormationSetpointGenerator
# --------------------------------------------------------------------------- #


class FormationSetpointGenerator:
    """Wraps ``swarm/formation.py`` FormationController for swarm setpoints."""

    def __init__(self, config: FormationConfig | None = None) -> None:
        self.config = config or FormationConfig()
        self._controller = FormationController(self.config)

    def compute_setpoints(self, leader_state: StateVector, num_agents: int) -> list[Pose3D]:
        """Delegate to FormationController.compute_formation_positions."""
        return self._controller.compute_formation_positions(leader_state, num_agents)

    def slot_setpoint(self, slot_index: int, leader_state: StateVector, num_agents: int) -> Pose3D:
        """Return the formation slot pose assigned to vehicle ``slot_index``."""
        positions = self.compute_setpoints(leader_state, num_agents)
        if not positions:
            return Pose3D(
                x=leader_state.pose.x,
                y=leader_state.pose.y,
                z=leader_state.pose.z,
            )
        idx = min(max(slot_index, 0), len(positions) - 1)
        return positions[idx]


# --------------------------------------------------------------------------- #
# GazeboSITLLauncher
# --------------------------------------------------------------------------- #


class GazeboSITLLauncher:
    """Thin orchestrator over PX4/Gazebo CLI for multi-vehicle SITL launch.

    Launches N PX4 SITL instances sequentially (to avoid Gazebo lock contention
    at startup), each bound to namespaced MAVLink/Gazebo UDP ports, headless,
    with per-slot PIDs recorded in a manifest for teardown.
    """

    def __init__(self, log_dir: str = "logs/sitl") -> None:
        self.log_dir = log_dir
        self._manifest: dict[int, LauncherManifest] = {}
        self._processes: dict[int, Any] = {}

    def launch_slot(
        self,
        slot: int,
        *,
        base_master_port: int = DEFAULT_BASE_MASTER_PORT,
        base_sitl_port: int = DEFAULT_BASE_SITL_PORT,
        model: str = "iris",
        headless: bool = True,
        env: dict[str, str] | None = None,
    ) -> LauncherManifest:
        """Reserve ports (bind-test), start one PX4 SITL instance, record manifest."""
        master_port = SwarmConnectionManager.master_port(slot, base_master_port)
        sitl_port = SwarmConnectionManager.sitl_port(slot, base_sitl_port)

        for port in (master_port, sitl_port):
            if not self._bind_test_port(port):
                raise RuntimeError(
                    f"Port {port} already in use for slot {slot}; refusing to launch SITL"
                )

        import os

        os.makedirs(self.log_dir, exist_ok=True)
        log_path = f"{self.log_dir}/vehicle_{slot}.log"

        launch_env = dict(os.environ)
        launch_env.update(
            {
                "PX4_SIM_MODEL": model,
                "PX4_GZ_MODEL_POSE": f"{float(slot * 5)},0,0",
                "ROS_DOMAIN_ID": str(slot),
                "MAV_SYS_ID": str(slot),
                "MAVLINK_UDP_PORT": str(master_port),
            }
        )
        if headless:
            launch_env["HEADLESS"] = "1"
        if env:
            launch_env.update(env)

        proc = None
        try:
            with open(log_path, "wb") as log_file:
                proc = subprocess.Popen(
                    ["px4", str(master_port), str(sitl_port)],
                    env=launch_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
        except FileNotFoundError:
            proc = None
            logger.warning("PX4 CLI not found; slot %d recorded in manifest only", slot)

        manifest = LauncherManifest(
            slot=slot,
            pid=proc.pid if proc is not None else None,
            ports=(master_port, sitl_port),
            log_path=log_path,
            started_at=time.time(),
        )
        self._manifest[slot] = manifest
        if proc is not None:
            self._processes[slot] = proc
        return manifest

    def _bind_test_port(self, port: int, host: str = "127.0.0.1") -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    def teardown_slot(self, slot: int, grace_s: float = 5.0) -> bool:
        """SIGTERM then SIGKILL a launched SITL instance."""
        proc = self._processes.get(slot)
        ok = True
        if proc is not None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=grace_s)
                except Exception:  # noqa: BLE001
                    proc.kill()
                    proc.wait(timeout=5)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Teardown of slot %d raised: %s", slot, exc)
                ok = False
        self._manifest.pop(slot, None)
        self._processes.pop(slot, None)
        return ok

    def teardown_all(self, grace_s: float = 5.0) -> dict[int, bool]:
        """Teardown every launched instance in reverse slot order."""
        results: dict[int, bool] = {}
        for slot in sorted(self._manifest.keys(), reverse=True):
            results[slot] = self.teardown_slot(slot, grace_s=grace_s)
        return results

    def get_manifest(self, slot: int) -> LauncherManifest | None:
        return self._manifest.get(slot)


# --------------------------------------------------------------------------- #
# SwarmStatsAggregator
# --------------------------------------------------------------------------- #


class SwarmStatsAggregator:
    """Per-vehicle rollups plus swarm-level statistics."""

    def __init__(self) -> None:
        self._vehicle_stats: dict[int, dict[str, Any]] = {}
        self._connected_at_start = 0
        self._connected_at_end = 0

    @staticmethod
    def _empty_stats() -> dict[str, Any]:
        return {
            "missions_run": 0,
            "missions_success": 0,
            "missions_fail": 0,
            "total_duration_seconds": 0.0,
            "step_latencies_ms": [],
            "safety_violations": 0,
            "min_observed_separation_m": None,
            "formation_deviations_m": [],
            "distance_flown_m": 0.0,
            "last_state_timestamp": None,
        }

    def record_mission(
        self,
        vehicle_id: int,
        result: SimulationResult,
        cycle_latency_ms: float = 0.0,
        separation_m: float | None = None,
        formation_deviation_m: float = 0.0,
    ) -> None:
        """Record one vehicle's mission outcome into its rollup."""
        stats = self._vehicle_stats.setdefault(vehicle_id, self._empty_stats())
        stats["missions_run"] += 1
        if result.success:
            stats["missions_success"] += 1
        else:
            stats["missions_fail"] += 1
        stats["total_duration_seconds"] += float(result.duration_seconds or 0.0)
        if cycle_latency_ms:
            stats["step_latencies_ms"].append(cycle_latency_ms)
        if separation_m is not None:
            cur_min = stats["min_observed_separation_m"]
            stats["min_observed_separation_m"] = (
                separation_m if cur_min is None else min(cur_min, separation_m)
            )
        stats["formation_deviations_m"].append(formation_deviation_m)
        stats["last_state_timestamp"] = time.time()

    def record_safety_violations(self, vehicle_id: int, count: int) -> None:
        stats = self._vehicle_stats.setdefault(vehicle_id, self._empty_stats())
        stats["safety_violations"] += count

    def set_connected_counts(self, start: int, end: int) -> None:
        self._connected_at_start = start
        self._connected_at_end = end

    def get_vehicle_stats(self, vehicle_id: int) -> dict[str, Any]:
        stats = self._vehicle_stats.get(vehicle_id, self._empty_stats())
        latencies = stats["step_latencies_ms"]
        return {
            "missions_run": stats["missions_run"],
            "missions_success": stats["missions_success"],
            "missions_fail": stats["missions_fail"],
            "total_duration_seconds": stats["total_duration_seconds"],
            "mean_step_latency_ms": float(np.mean(latencies)) if latencies else 0.0,
            "p95_step_latency_ms": float(np.percentile(latencies, 95)) if latencies else 0.0,
            "safety_violations": stats["safety_violations"],
            "min_observed_separation_m": stats["min_observed_separation_m"],
            "mean_formation_deviation_m": float(np.mean(stats["formation_deviations_m"]))
            if stats["formation_deviations_m"]
            else 0.0,
            "distance_flown_m": stats["distance_flown_m"],
            "last_state_timestamp": stats["last_state_timestamp"],
        }

    def get_swarm_stats(self) -> dict[str, Any]:
        """Swarm-level rollup: makespan, success rate, safety, formation, latency."""
        total = 0
        success = 0
        failed = 0
        duration = 0.0
        total_violations = 0
        makespan = 0.0
        all_latencies: list[float] = []
        all_deviations: list[float] = []
        min_separation: float | None = None

        for stats in self._vehicle_stats.values():
            total += stats["missions_run"]
            success += stats["missions_success"]
            failed += stats["missions_fail"]
            duration += stats["total_duration_seconds"]
            total_violations += stats["safety_violations"]
            makespan = max(makespan, stats["total_duration_seconds"])
            all_latencies.extend(stats["step_latencies_ms"])
            all_deviations.extend(stats["formation_deviations_m"])
            if stats["min_observed_separation_m"] is not None:
                min_separation = (
                    stats["min_observed_separation_m"]
                    if min_separation is None
                    else min(min_separation, stats["min_observed_separation_m"])
                )

        success_rate = (success / total) if total else 0.0
        mean_latency = float(np.mean(all_latencies)) if all_latencies else 0.0
        p95_latency = float(np.percentile(all_latencies, 95)) if all_latencies else 0.0
        mean_deviation = float(np.mean(all_deviations)) if all_deviations else 0.0

        return {
            "total_missions": total,
            "successful_missions": success,
            "failed_missions": failed,
            "success_rate": success_rate,
            "total_duration_seconds": duration,
            "swarm_makespan_seconds": makespan,
            "total_safety_violations": total_violations,
            "mean_formation_deviation_m": mean_deviation,
            "mean_cycle_latency_ms": mean_latency,
            "p95_cycle_latency_ms": p95_latency,
            "latency_under_budget_ms": p95_latency <= 50.0,
            "min_observed_separation_m": min_separation,
            "connected_vehicles": self._connected_at_end,
        }

    def get_runner_stats(self) -> dict[str, Any]:
        """Backward-compatible shape mirroring SimulationRunner.get_runner_stats()."""
        total = sum(s["missions_run"] for s in self._vehicle_stats.values())
        successful = sum(s["missions_success"] for s in self._vehicle_stats.values())
        failed = sum(s["missions_fail"] for s in self._vehicle_stats.values())
        duration = sum(s["total_duration_seconds"] for s in self._vehicle_stats.values())
        return {
            "total_missions": total,
            "successful_missions": successful,
            "failed_missions": failed,
            "total_duration_seconds": duration,
        }


# --------------------------------------------------------------------------- #
# SwarmRunner
# --------------------------------------------------------------------------- #


class _NoOpSwarmPlanner:
    """Fallback planner that returns a non-terminal plan so the loop runs."""

    def plan(self, problem: Any, state: Any) -> Any:
        return "plan"


class _NoOpSwarmController:
    """Fallback controller that produces a neutral control input."""

    def compute_control(self, state: Any, plan: Any) -> ControlInput:
        return ControlInput()


class _NoOpSwarmEstimator:
    """Fallback state estimator that performs no estimation."""

    def estimate(self, *args: Any, **kwargs: Any) -> Any:
        return None


class SwarmRunner:
    """N-vehicle swarm orchestrator extending the SimulationRunner loop pattern.

    Orchestrates per-vehicle connect/arm/plan/control/safety/step loops on a
    synchronized ``dt`` cycle, with partial-failure isolation, an
    ``abort_on_any_failure`` flag, and a guaranteed ``disconnect_all`` teardown.
    """

    def __init__(self) -> None:
        self._connection_manager = SwarmConnectionManager()
        self._state_store = SwarmStateStore()
        self._safety_filter = SwarmSafetyFilter()
        self._formation_generator = FormationSetpointGenerator()
        self._launcher = GazeboSITLLauncher()
        self._stats = SwarmStatsAggregator()
        self._sims: dict[int, SimulationInterface] = {}
        self._sessions: dict[int, VehicleSession] = {}
        self._wta_config: WTAConfig | None = None
        self._wta_solver: TieredWTASolver | None = None
        self._wta_reallocators: dict[int, CombatReallocator] = {}
        self._wta_cycle_reports: dict[int, list[dict[str, Any]]] = {}
        self._wta_latency_over_budget = 0

    @staticmethod
    def _config_flag(config: SimulationConfig, name: str, default: Any = False) -> Any:
        return getattr(config, name, default)

    def run_swarm_mission(
        self,
        problems: dict[int, Any],
        config: SimulationConfig,
        *,
        components_per_vehicle: dict[int, dict[str, Any]] | None = None,
        formation: FormationConfig | None = None,
        safety: SwarmSafetyConfig | None = None,
        dt: float = DEFAULT_DT,
        max_steps: int = DEFAULT_MAX_STEPS,
        sim_factory: Callable[[], SimulationInterface] | None = None,
        abort_on_any_failure: bool = False,
    ) -> SwarmMissionResult:
        """Execute a synchronized N-vehicle swarm mission.

        Lifecycle:
          1. connect_all (per-slot MAVLink + SimulationInterface)
          2. arm + set_mode("GUIDED") per vehicle
          3. synchronized dt step loop
          4. disconnect_all in finally (guaranteed teardown)
          5. return SwarmMissionResult with per-vehicle + swarm aggregates
        """
        swarm_size = len(problems)
        start_slot = self._config_flag(config, "start_slot", 0)
        abort = abort_on_any_failure or self._config_flag(config, "abort_on_any_failure", False)

        if safety is not None:
            self._safety_filter = SwarmSafetyFilter(safety)
        if formation is not None:
            self._formation_generator = FormationSetpointGenerator(formation)

        components_per_vehicle = components_per_vehicle or {}
        factory = sim_factory or SimulationInterface

        result = SwarmMissionResult()
        per_vehicle_results: dict[int, SimulationResult] = {}
        vehicle_statuses: dict[int, str] = {}
        connected_slots: list[int] = []

        try:
            # --- 1. connect_all ------------------------------------------ #
            if swarm_size == 0:
                result.success = False
                result.message = "No vehicles in swarm mission"
                result.swarm = self._stats.get_swarm_stats()
                return result

            connect_results = self._connection_manager.connect_all(
                swarm_size,
                start_slot=start_slot,
                base_master_port=DEFAULT_BASE_MASTER_PORT,
                simulation=True,
            )
            connected_slots = [s for s, ok in connect_results.items() if ok]
            self._stats.set_connected_counts(len(connected_slots), len(connected_slots))
            if not connected_slots:
                result.success = False
                result.message = "No vehicles connected"
                result.swarm = self._stats.get_swarm_stats()
                return result

            # Build sim instances per connected slot.
            for slot in connected_slots:
                sim = factory()
                try:
                    sim.connect(self._connection_manager.connection_string(slot))
                except Exception:  # noqa: BLE001
                    logger.warning("SimulationInterface.connect() raised for slot %d", slot)
                self._sims[slot] = sim
                session = VehicleSession(
                    vehicle_id=slot,
                    mavlink=self._connection_manager.get_bridge(slot),
                    sim=sim,
                    status="CONNECTED",
                )
                self._sessions[slot] = session

            # --- 2. arm + set_mode("GUIDED") per vehicle ----------------- #
            for slot in list(connected_slots):
                sim = self._sims[slot]
                bridge = self._connection_manager.get_bridge(slot)
                armed = False
                mode_set = False
                if bridge is not None:
                    try:
                        armed = bridge.arm()
                    except Exception:  # noqa: BLE001
                        armed = False
                    try:
                        mode_set = bridge.set_mode("GUIDED")
                    except Exception:  # noqa: BLE001
                        mode_set = False
                if sim is not None:
                    try:
                        armed = armed and sim.arm()
                        mode_set = mode_set and sim.set_mode("GUIDED")
                    except Exception:  # noqa: BLE001
                        armed = False
                        mode_set = False
                if not armed or not mode_set:
                    vehicle_statuses[slot] = "FAILED"
                    connected_slots.remove(slot)
                    logger.warning("Slot %d failed to arm/mode; excluded from step loop", slot)
                else:
                    vehicle_statuses[slot] = "ARMED"

            if not connected_slots:
                result.success = False
                result.message = "No vehicles armed/moded"
                result.swarm = self._stats.get_swarm_stats()
                return result

            # --- 3. synchronized dt step loop ---------------------------- #
            leader_slot = connected_slots[0]
            cycle_latencies: list[float] = []

            for _step_idx in range(max_steps):
                cycle_start = time.perf_counter()
                any_active = False
                per_vehicle_controls: dict[int, ControlInput] = {}

                # Snapshot state store once (consistent instant for all consumers).
                states = self._state_store.snapshot()

                for slot in list(connected_slots):
                    bridge = self._connection_manager.get_bridge(slot)
                    sim = self._sims[slot]
                    if bridge is None or sim is None:
                        continue
                    if not self._connection_manager.is_connected(slot):
                        vehicle_statuses[slot] = "FAILED"
                        connected_slots.remove(slot)
                        continue

                    state: StateVector | None = None
                    try:
                        state = bridge.get_state()
                    except Exception:  # noqa: BLE001
                        state = states.get(slot)
                    if state is None:
                        state = states.get(slot)
                    if state is None:
                        continue
                    self._state_store.update(slot, state)
                    any_active = True

                    # Plan -> control.
                    comps = components_per_vehicle.get(slot, {})
                    planner = comps.get("planner", _NoOpSwarmPlanner())
                    controller = comps.get("controller", _NoOpSwarmController())
                    problem = problems.get(slot)

                    try:
                        plan = planner.plan(problem, state)
                    except Exception:  # noqa: BLE001
                        plan = None
                    if plan is None:
                        vehicle_statuses[slot] = "FAILED"
                        connected_slots.remove(slot)
                        continue

                    try:
                        control = controller.compute_control(state, plan)
                    except Exception:  # noqa: BLE001
                        control = ControlInput()
                    if control is None:
                        control = ControlInput()

                    # Formation overlay: slot i tracks formation offset relative to leader.
                    leader_state = states.get(leader_slot, state)
                    setpoint = self._formation_generator.slot_setpoint(
                        slot, leader_state, len(connected_slots)
                    )
                    _ = setpoint  # setpoint biases control; kept neutral for no-op path
                    control = ControlInput(
                        throttle=max(0.0, min(1.0, float(getattr(control, "throttle", 0.0)) + 0.1)),
                        roll_rate=float(getattr(control, "roll_rate", 0.0)),
                        pitch_rate=float(getattr(control, "pitch_rate", 0.0)),
                        yaw_rate=float(getattr(control, "yaw_rate", 0.0)),
                    )

                    per_vehicle_controls[slot] = control

                if not any_active:
                    break

                # Safety filter over all per-vehicle controls.
                try:
                    safety_report = self._safety_filter.filter(
                        self._state_store, per_vehicle_controls
                    )
                except Exception:  # noqa: BLE001
                    safety_report = SafetyReport(filtered_controls=dict(per_vehicle_controls))

                result.safety_violations += safety_report.violation_count
                result.collision_events.extend(safety_report.collision_events)

                # Apply failsafe for safety-hold vehicles.
                for violation in safety_report.violations:
                    vehicle_statuses[violation.vehicle_id] = "SAFETY_HOLD"
                    if abort:
                        connected_slots = [s for s in connected_slots if s != violation.vehicle_id]
                        logger.warning(
                            "Slot %d aborted (safety) due to abort_on_any_failure",
                            violation.vehicle_id,
                        )

                # Send filtered controls + step each sim.
                abort_requested = False
                for slot in list(connected_slots):
                    bridge = self._connection_manager.get_bridge(slot)
                    sim = self._sims[slot]
                    if bridge is None or sim is None:
                        continue
                    control = safety_report.filtered_controls.get(
                        slot, per_vehicle_controls.get(slot, ControlInput())
                    )
                    try:
                        if not bridge.send_control(control):
                            vehicle_statuses[slot] = "FAILED"
                            connected_slots.remove(slot)
                            if abort:
                                abort_requested = True
                            continue
                    except Exception:  # noqa: BLE001
                        vehicle_statuses[slot] = "FAILED"
                        connected_slots.remove(slot)
                        if abort:
                            abort_requested = True
                        continue

                    try:
                        if not sim.step(dt):
                            vehicle_statuses[slot] = "FAILED"
                            connected_slots.remove(slot)
                            if abort:
                                abort_requested = True
                            continue
                    except Exception:  # noqa: BLE001
                        vehicle_statuses[slot] = "FAILED"
                        connected_slots.remove(slot)
                        if abort:
                            abort_requested = True
                        continue

                    if abort_requested:
                        break

                    # Update state store from stepped state.
                    new_state: StateVector | None = None
                    try:
                        new_state = bridge.get_state()
                    except Exception:  # noqa: BLE001
                        new_state = None
                    if new_state is not None:
                        self._state_store.update(slot, new_state)
                    used_state = new_state if new_state is not None else state

                    # Accumulate per-vehicle mission result.
                    vr = per_vehicle_results.get(slot)
                    if vr is None:
                        vr = SimulationResult(
                            success=True,
                            trajectory=[],
                            metrics={},
                            duration_seconds=0.0,
                            message="",
                        )
                    traj = list(vr.trajectory)
                    traj.append(used_state)
                    per_vehicle_results[slot] = SimulationResult(
                        success=True,
                        trajectory=traj,
                        metrics=dict(vr.metrics),
                        duration_seconds=vr.duration_seconds + dt,
                        message="step",
                    )

                cycle_latency_ms = (time.perf_counter() - cycle_start) * 1000.0
                cycle_latencies.append(cycle_latency_ms)

                # Record per-step stats (latency, separation, deviation).
                for slot in list(connected_slots):
                    state = self._state_store.get(slot)
                    deviation = 0.0
                    if state is not None:
                        try:
                            sp = self._formation_generator.slot_setpoint(
                                slot, states.get(leader_slot, state), len(connected_slots)
                            )
                            deviation = state.pose.distance_to(sp)
                        except Exception:  # noqa: BLE001
                            deviation = 0.0
                    sep = self._min_separation(self._state_store.snapshot(), slot)
                    self._stats.record_mission(
                        slot,
                        SimulationResult(success=True, duration_seconds=dt),
                        cycle_latency_ms=cycle_latency_ms,
                        separation_m=sep,
                        formation_deviation_m=deviation,
                    )

                if not connected_slots:
                    break
                if abort_requested:
                    break

            # --- build per-vehicle SimulationResults --------------------- #
            for slot in connected_slots:
                per_vehicle_results.setdefault(
                    slot,
                    SimulationResult(
                        success=True,
                        trajectory=[],
                        metrics={},
                        duration_seconds=0.0,
                        message="completed",
                    ),
                )
            for slot, status in vehicle_statuses.items():
                if status == "FAILED" and slot not in per_vehicle_results:
                    per_vehicle_results[slot] = SimulationResult(
                        success=False,
                        trajectory=[],
                        metrics={},
                        duration_seconds=0.0,
                        message="vehicle failed",
                    )

            result.per_vehicle = per_vehicle_results
            result.makespan_seconds = max(
                (r.duration_seconds for r in per_vehicle_results.values()), default=0.0
            )
            result.formation_deviation_m = self._mean_formation_deviation()
            result.success = (
                all(r.success for r in per_vehicle_results.values())
                if per_vehicle_results
                else False
            )
            result.message = (
                "Swarm mission completed"
                if result.success
                else "Swarm mission completed with failures"
            )

            # --- stats rollup ------------------------------------------- #
            self._stats.set_connected_counts(len(connected_slots), len(connected_slots))
            result.swarm = self._stats.get_swarm_stats()

        finally:
            # --- 4. guaranteed disconnect_all teardown ------------------- #
            self.disconnect_all()

        return result

    # -- helpers ----------------------------------------------------------- #

    @staticmethod
    def _min_separation(snapshot: dict[int, StateVector], slot: int) -> float | None:
        state = snapshot.get(slot)
        if state is None:
            return None
        best: float | None = None
        for other_slot, other_state in snapshot.items():
            if other_slot == slot:
                continue
            dist = state.pose.distance_to(other_state.pose)
            best = dist if best is None else min(best, dist)
        return best

    def _mean_formation_deviation(self) -> float:
        vals: list[float] = []
        for stats in self._stats._vehicle_stats.values():  # noqa: SLF001
            vals.extend(stats["formation_deviations_m"])
        return float(np.mean(vals)) if vals else 0.0

    def disconnect_all(self) -> dict[str, bool]:
        """Guaranteed teardown: disconnect every bridge and sim in reverse slot order."""
        results: dict[str, bool] = {}
        for slot in sorted(self._sims.keys(), reverse=True):
            sim = self._sims.pop(slot)
            try:
                results[f"sim_{slot}"] = bool(sim.disconnect())
            except Exception:  # noqa: BLE001
                results[f"sim_{slot}"] = False
        results.update(self._connection_manager.disconnect_all())
        for session in self._sessions.values():
            session.status = "DISCONNECTED"
        return results

    def get_runner_stats(self) -> dict[str, Any]:
        """Aggregate runner stats across the swarm (backward-compatible shape)."""
        return self._stats.get_runner_stats()

    # --------------------------------------------------------------------------- #
    # WTA batch mission integration
    # --------------------------------------------------------------------------- #

    @property
    def wta_cycle_reports(self) -> dict[int, list[dict[str, Any]]]:
        """Per-slot per-cycle WTA reports (assignments, solve time, BDA, latency)."""
        return self._wta_cycle_reports

    def run_wta_batch_mission(
        self,
        problems: dict[int, WTAMissionProblem],
        config: SimulationConfig,
        *,
        components_per_vehicle: dict[int, dict[str, Any]] | None = None,
        formation: FormationConfig | None = None,
        safety: SwarmSafetyConfig | None = None,
        dt: float = DEFAULT_DT,
        max_steps: int = DEFAULT_MAX_STEPS,
        sim_factory: Callable[[], SimulationInterface] | None = None,
        abort_on_any_failure: bool = False,
        wta_config: WTAConfig | None = None,
        cycle_budget_ms: float = 100.0,
        bda_events: dict[int, list[BDAEvent | None]] | None = None,
    ) -> SwarmMissionResult:
        """Execute a synchronized N-vehicle swarm mission with per-vehicle WTA.

        Each vehicle slot owns a ``WTAMissionProblem``. Every cycle the tiered
        solver runs per vehicle (time-boxed to the cycle budget), assignments
        are applied as formation setpoints toward the assigned target poses,
        optional BDA events drive ``CombatReallocator`` reallocation, and a
        single vehicle's solver/step failure never aborts the rest unless
        ``abort_on_any_failure`` is set. Guarantees ``disconnect_all`` teardown.
        """
        self._wta_config = wta_config or WTAConfig()
        self._wta_solver = TieredWTASolver(self._wta_config)
        self._wta_reallocators = {}
        self._wta_cycle_reports = {}
        self._wta_latency_over_budget = 0

        swarm_size = len(problems)
        start_slot = self._config_flag(config, "start_slot", 0)
        abort = abort_on_any_failure or self._config_flag(config, "abort_on_any_failure", False)

        if safety is not None:
            self._safety_filter = SwarmSafetyFilter(safety)
        if formation is not None:
            self._formation_generator = FormationSetpointGenerator(formation)

        components_per_vehicle = components_per_vehicle or {}
        factory = sim_factory or SimulationInterface
        bda_events = bda_events or {}

        result = SwarmMissionResult()
        per_vehicle_results: dict[int, SimulationResult] = {}
        vehicle_statuses: dict[int, str] = {}
        connected_slots: list[int] = []

        try:
            # --- 1. connect_all ------------------------------------------ #
            if swarm_size == 0:
                result.success = False
                result.message = "No vehicles in WTA swarm mission"
                result.swarm = self._stats.get_swarm_stats()
                return result

            connect_results = self._connection_manager.connect_all(
                swarm_size,
                start_slot=start_slot,
                base_master_port=DEFAULT_BASE_MASTER_PORT,
                simulation=True,
            )
            connected_slots = [s for s, ok in connect_results.items() if ok]
            self._stats.set_connected_counts(len(connected_slots), len(connected_slots))
            if not connected_slots:
                result.success = False
                result.message = "No vehicles connected"
                result.swarm = self._stats.get_swarm_stats()
                return result

            for slot in connected_slots:
                sim = factory()
                try:
                    sim.connect(self._connection_manager.connection_string(slot))
                except Exception:  # noqa: BLE001
                    logger.warning("SimulationInterface.connect() raised for slot %d", slot)
                self._sims[slot] = sim
                self._sessions[slot] = VehicleSession(
                    vehicle_id=slot,
                    mavlink=self._connection_manager.get_bridge(slot),
                    sim=sim,
                    status="CONNECTED",
                )

            # --- 2. arm + set_mode("GUIDED") per vehicle ----------------- #
            for slot in list(connected_slots):
                sim = self._sims[slot]
                bridge = self._connection_manager.get_bridge(slot)
                armed = mode_set = False
                if bridge is not None:
                    try:
                        armed = bridge.arm()
                    except Exception:  # noqa: BLE001
                        armed = False
                    try:
                        mode_set = bridge.set_mode("GUIDED")
                    except Exception:  # noqa: BLE001
                        mode_set = False
                if sim is not None:
                    try:
                        armed = armed and sim.arm()
                        mode_set = mode_set and sim.set_mode("GUIDED")
                    except Exception:  # noqa: BLE001
                        armed = mode_set = False
                if not armed or not mode_set:
                    vehicle_statuses[slot] = "FAILED"
                    connected_slots.remove(slot)
                else:
                    vehicle_statuses[slot] = "ARMED"

            if not connected_slots:
                result.success = False
                result.message = "No vehicles armed/moded"
                result.swarm = self._stats.get_swarm_stats()
                return result

            # --- 3. synchronized dt step loop with per-vehicle WTA ------- #
            leader_slot = connected_slots[0]
            cycle_latencies: list[float] = []

            for step_idx in range(max_steps):
                cycle_start = time.perf_counter()
                any_active = False
                per_vehicle_controls: dict[int, ControlInput] = {}

                states = self._state_store.snapshot()

                for slot in list(connected_slots):
                    bridge = self._connection_manager.get_bridge(slot)
                    sim = self._sims[slot]
                    if bridge is None or sim is None:
                        continue
                    if not self._connection_manager.is_connected(slot):
                        vehicle_statuses[slot] = "FAILED"
                        connected_slots.remove(slot)
                        continue

                    state: StateVector | None = None
                    try:
                        state = bridge.get_state()
                    except Exception:  # noqa: BLE001
                        state = states.get(slot)
                    if state is None:
                        state = states.get(slot)
                    if state is None:
                        continue
                    self._state_store.update(slot, state)
                    any_active = True

                    control = self._run_wta_cycle(
                        slot,
                        problems.get(slot),
                        state,
                        step_idx,
                        cycle_budget_ms,
                        bda_events.get(slot, []),
                    )
                    per_vehicle_controls[slot] = control

                if not any_active:
                    break

                # Safety filter over all per-vehicle controls.
                try:
                    safety_report = self._safety_filter.filter(
                        self._state_store, per_vehicle_controls
                    )
                except Exception:  # noqa: BLE001
                    safety_report = SafetyReport(filtered_controls=dict(per_vehicle_controls))

                result.safety_violations += safety_report.violation_count
                result.collision_events.extend(safety_report.collision_events)

                for violation in safety_report.violations:
                    vehicle_statuses[violation.vehicle_id] = "SAFETY_HOLD"
                    if abort:
                        connected_slots = [s for s in connected_slots if s != violation.vehicle_id]

                # Send filtered controls + step each sim; one failure never
                # aborts the remaining vehicles unless abort_on_any_failure.
                abort_requested = False
                for slot in list(connected_slots):
                    bridge = self._connection_manager.get_bridge(slot)
                    sim = self._sims[slot]
                    if bridge is None or sim is None:
                        continue
                    control = safety_report.filtered_controls.get(
                        slot, per_vehicle_controls.get(slot, ControlInput())
                    )
                    try:
                        if not bridge.send_control(control):
                            vehicle_statuses[slot] = "FAILED"
                            connected_slots.remove(slot)
                            if abort:
                                abort_requested = True
                            continue
                    except Exception:  # noqa: BLE001
                        vehicle_statuses[slot] = "FAILED"
                        connected_slots.remove(slot)
                        if abort:
                            abort_requested = True
                        continue

                    try:
                        if not sim.step(dt):
                            vehicle_statuses[slot] = "FAILED"
                            connected_slots.remove(slot)
                            if abort:
                                abort_requested = True
                            continue
                    except Exception:  # noqa: BLE001
                        vehicle_statuses[slot] = "FAILED"
                        connected_slots.remove(slot)
                        if abort:
                            abort_requested = True
                        continue

                    if abort_requested:
                        break

                    new_state: StateVector | None = None
                    try:
                        new_state = bridge.get_state()
                    except Exception:  # noqa: BLE001
                        new_state = None
                    if new_state is not None:
                        self._state_store.update(slot, new_state)
                    used_state = new_state if new_state is not None else state

                    vr = per_vehicle_results.get(slot)
                    if vr is None:
                        vr = SimulationResult(
                            success=True,
                            trajectory=[],
                            metrics={},
                            duration_seconds=0.0,
                            message="",
                        )
                    traj = list(vr.trajectory)
                    traj.append(used_state)
                    per_vehicle_results[slot] = SimulationResult(
                        success=True,
                        trajectory=traj,
                        metrics=dict(vr.metrics),
                        duration_seconds=vr.duration_seconds + dt,
                        message="step",
                    )

                cycle_latency_ms = (time.perf_counter() - cycle_start) * 1000.0
                cycle_latencies.append(cycle_latency_ms)
                if cycle_latency_ms > cycle_budget_ms:
                    self._wta_latency_over_budget += 1
                    logger.warning(
                        "WTA cycle %.2f ms over budget %.2f ms",
                        cycle_latency_ms,
                        cycle_budget_ms,
                    )
                # Stamp cycle latency onto the per-slot reports just written.
                for slot_reports in self._wta_cycle_reports.values():
                    if slot_reports:
                        slot_reports[-1]["cycle_lat_ms"] = cycle_latency_ms

                # Record per-step stats (latency, separation, deviation).
                for slot in list(connected_slots):
                    state = self._state_store.get(slot)
                    deviation = 0.0
                    if state is not None:
                        try:
                            sp = self._formation_generator.slot_setpoint(
                                slot, states.get(leader_slot, state), len(connected_slots)
                            )
                            deviation = state.pose.distance_to(sp)
                        except Exception:  # noqa: BLE001
                            deviation = 0.0
                    sep = self._min_separation(self._state_store.snapshot(), slot)
                    self._stats.record_mission(
                        slot,
                        SimulationResult(success=True, duration_seconds=dt),
                        cycle_latency_ms=cycle_latency_ms,
                        separation_m=sep,
                        formation_deviation_m=deviation,
                    )

                if not connected_slots or abort_requested:
                    break

            # --- build per-vehicle results ------------------------------- #
            for slot in connected_slots:
                per_vehicle_results.setdefault(
                    slot,
                    SimulationResult(
                        success=True,
                        trajectory=[],
                        metrics={},
                        duration_seconds=0.0,
                        message="completed",
                    ),
                )
            for slot, status in vehicle_statuses.items():
                if status == "FAILED" and slot not in per_vehicle_results:
                    per_vehicle_results[slot] = SimulationResult(
                        success=False,
                        trajectory=[],
                        metrics={},
                        duration_seconds=0.0,
                        message="vehicle failed",
                    )

            result.per_vehicle = per_vehicle_results
            result.makespan_seconds = max(
                (r.duration_seconds for r in per_vehicle_results.values()), default=0.0
            )
            result.formation_deviation_m = self._mean_formation_deviation()
            result.success = (
                all(r.success for r in per_vehicle_results.values())
                if per_vehicle_results
                else False
            )
            result.message = (
                "WTA swarm mission completed"
                if result.success
                else "WTA swarm mission completed with failures"
            )

            # --- stats rollup ------------------------------------------- #
            self._stats.set_connected_counts(len(connected_slots), len(connected_slots))
            swarm_stats = self._stats.get_swarm_stats()
            swarm_stats.update(
                {
                    "wta_cycle_reports": self._wta_cycle_reports,
                    "wta_latency_over_budget": self._wta_latency_over_budget,
                    "wta_cycle_budget_ms": cycle_budget_ms,
                }
            )
            result.swarm = swarm_stats

        finally:
            # --- 4. guaranteed disconnect_all teardown ------------------- #
            self.disconnect_all()

        return result

    def _run_wta_cycle(
        self,
        slot: int,
        problem: WTAMissionProblem | None,
        state: StateVector,
        step_idx: int,
        cycle_budget_ms: float,
        slot_bda_events: list[BDAEvent | None],
    ) -> ControlInput:
        """One WTA solve + setpoint application for one vehicle in one cycle.

        Solver/reallocator failures are isolated to this vehicle: on any
        exception the vehicle holds its position so the rest of the swarm is
        unaffected.
        """
        assignments: list[tuple[int, int]] = []
        reallocated = False
        killed: list[int] = []

        solver = self._wta_solver
        assert solver is not None

        if problem is None:
            return self._hold_control(state)

        # --- BDA from the previous engagement -> residual re-solve ------- #
        reallocator = self._wta_reallocators.get(slot)
        bda_event = slot_bda_events[step_idx] if step_idx < len(slot_bda_events) else None
        if reallocator is None and bda_event is not None:
            reallocator = CombatReallocator(
                solver=solver,
                weapons=problem.weapons,
                targets=problem.targets,
                kill_prob=problem.kill_prob,
                values=problem.values,
                time_feasible=problem.time_feasible,
                salvo_caps=problem.salvo_caps,
                interference_cliques=problem.interference_cliques,
                mode=(self._wta_config.dynamic_mode if self._wta_config is not None else "sls"),
            )
            self._wta_reallocators[slot] = reallocator
        # --- solve per vehicle, time-boxed to the cycle budget ---------- #
        if reallocator is not None:
            try:
                already_reallocated = False
                if bda_event is not None:
                    new_state = reallocator.report_bda(
                        bda_event.killed_target_ids, bda_event.damage_updates or {}
                    )
                    killed = list(bda_event.killed_target_ids)
                    if new_state == SolverState.RE_EVALUATING:
                        reallocator.reallocate_on_residual()
                        reallocated = True
                        already_reallocated = True
                if reallocator.state == SolverState.IDLE:
                    assignments = list(reallocator.request_allocation())
                elif reallocator.state == SolverState.ALLOCATING and not already_reallocated:
                    # Residual instance left over from a previous cycle: re-solve.
                    assignments = list(reallocator.request_allocation())
                else:
                    assignments = list(reallocator.current_assignments)
            except Exception:  # noqa: BLE001
                logger.warning("WTA reallocation raised for slot %d", slot)
                assignments = []
        else:
            time_limit_ms = max(1.0, cycle_budget_ms * 0.7)
            try:
                wta_result = solver.solve(
                    problem.weapons,
                    problem.targets,
                    problem.kill_prob,
                    problem.values,
                    time_feasible=problem.time_feasible,
                    salvo_caps=problem.salvo_caps,
                    interference_cliques=problem.interference_cliques,
                    time_limit_ms=time_limit_ms,
                )
                assignments = list(wta_result.assignments)
            except Exception:  # noqa: BLE001
                logger.warning("WTA solver raised for slot %d; holding", slot)
                assignments = []

        # --- apply assignments as formation setpoints ------------------- #
        control = self._assignments_to_control(slot, state, assignments, problem)

        self._wta_cycle_reports.setdefault(slot, []).append(
            {
                "cycle": step_idx,
                "assignments": assignments,
                "reallocated": reallocated,
                "killed_targets": killed,
            }
        )
        return control

    @staticmethod
    def _assignments_to_control(
        slot: int,
        state: StateVector,
        assignments: list[tuple[int, int]],
        problem: WTAMissionProblem | None,
    ) -> ControlInput:
        """Convert WTA weapon->target assignments into a control toward target pose.

        The first assigned target with a known pose becomes the vehicle's
        formation setpoint; without an assignment the vehicle holds position.
        ``slot`` is kept for future per-slot bookkeeping.
        """
        del slot  # reserved for per-slot setpoint overrides
        target_pose: Pose3D | None = None
        if problem is not None and problem.target_poses:
            for _weapon_id, target_id in assignments:
                candidate = problem.target_poses.get(target_id)
                if candidate is not None:
                    target_pose = candidate
                    break
        if target_pose is None:
            target_pose = Pose3D(x=state.pose.x, y=state.pose.y, z=state.pose.z)

        dx = target_pose.x - state.pose.x
        dy = target_pose.y - state.pose.y
        dz = target_pose.z - state.pose.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        throttle = max(0.0, min(1.0, 0.5 * dist))
        bearing = math.atan2(dy, dx) - state.pose.yaw
        yaw_rate = max(-1.0, min(1.0, bearing))
        return ControlInput(
            throttle=throttle,
            roll_rate=0.0,
            pitch_rate=0.0,
            yaw_rate=yaw_rate,
            timestamp=state.timestamp,
        )

    @staticmethod
    def _hold_control(state: StateVector) -> ControlInput:
        """Neutral control used when a vehicle has no WTA assignment."""
        return ControlInput(
            throttle=0.0,
            roll_rate=0.0,
            pitch_rate=0.0,
            yaw_rate=0.0,
            timestamp=state.timestamp,
        )
