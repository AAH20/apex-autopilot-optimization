"""FMEA (Failure Mode and Effects Analysis) entries."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FMEARiskLevel(str, Enum):
    """Risk levels derived from FMEA risk priority numbers."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class FMEAEntry:
    """A single FMEA analysis entry."""

    id: str
    component: str
    failure_mode: str
    effect: str
    cause: str
    severity: int
    occurrence: int
    detection: int
    rpn: int = 0

    def calculate_rpn(self) -> int:
        """Compute the Risk Priority Number: severity * occurrence * detection."""
        return self.severity * self.occurrence * self.detection

    def get_risk_level(self) -> FMEARiskLevel:
        """Classify the entry's RPN into a risk level."""
        rpn = self.rpn if self.rpn else self.calculate_rpn()
        if rpn < 100:
            return FMEARiskLevel.LOW
        if rpn < 200:
            return FMEARiskLevel.MEDIUM
        if rpn < 500:
            return FMEARiskLevel.HIGH
        return FMEARiskLevel.CRITICAL
