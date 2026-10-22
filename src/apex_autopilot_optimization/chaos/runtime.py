"""Runtime fault injection into live components.

Wraps component methods (``CBFFilter.filter``,
``CombatReallocator.request_allocation``/``report_bda``,
``PolicyEngine.evaluate_assignment``/``evaluate_action``, HITL ``submit``,
``VetoManager.issue``) with fault behaviors so resilience is exercised
against real component code, not just a fault tracker.

Usage::

    from apex_autopilot_optimization.chaos.runtime import RuntimeFaultInjector

    injector = RuntimeFaultInjector()
    with injector.scope():
        injector.apply(cbf, "filter", FaultType.SENSOR_NOISE, {"noise_std": 0.5})
        result = cbf.filter(state, control, obstacles)  # noisy inputs
    # original methods restored on exit
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar

import numpy as np

from apex_autopilot_optimization.chaos.config import ChaosConfig
from apex_autopilot_optimization.chaos.faults import FaultSpec, FaultType, Severity
from apex_autopilot_optimization.chaos.injector import FaultInjector
from apex_autopilot_optimization.chaos.result import ChaosResult

__all__ = [
    "RuntimeFaultInjector",
    "inject_fault_behavior",
    "BEHAVIORS",
    "fault_scope",
]

# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #

FaultFn = Callable[..., Any]
Behavior = Callable[[FaultFn, tuple, dict[str, Any], dict[str, Any]], Any]
T = TypeVar("T")

# sentinel so callers can distinguish "no clock" from a real clock
_NO_CLOCK: Any = object()


# --------------------------------------------------------------------------- #
# Primitive fault behaviors
# --------------------------------------------------------------------------- #

def _passthrough(original: FaultFn, args: tuple, kwargs: dict[str, Any], params: dict[str, Any]) -> Any:
    return original(*args, **kwargs)


def _rng(params: dict[str, Any]) -> np.random.Generator:
    seed = params.get("seed")
    return np.random.default_rng(seed)


def _cpu_spike(original, args, kwargs, params):
    """Burn wall-clock time before the call to stress cycle budgets."""
    delay_sec = float(params.get("delay_sec", 0.05))
    import time

    time.sleep(delay_sec)
    return original(*args, **kwargs)


def _sensor_noise(original, args, kwargs, params):
    """Add Gaussian noise to a StateVector position and obstacle centers.

    Targets ``CBFFilter.filter(state, control, obstacles)``.
    """
    noise_std = float(params.get("noise_std", 0.5))
    rng = _rng(params)
    new_args = list(args)
    state_idx = 1  # args[0] is the component instance (self) when patched on a class
    if len(new_args) > state_idx and hasattr(new_args[state_idx], "pose"):
        s = new_args[state_idx]
        new_args[state_idx] = _noisy_state(s, rng, noise_std)
    obs_idx = 3  # self, state, control, obstacles
    if len(new_args) > obs_idx and isinstance(new_args[obs_idx], list):
        new_args[obs_idx] = [_noisy_obstacle(o, rng, noise_std) for o in new_args[obs_idx]]
    return original(*new_args, **kwargs)


def _noisy_state(state, rng, noise_std):
    from apex_autopilot_optimization.core.types import Pose3D, StateVector, Velocity3D

    return StateVector(
        pose=Pose3D(
            x=float(state.pose.x) + float(rng.normal(0.0, noise_std)),
            y=float(state.pose.y) + float(rng.normal(0.0, noise_std)),
            z=float(state.pose.z) + float(rng.normal(0.0, noise_std)),
            roll=state.pose.roll,
            pitch=state.pose.pitch,
            yaw=state.pose.yaw,
        ),
        velocity=state.velocity,
        timestamp=state.timestamp,
    )


def _noisy_obstacle(obs, rng, noise_std):
    if not isinstance(obs, dict) or obs.get("type") != "sphere":
        return obs
    center = obs["center"]
    return {
        "type": "sphere",
        "center": [float(c) + float(rng.normal(0.0, noise_std)) for c in center],
        "radius": float(obs.get("radius", 0.0)),
    }


def _sensor_dropout(original, args, kwargs, params):
    """Hide obstacles probabilistically so CBF may pass control through.

    Targets ``CBFFilter.filter(state, control, obstacles)``.
    """
    dropout_prob = float(params.get("dropout_prob", 1.0))
    rng = _rng(params)
    new_args = list(args)
    obs_idx = 3  # self, state, control, obstacles
    if len(new_args) > obs_idx and isinstance(new_args[obs_idx], list):
        new_args[obs_idx] = [o for o in new_args[obs_idx] if rng.random() > dropout_prob]
    return original(*new_args, **kwargs)


def _actuator_failure(original, args, kwargs, params):
    """Clamp the control output throttle to a stuck value.

    Targets anything returning a ``ControlInput`` (``CBFFilter.filter``).
    """
    stuck_throttle = float(params.get("stuck_throttle", 0.0))
    result = original(*args, **kwargs)
    if hasattr(result, "throttle") and hasattr(result, "roll_rate"):
        result = type(result)(
            throttle=stuck_throttle,
            roll_rate=result.roll_rate,
            pitch_rate=result.pitch_rate,
            yaw_rate=result.yaw_rate,
            timestamp=getattr(result, "timestamp", 0.0),
        )
    return result


def _network_drop(original, args, kwargs, params):
    """Drop the call (return None) or raise ConnectionError probabilistically."""
    drop_prob = float(params.get("drop_prob", 1.0))
    raise_on_drop = bool(params.get("raise_on_drop", False))
    rng = _rng(params)
    if rng.random() < drop_prob:
        if raise_on_drop:
            raise ConnectionError(params.get("reason", "network drop"))
        return None
    return original(*args, **kwargs)


def _packet_loss(original, args, kwargs, params):
    """Alias of network_drop for packet-loss semantics."""
    return _network_drop(original, args, kwargs, params)


def _communication_error(original, args, kwargs, params):
    """Raise a communication error on the call."""
    raise ConnectionError(params.get("reason", "communication error"))


def _memory_pressure(original, args, kwargs, params):
    """Raise MemoryError probabilistically."""
    prob = float(params.get("prob", 0.5))
    rng = _rng(params)
    if rng.random() < prob:
        raise MemoryError(params.get("reason", "memory pressure"))
    return original(*args, **kwargs)


def _clock_drift(original, args, kwargs, params):
    """No-op for method patching; clock drift is applied via ``apply_clock_drift``."""
    return original(*args, **kwargs)


# Map FaultType -> behavior. Behaviors that need component-specific access
# (clock drift, attribute patching) are handled separately in apply().
BEHAVIORS: dict[FaultType, Behavior] = {
    FaultType.NETWORK_DELAY: _cpu_spike,
    FaultType.CPU_SPIKE: _cpu_spike,
    FaultType.MEMORY_PRESSURE: _memory_pressure,
    FaultType.SENSOR_NOISE: _sensor_noise,
    FaultType.SENSOR_DROPOUT: _sensor_dropout,
    FaultType.ACTUATOR_FAILURE: _actuator_failure,
    FaultType.NETWORK_DROP: _network_drop,
    FaultType.PACKET_LOSS: _packet_loss,
    FaultType.COMMUNICATION_ERROR: _communication_error,
    FaultType.CLOCK_DRIFT: _clock_drift,
}


def _bound_behavior(original: FaultFn, behavior: Behavior, params: dict[str, Any]) -> FaultFn:
    def wrapped(*args, **kwargs):
        return behavior(original, args, kwargs, params)

    wrapped.__wrapped__ = original  # type: ignore[attr-defined]
    wrapped.__fault_params__ = params  # type: ignore[attr-defined]
    return wrapped


# --------------------------------------------------------------------------- #
# Runtime fault injector
# --------------------------------------------------------------------------- #


class RuntimeFaultInjector:
    """Injects faults into live component methods and tracks them.

    Patching is temporary: ``restore``/``restore_all`` reinstalls the
    original methods, and the ``scope`` context manager restores on exit.
    """

    def __init__(self, injector: FaultInjector | None = None, config: ChaosConfig | None = None):
        self._injector = injector or FaultInjector(config=config)
        self._patches: list[tuple[object, str, Any]] = []
        self._clock_patches: list[tuple[object, str, Any]] = []

    # -- method patching ---------------------------------------------------
    def apply(
        self,
        obj: Any,
        method_name: str,
        fault_type: FaultType,
        params: dict[str, Any] | None = None,
    ) -> ChaosResult | None:
        """Wrap ``obj.method_name`` with the behavior for ``fault_type``.

        Patches the *class* so the fault lands on ``slots=True`` components
        (whose instances forbid arbitrary attribute assignment) as well as
        regular classes. Returns the :class:`ChaosResult` recorded by the
        underlying injector, or None if injection was rejected.
        """
        params = dict(params or {})
        cls = type(obj)
        original = getattr(cls, method_name)
        behavior = BEHAVIORS.get(fault_type, _passthrough)
        wrapped = _bound_behavior(original, behavior, params)
        setattr(cls, method_name, wrapped)
        target = f"{cls.__name__}.{method_name}"
        result = self._injector.inject_fault(fault_type, target, params)
        self._patches.append((cls, method_name, original))
        return result

    def restore(self, obj: Any, method_name: str) -> bool:
        """Reinstall the original method for one patched entry."""
        cls = type(obj)
        for i, (c, m, original) in enumerate(self._patches):
            if c is cls and m == method_name:
                setattr(c, m, original)
                self._patches.pop(i)
                return True
        return False

    def restore_all(self) -> None:
        """Reinstall every patched method and clear tracked faults."""
        for cls, method_name, original in self._patches:
            setattr(cls, method_name, original)
        self._patches.clear()
        for obj, attr_name, original in self._clock_patches:
            setattr(obj, attr_name, original)
        self._clock_patches.clear()
        self._injector.clear_all_faults()

    # -- attribute patching (clock drift, etc.) ----------------------------
    def apply_clock_drift(self, obj: Any, drift_sec: float) -> None:
        """Skew ``obj._clock`` by ``drift_sec`` seconds (PolicyEngine clock)."""
        attr = "_clock"
        original = getattr(obj, attr)
        start = original()
        setattr(obj, attr, lambda: original() + drift_sec)
        self._clock_patches.append((obj, attr, original))

    # -- context manager ---------------------------------------------------
    @contextmanager
    def scope(self):
        """Inject faults within the block; restore everything on exit."""
        try:
            yield self
        finally:
            self.restore_all()


def fault_scope(injector: RuntimeFaultInjector):
    """Decorator/context helper: inject faults, run, then restore.

    Equivalent to ``injector.scope()``; provided for readability::

        with fault_scope(injector):
            injector.apply(...)
            ...
    """
    return injector.scope()


def inject_fault_behavior(fault_type: FaultType, params: dict[str, Any] | None = None) -> Callable[[FaultFn], FaultFn]:
    """Decorator that wraps a plain function with a fault behavior.

    Example::

        @inject_fault_behavior(FaultType.CPU_SPIKE, {"delay_sec": 0.1})
        def my_slow_fn(): ...
    """

    def decorator(fn: FaultFn) -> FaultFn:
        behavior = BEHAVIORS.get(fault_type, _passthrough)
        return _bound_behavior(fn, behavior, params or {})

    return decorator


def get_active_faults(injector: RuntimeFaultInjector) -> list[ChaosResult]:
    return injector._injector.get_active_faults()


def get_fault_stats(injector: RuntimeFaultInjector) -> dict[str, Any]:
    return injector._injector.get_fault_stats()
