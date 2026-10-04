"""Fault injector for chaos engineering."""

from __future__ import annotations

import random
import time
from typing import Any

from apex_autopilot_optimization.chaos.config import ChaosConfig
from apex_autopilot_optimization.chaos.faults import FaultType
from apex_autopilot_optimization.chaos.result import ChaosResult


class FaultInjector:
    """Injects and manages faults for chaos engineering experiments.

    This class provides a controlled way to inject various types of faults
    into the system to test resilience and error handling.
    """

    def __init__(self, config: ChaosConfig | None = None) -> None:
        self.config = config or ChaosConfig()
        self._active_faults: dict[tuple[str, str], ChaosResult] = {}
        self._fault_history: list[ChaosResult] = []

    def inject_fault(
        self,
        fault_type: FaultType,
        target: str,
        params: dict[str, Any] | None = None,
    ) -> ChaosResult | None:
        """Inject a fault into the target module.

        Args:
            fault_type: The type of fault to inject.
            target: The target module or component name.
            params: Optional parameters for the fault.

        Returns:
            ChaosResult if the fault was injected, None if rejected.
        """
        key = (fault_type.name, target)

        # Reject if already active
        if key in self._active_faults:
            return None

        # Reject if at max concurrent faults
        if len(self._active_faults) >= self.config.max_concurrent_faults:
            return None

        result = ChaosResult(
            fault_type=fault_type.name,
            target=target,
            start_time=time.time(),
            end_time=None,
            params=params or {},
            status="active",
        )

        self._active_faults[key] = result
        self._fault_history.append(result)
        return result

    def remove_fault(self, fault_type: FaultType, target: str) -> bool:
        """Remove a previously injected fault.

        Args:
            fault_type: The type of fault to remove.
            target: The target module or component name.

        Returns:
            True if the fault was found and removed, False otherwise.
        """
        key = (fault_type.name, target)
        if key not in self._active_faults:
            return False

        result = self._active_faults.pop(key)
        result.end_time = time.time()
        result.status = "completed"
        return True

    def get_active_faults(self) -> list[ChaosResult]:
        """Return a list of all currently active faults."""
        return list(self._active_faults.values())

    def clear_all_faults(self) -> int:
        """Remove all active faults.

        Returns:
            The number of faults that were cleared.
        """
        count = len(self._active_faults)
        now = time.time()
        for result in self._active_faults.values():
            result.end_time = now
            result.status = "completed"
        self._active_faults.clear()
        return count

    def inject_random_fault(
        self,
        target: str | None = None,
        seed: int | None = None,
    ) -> ChaosResult | None:
        """Inject a random fault based on the configured probability.

        Args:
            target: Optional target module. If None, a random target is chosen.
            seed: Optional random seed for reproducibility.

        Returns:
            ChaosResult if a fault was injected, None if probability check failed.
        """
        if not self.config.enabled:
            return None

        rng = random.Random(seed)

        if rng.random() > self.config.fault_probability:
            return None

        fault_type = rng.choice(list(FaultType))

        if target is None:
            if self.config.target_modules:
                target = rng.choice(self.config.target_modules)
            else:
                target = f"module_{rng.randint(1, 10)}"

        return self.inject_fault(fault_type, target)

    def get_fault_stats(self) -> dict[str, Any]:
        """Return statistics about active and historical faults.

        Returns:
            Dictionary with total_active count and by_type breakdown.
        """
        by_type: dict[str, int] = {}
        for result in self._active_faults.values():
            by_type[result.fault_type] = by_type.get(result.fault_type, 0) + 1

        return {
            "total_active": len(self._active_faults),
            "total_history": len(self._fault_history),
            "by_type": by_type,
        }
