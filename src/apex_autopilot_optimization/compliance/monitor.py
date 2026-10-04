"""Compliance monitoring, violation detection, and scoring."""

from apex_autopilot_optimization.compliance.report import ComplianceReport, generate_report


class ComplianceMonitor:
    """Monitors compliance status, violations, and scores."""

    def __init__(self) -> None:
        self._reports: list[ComplianceReport] = []
        self._controls: dict[str, str] = {}

    def check_compliance(self, standard: str, controls: list[dict]) -> ComplianceReport:
        """Run a compliance check and store the report."""
        report = generate_report(standard, controls)
        self._reports.append(report)
        return report

    def get_violations(self) -> list[dict]:
        """Get all violations from the most recent report."""
        if not self._reports:
            return []
        latest = self._reports[-1]
        return [
            {
                "control_id": c["id"],
                "control_name": c["name"],
                "standard": latest.standard,
            }
            for c in latest.controls
            if c["status"] == "fail"
        ]

    def get_remediation_plan(self, violation: dict) -> dict:
        """Get a remediation plan for a violation."""
        if not self._reports:
            return {"control_id": violation["control_id"], "remediation": "No remediation available"}
        latest = self._reports[-1]
        for control in latest.controls:
            if control["id"] == violation["control_id"]:
                return {
                    "control_id": violation["control_id"],
                    "remediation": control.get("remediation", "No remediation defined"),
                }
        return {"control_id": violation["control_id"], "remediation": "No remediation available"}

    def track_control(self, control_id: str, status: str) -> None:
        """Track the status of a control."""
        self._controls[control_id] = status

    def get_compliance_score(self) -> float:
        """Get the compliance score as a percentage."""
        if not self._controls:
            return 0.0
        passed = sum(1 for s in self._controls.values() if s == "pass")
        return (passed / len(self._controls)) * 100.0
