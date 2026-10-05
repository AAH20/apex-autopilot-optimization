"""Governance policies and compliance standards."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ComplianceStandard(Enum):
    """Supported compliance standards."""

    SOC2 = "SOC2"
    GDPR = "GDPR"
    ISO27001 = "ISO27001"
    NIST_AI_RMF = "NIST_AI_RMF"
    EU_AI_ACT = "EU_AI_ACT"


@dataclass
class GovernancePolicy:
    """A governance policy with rules and enforcement level."""

    name: str
    description: str
    rules: list[dict[str, Any]]
    enforcement: str


_STANDARD_REQUIREMENTS: dict[ComplianceStandard, list[dict[str, Any]]] = {
    ComplianceStandard.SOC2: [
        {
            "id": "SOC2-CC6.1",
            "name": "Logical Access Control",
            "description": "Enforce least-privilege access",
        },
        {
            "id": "SOC2-CC6.2",
            "name": "Access Provisioning",
            "description": "Provision access based on authorization",
        },
        {
            "id": "SOC2-CC6.3",
            "name": "Access Deprovisioning",
            "description": "Remove access when no longer needed",
        },
        {
            "id": "SOC2-CC7.1",
            "name": "Security Monitoring",
            "description": "Monitor for security events",
        },
        {
            "id": "SOC2-CC7.2",
            "name": "Incident Response",
            "description": "Respond to security incidents",
        },
        {
            "id": "SOC2-CC8.1",
            "name": "Change Management",
            "description": "Manage changes to infrastructure",
        },
    ],
    ComplianceStandard.GDPR: [
        {
            "id": "GDPR-ART5",
            "name": "Data Minimization",
            "description": "Collect only necessary data",
        },
        {
            "id": "GDPR-ART6",
            "name": "Lawful Basis",
            "description": "Process data with lawful basis",
        },
        {
            "id": "GDPR-ART17",
            "name": "Right to Erasure",
            "description": "Support data deletion requests",
        },
        {
            "id": "GDPR-ART25",
            "name": "Privacy by Design",
            "description": "Build privacy into systems",
        },
        {
            "id": "GDPR-ART32",
            "name": "Security of Processing",
            "description": "Ensure data security",
        },
    ],
    ComplianceStandard.ISO27001: [
        {
            "id": "ISO-A.9.1",
            "name": "Access Control Policy",
            "description": "Document access control policy",
        },
        {
            "id": "ISO-A.9.2",
            "name": "User Access Management",
            "description": "Manage user access rights",
        },
        {"id": "ISO-A.12.3", "name": "Backup", "description": "Maintain data backups"},
        {
            "id": "ISO-A.12.4",
            "name": "Logging and Monitoring",
            "description": "Log and monitor events",
        },
        {
            "id": "ISO-A.16.1",
            "name": "Incident Management",
            "description": "Manage information security incidents",
        },
    ],
    ComplianceStandard.NIST_AI_RMF: [
        {"id": "NIST-MAP", "name": "Map", "description": "Identify AI system context and risks"},
        {
            "id": "NIST-MEASURE",
            "name": "Measure",
            "description": "Measure AI system performance and risks",
        },
        {"id": "NIST-MANAGE", "name": "Manage", "description": "Manage identified risks"},
        {"id": "NIST-GOVERN", "name": "Govern", "description": "Establish governance structures"},
    ],
    ComplianceStandard.EU_AI_ACT: [
        {
            "id": "EU-TIER1",
            "name": "Prohibited Practices",
            "description": "Comply with prohibited AI practices",
        },
        {
            "id": "EU-TIER2",
            "name": "High-Risk Obligations",
            "description": "Meet high-risk system requirements",
        },
        {"id": "EU-TIER3", "name": "Transparency", "description": "Ensure AI system transparency"},
        {
            "id": "EU-GPAI",
            "name": "General Purpose AI",
            "description": "Comply with GPAI model rules",
        },
    ],
}


def get_standard_requirements(standard: ComplianceStandard) -> list[dict[str, Any]]:
    """Get the requirements for a specific compliance standard."""
    return _STANDARD_REQUIREMENTS.get(standard, [])
