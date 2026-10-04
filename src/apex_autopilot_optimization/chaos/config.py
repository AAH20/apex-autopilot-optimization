"""Configuration for chaos engineering and fault injection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChaosConfig:
    """Configuration for chaos engineering experiments.

    Attributes:
        enabled: Whether chaos engineering is active.
        fault_probability: Probability of a random fault being injected (0.0-1.0).
        max_concurrent_faults: Maximum number of simultaneous active faults.
        target_modules: List of module names eligible for fault injection.
    """

    enabled: bool = True
    fault_probability: float = 0.1
    max_concurrent_faults: int = 3
    target_modules: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= self.fault_probability <= 1.0:
            raise ValueError(
                f"fault_probability must be between 0.0 and 1.0, got {self.fault_probability}"
            )
        if self.max_concurrent_faults < 1:
            raise ValueError(
                f"max_concurrent_faults must be >= 1, got {self.max_concurrent_faults}"
            )
