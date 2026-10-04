"""Disaster recovery plans for apex-autopilot-optimization.

Defines tiered DR plans (RTO/RPO targets, backup schedules, recovery
procedures) and validation logic for user-supplied plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DRPlan:
    """Disaster recovery plan for a service tier.

    Attributes:
        rto_seconds: Recovery Time Objective — max acceptable downtime.
        rpo_seconds: Recovery Point Objective — max acceptable data loss window.
        backup_schedule: Human-readable backup cadence (e.g. "hourly").
        recovery_steps: Ordered recovery procedure steps.
    """

    rto_seconds: float
    rpo_seconds: float
    backup_schedule: str
    recovery_steps: list[str] = field(default_factory=list)


_TIERS: dict[str, DRPlan] = {
    "basic": DRPlan(
        rto_seconds=86400.0,  # 24 h
        rpo_seconds=86400.0,  # 24 h
        backup_schedule="daily",
        recovery_steps=[
            "Restore latest configuration backup from backup_dir.",
            "Restart autopilot modules in dependency order.",
            "Verify estimator convergence before resuming mission.",
        ],
    ),
    "standard": DRPlan(
        rto_seconds=3600.0,  # 1 h
        rpo_seconds=3600.0,  # 1 h
        backup_schedule="hourly",
        recovery_steps=[
            "Restore latest configuration and algorithm-state backups.",
            "Restart autopilot modules in dependency order.",
            "Re-run safety checks (CBF validation) before arming.",
            "Verify estimator convergence before resuming mission.",
        ],
    ),
    "critical": DRPlan(
        rto_seconds=60.0,  # 1 min
        rpo_seconds=300.0,  # 5 min
        backup_schedule="every-5-minutes",
        recovery_steps=[
            "Fail over to hot standby instance.",
            "Restore latest algorithm-state backup (EKF covariance, formation).",
            "Verify state checksums before control handover.",
            "Run full safety validation suite before arming.",
            "Resume mission from last verified checkpoint.",
        ],
    ),
}


def get_dr_plan(tier: str) -> DRPlan:
    """Return the predefined DR plan for a tier ("basic", "standard", "critical").

    Raises:
        ValueError: If the tier name is not recognized.
    """
    try:
        return _TIERS[tier.lower()]
    except KeyError:
        raise ValueError(
            f"unknown DR tier: {tier!r}; expected one of {sorted(_TIERS)}"
        ) from None


def validate_dr_plan(plan: DRPlan) -> bool:
    """Validate a DR plan.

    A plan is valid when RTO/RPO are positive, the backup schedule is
    non-empty, and at least one recovery step exists. RTO and RPO are
    independent objectives (downtime vs data loss), so no ordering between
    them is imposed.
    """
    if plan.rto_seconds <= 0 or plan.rpo_seconds <= 0:
        return False
    if not plan.backup_schedule.strip():
        return False
    if not plan.recovery_steps:
        return False
    return True
