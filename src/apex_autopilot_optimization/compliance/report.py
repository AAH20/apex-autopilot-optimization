"""Compliance report generation and control status tracking."""

import time
from dataclasses import dataclass, field


@dataclass
class ComplianceReport:
    """A compliance report for a specific standard."""

    standard: str
    controls: list[dict]
    timestamp: float
    status: str

    def get_control_status(self, control_id: str) -> str | None:
        """Get the status of a specific control."""
        for control in self.controls:
            if control["id"] == control_id:
                return control["status"]
        return None

    def get_remediation(self, control_id: str) -> str | None:
        """Get the remediation for a failed control."""
        for control in self.controls:
            if control["id"] == control_id:
                if control["status"] == "fail":
                    return control.get("remediation")
                return None
        return None


def generate_report(standard: str, controls: list[dict]) -> ComplianceReport:
    """Generate a compliance report from a list of controls."""
    all_pass = all(c["status"] == "pass" for c in controls)
    status = "compliant" if all_pass else "non_compliant"
    return ComplianceReport(
        standard=standard,
        controls=controls,
        timestamp=time.time(),
        status=status,
    )
