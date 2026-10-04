"""Configuration for the ethics and fairness subsystem."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EthicsConfig:
    """Settings controlling ethics policy enforcement and auditing.

    Attributes:
        enabled: Master switch for ethics evaluation.
        auto_review: Whether actions are automatically submitted for review.
        bias_threshold: Maximum acceptable disparity before bias is flagged.
        fairness_threshold: Minimum acceptable fairness score (0..1).
        require_human_approval: Whether a human must approve flagged actions.
    """

    enabled: bool = True
    auto_review: bool = True
    bias_threshold: float = 0.1
    fairness_threshold: float = 0.8
    require_human_approval: bool = True
