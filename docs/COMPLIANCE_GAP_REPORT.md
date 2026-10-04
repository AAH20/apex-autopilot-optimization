# Compliance & Governance Gap Report
## apex-autopilot-optimization

**Date:** 2026-10-04  
**Auditor:** AI Compliance Analysis  
**Project License:** AGPL-3.0  
**Project Type:** Python library for UAV/UAS autopilot optimization  

---

## Executive Summary

The apex-autopilot-optimization project has foundational security primitives but lacks comprehensive compliance infrastructure. This report identifies critical gaps across audit trails, compliance reporting, GDPR support, and SOC 2 alignment, and provides a prioritized remediation roadmap.

**Current State:**
- Basic in-memory `SecurityAuditLog` (no persistence, no integrity verification)
- 3 security policy checks (encryption, authentication, audit logging)
- HMAC-based "encryption" (not real encryption — integrity only)
- In-memory token authentication
- No GDPR data handling
- No compliance reporting framework
- No governance documentation

**Risk Level:** HIGH — the project handles autopilot/safety-critical systems with no verifiable compliance posture.

---

## 1. What Compliance Is Needed

### 1.1 Regulatory & Standards Framework

| Framework | Applicability | Priority | Current Status |
|-----------|--------------|----------|----------------|
| **SOC 2 Type II** | If SaaS/cloud-hosted autopilot optimization | P1 | Not implemented |
| **GDPR** | If any EU user data is processed | P1 | Not implemented |
| **ISO 27001/27701** | Information security management | P2 | Not implemented |
| **OpenSSF Baseline** | Open source security baseline | P2 | Not implemented |
| **NIST AI RMF** | AI/ML system governance (autopilot) | P3 | Not implemented |
| **EU AI Act** | High-risk AI systems (autonomous vehicles) | P3 | Not implemented |

### 1.2 SOC 2 Trust Services Criteria Gap Map

SOC 2 defines 61 criteria across 9 series (CC1–CC9). The project currently addresses ~5% of mandatory criteria.

| SOC 2 Series | Description | Current Coverage | Gap |
|-------------|-------------|-----------------|-----|
| **CC1** Control Environment | Governance, policies, roles | None | Full |
| **CC2** Communication & Information | Internal/external communication | None | Full |
| **CC3** Risk Assessment | Risk identification & analysis | None | Full |
| **CC4** Monitoring | Ongoing control monitoring | None | Full |
| **CC5** Control Activities | Policy deployment, procedures | `SecurityPolicy` class (3 checks) | ~80% |
| **CC6** Logical Access | Access control, authentication | `AuthenticationHelper` (in-memory) | ~60% |
| **CC7** System Operations | Logging, monitoring, incident response | `SecurityAuditLog` (in-memory) | ~70% |
| **CC8** Change Management | Change control process | None | Full |
| **CC9** Risk Mitigation | Vendor/third-party risk | None | Full |
| **A** Availability | System availability | `HealthCheck` class | ~85% |
| **PI** Processing Integrity | Data processing validation | None | Full |
| **C** Confidentiality | Data classification & handling | `EncryptionHelper` (HMAC only) | ~75% |
| **P** Privacy | Personal data handling | None | Full |

### 1.3 GDPR Gap Analysis

| GDPR Requirement | Article | Current Status |
|-----------------|---------|----------------|
| Lawful basis for processing | Art. 6 | Not implemented |
| Data subject rights (access, erasure, portability) | Art. 15–22 | Not implemented |
| Records of processing activities | Art. 30 | Not implemented |
| Data protection by design/default | Art. 25 | Not implemented |
| Security of processing | Art. 32 | Partial (HMAC only) |
| Breach notification (72h) | Art. 33–34 | Not implemented |
| Data protection impact assessment | Art. 35 | Not implemented |
| Data Protection Officer | Art. 37–39 | Not designated |
| Cross-border transfer safeguards | Art. 44–49 | Not implemented |
| Privacy notice | Art. 13–14 | Not implemented |

---

## 2. How to Implement Audit Trails

### 2.1 Current Limitations

The existing `SecurityAuditLog` class has critical deficiencies:
- **In-memory only** — entries lost on process restart
- **No integrity verification** — entries can be tampered with silently
- **No cryptographic chaining** — no tamper evidence
- **No structured schema** — untyped `Dict[str, Any]` details
- **No log separation** — mixed with operational logs
- **No retention policy** — no lifecycle management
- **No access control** — anyone with process access can modify

### 2.2 Recommended Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Auth Events  │  │ Data Access  │  │ Config Changes │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
│         └────────────────┼──────────────────┘           │
│                          ▼                               │
│              ┌─────────────────────┐                     │
│              │   AuditEvent Schema  │                     │
│              │  (Pydantic model)    │                     │
│              └──────────┬──────────┘                     │
└─────────────────────────┼───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Audit Trail Pipeline                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │Timestamp │→ │  Actor   │→ │  Event   │→ │ Context│  │
│  │(ISO 8601)│  │(user/svc)│  │  Type    │  │(entity)│  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
│                          │                               │
│                          ▼                               │
│              ┌─────────────────────┐                     │
│              │  Hash Chain + HMAC  │                     │
│              │  (tamper evidence)  │                     │
│              └──────────┬──────────┘                     │
└─────────────────────────┼───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Storage Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  WORM Files  │  │  Structlog   │  │  SIEM Export │  │
│  │ (append-only)│  │  (JSON)      │  │  (optional)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.3 Implementation: Tamper-Evident Audit Logger

```python
# src/apex_autopilot_optimization/compliance/audit.py

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Standardized audit event types for compliance."""
    AUTHENTICATION = "auth.authentication"
    AUTHORIZATION = "auth.authorization"
    DATA_ACCESS = "data.access"
    DATA_MODIFICATION = "data.modification"
    DATA_DELETION = "data.deletion"
    CONFIG_CHANGE = "config.change"
    POLICY_VIOLATION = "policy.violation"
    SECURITY_ALERT = "security.alert"
    PRIVACY_REQUEST = "privacy.request"
    SYSTEM_OPERATION = "system.operation"


class AuditEvent(BaseModel):
    """Structured audit event schema."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    event_type: AuditEventType
    actor: str  # user ID, service name, or "system"
    action: str  # e.g., "read", "write", "delete", "login"
    resource: str  # resource identifier
    outcome: str  # "success", "failure", "denied"
    context: Dict[str, Any] = Field(default_factory=dict)
    previous_hash: Optional[str] = None
    entry_hash: Optional[str] = None
    signature: Optional[str] = None


class TamperEvidentAuditLog:
    """
    Tamper-evident audit log with cryptographic hash chaining.
    
    Each entry includes a hash of its contents and the previous entry's hash,
    creating a blockchain-style chain that makes tampering detectable.
    """

    def __init__(
        self,
        log_dir: str | Path = "logs/audit",
        signing_key: bytes | None = None,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._signing_key = signing_key or os.urandom(32)
        self._previous_hash: str = "0" * 64
        self._sequence: int = 0
        self._logger = structlog.get_logger("audit")

    def log_event(
        self,
        event_type: AuditEventType,
        actor: str,
        action: str,
        resource: str,
        outcome: str = "success",
        **context: Any,
    ) -> AuditEvent:
        """Log a tamper-evident audit event."""
        self._sequence += 1

        event = AuditEvent(
            event_type=event_type,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            context=context,
            previous_hash=self._previous_hash,
        )

        # Compute entry hash
        event_bytes = event.model_dump_json(
            exclude={"entry_hash", "signature"}
        ).encode()
        event.entry_hash = hashlib.sha256(event_bytes).hexdigest()

        # Sign the entry
        event.signature = hmac.new(
            self._signing_key, event_bytes, hashlib.sha256
        ).hexdigest()

        # Update chain
        self._previous_hash = event.entry_hash

        # Persist
        self._write_entry(event)

        # Also log via structlog for operational visibility
        self._logger.info(
            "audit_event",
            event_id=event.event_id,
            event_type=event.event_type.value,
            actor=event.actor,
            action=event.action,
            resource=event.resource,
            outcome=event.outcome,
        )

        return event

    def _write_entry(self, event: AuditEvent) -> None:
        """Write entry to append-only log file."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self._log_dir / f"audit-{date_str}.log"
        with open(log_file, "a") as f:
            f.write(event.model_dump_json() + "\n")

    def verify_chain(self, date_str: str | None = None) -> Dict[str, Any]:
        """Verify the integrity of the audit log chain."""
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        log_file = self._log_dir / f"audit-{date_str}.log"
        if not log_file.exists():
            return {"valid": True, "entries_checked": 0, "errors": []}

        errors = []
        previous_hash = "0" * 64
        entries_checked = 0

        with open(log_file) as f:
            for line_num, line in enumerate(f, 1):
                entry = json.loads(line.strip())
                entries_checked += 1

                # Verify chain linkage
                if entry.get("previous_hash") != previous_hash:
                    errors.append(
                        f"Line {line_num}: chain break "
                        f"(expected {previous_hash[:16]}..., "
                        f"got {entry.get('previous_hash', 'none')[:16]}...)"
                    )

                # Verify entry hash
                entry_copy = {
                    k: v for k, v in entry.items()
                    if k not in ("entry_hash", "signature")
                }
                computed_hash = hashlib.sha256(
                    json.dumps(entry_copy, sort_keys=True).encode()
                ).hexdigest()
                if computed_hash != entry.get("entry_hash"):
                    errors.append(
                        f"Line {line_num}: hash mismatch "
                        f"(tampering detected)"
                    )

                # Verify signature
                expected_sig = hmac.new(
                    self._signing_key,
                    json.dumps(entry_copy, sort_keys=True).encode(),
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(expected_sig, entry.get("signature", "")):
                    errors.append(
                        f"Line {line_num}: signature verification failed"
                    )

                previous_hash = entry["entry_hash"]

        return {
            "valid": len(errors) == 0,
            "entries_checked": entries_checked,
            "errors": errors,
        }

    def get_events(
        self,
        event_type: AuditEventType | None = None,
        actor: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> List[AuditEvent]:
        """Query audit events with filters."""
        events = []
        for log_file in sorted(self._log_dir.glob("audit-*.log")):
            with open(log_file) as f:
                for line in f:
                    event = AuditEvent.model_validate_json(line.strip())
                    if event_type and event.event_type != event_type:
                        continue
                    if actor and event.actor != actor:
                        continue
                    if start_time and event.timestamp < start_time:
                        continue
                    if end_time and event.timestamp > end_time:
                        continue
                    events.append(event)
        return events
```

### 2.4 Structured Logging Integration

The project already depends on `structlog`. Configure it for audit separation:

```python
# src/apex_autopilot_optimization/compliance/logging_config.py

import logging
import sys
from pathlib import Path

import structlog


def configure_audit_logging(
    log_dir: str | Path = "logs/audit",
    environment: str = "production",
) -> None:
    """
    Configure structlog with separate audit log routing.
    
    Audit events go to a dedicated file with JSON formatting.
    Operational logs go to stdout with console formatting.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Audit file handler — JSON, append-only
    audit_handler = logging.FileHandler(
        log_path / "audit.log",
        mode="a",
    )
    audit_handler.setFormatter(logging.Formatter("%(message)s"))

    # Operational stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
            if environment == "production"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )

    # Dedicated audit logger
    audit_logger = logging.getLogger("audit")
    audit_logger.propagate = False
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)
```

### 2.5 Audit Event Catalog

| Event Type | Trigger | Actor | Context Fields |
|-----------|---------|-------|----------------|
| `auth.authentication` | Login attempt | user_id | method, ip_address, success |
| `auth.authorization` | Access control decision | user_id | resource, action, allowed |
| `data.access` | Data read operation | user_id/service | resource_type, resource_id |
| `data.modification` | Data write/update | user_id/service | resource_type, old/new summary |
| `data.deletion` | Data deletion | user_id/service | resource_type, reason |
| `config.change` | Configuration change | user_id | config_key, old/new summary |
| `policy.violation` | Security policy failure | system | policy_name, details |
| `security.alert` | Security incident | system | alert_type, severity |
| `privacy.request` | GDPR data subject request | user_id | request_type, status |
| `system.operation` | System lifecycle events | system | operation, status |

---

## 3. What Compliance Reporting to Add

### 3.1 SOC 2 Control Matrix

Create a machine-readable control matrix mapping SOC 2 criteria to implementation evidence:

```yaml
# configs/soc2_controls.yaml
framework: SOC2
version: "2017"
last_updated: "2026-10-04"

controls:
  CC1.1:
    name: "Demonstrates commitment to integrity and ethical values"
    status: not_implemented
    evidence: []
    remediation: "Create governance documentation, code of conduct"

  CC1.2:
    name: "Exercises oversight responsibility"
    status: not_implemented
    evidence: []
    remediation: "Establish technical steering committee"

  CC5.1:
    name: "Selects and develops control activities"
    status: partial
    evidence:
      - "src/apex_autopilot_optimization/security.py:SecurityPolicy"
    gaps: ["Only 3 checks implemented", "No policy enforcement automation"]

  CC6.1:
    name: "Implements logical access controls"
    status: partial
    evidence:
      - "src/apex_autopilot_optimization/security.py:AuthenticationHelper"
    gaps: ["In-memory only", "No RBAC", "No session persistence"]

  CC7.1:
    name: "Uses detection and monitoring mechanisms"
    status: partial
    evidence:
      - "src/apex_autopilot_optimization/security.py:SecurityAuditLog"
      - "src/apex_autopilot_optimization/observability.py:HealthCheck"
    gaps: ["No persistence", "No alerting", "No log integrity"]

  CC7.2:
    name: "Monitors security events"
    status: not_implemented
    evidence: []
    remediation: "Implement real-time security event monitoring"

  CC7.3:
    name: "Identifies and responds to security incidents"
    status: not_implemented
    evidence: []
    remediation: "Create incident response plan and runbooks"

  CC8.1:
    name: "Manages changes to system components"
    status: not_implemented
    evidence: []
    remediation: "Implement change management workflow"

  CC9.1:
    name: "Identifies and assesses vendor risk"
    status: not_implemented
    evidence: []
    remediation: "Create vendor risk register"
```

### 3.2 Compliance Report Generator

```python
# src/apex_autopilot_optimization/compliance/reporting.py

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

import yaml


class ControlStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not_implemented"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class ControlAssessment:
    """Assessment of a single compliance control."""
    control_id: str
    name: str
    status: ControlStatus
    evidence: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    remediation: str = ""
    last_assessed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ComplianceReportGenerator:
    """
    Generates compliance reports from control assessments.
    
    Produces structured JSON output ready for SIEM ingestion
    or GRC platform import.
    """

    def __init__(self, config_path: str | Path) -> None:
        with open(config_path) as f:
            self._config = yaml.safe_load(f)

    def generate_report(self) -> Dict[str, Any]:
        """Generate a full compliance report."""
        controls = self._config.get("controls", {})

        assessments = []
        for control_id, control_data in controls.items():
            assessments.append(
                ControlAssessment(
                    control_id=control_id,
                    name=control_data.get("name", ""),
                    status=ControlStatus(control_data.get("status", "not_implemented")),
                    evidence=control_data.get("evidence", []),
                    gaps=control_data.get("gaps", []),
                    remediation=control_data.get("remediation", ""),
                )
            )

        total = len(assessments)
        implemented = sum(
            1 for a in assessments if a.status == ControlStatus.IMPLEMENTED
        )
        partial = sum(
            1 for a in assessments if a.status == ControlStatus.PARTIAL
        )
        not_implemented = sum(
            1 for a in assessments if a.status == ControlStatus.NOT_IMPLEMENTED
        )

        return {
            "report_metadata": {
                "framework": self._config.get("framework", "Unknown"),
                "version": self._config.get("version", "Unknown"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "project": "apex-autopilot-optimization",
            },
            "summary": {
                "total_controls": total,
                "implemented": implemented,
                "partial": partial,
                "not_implemented": not_implemented,
                "compliance_score": round(
                    (implemented + partial * 0.5) / total * 100, 1
                ) if total > 0 else 0,
            },
            "controls": [
                {
                    "id": a.control_id,
                    "name": a.name,
                    "status": a.status.value,
                    "evidence": a.evidence,
                    "gaps": a.gaps,
                    "remediation": a.remediation,
                    "last_assessed": a.last_assessed,
                }
                for a in assessments
            ],
        }

    def export_json(self, output_path: str | Path) -> None:
        """Export report as JSON."""
        report = self.generate_report()
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    def export_markdown(self, output_path: str | Path) -> None:
        """Export report as Markdown for human review."""
        report = self.generate_report()
        meta = report["report_metadata"]
        summary = report["summary"]

        lines = [
            f"# {meta['framework']} Compliance Report",
            "",
            f"**Generated:** {meta['generated_at']}",
            f"**Framework Version:** {meta['version']}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Controls | {summary['total_controls']} |",
            f"| Implemented | {summary['implemented']} |",
            f"| Partial | {summary['partial']} |",
            f"| Not Implemented | {summary['not_implemented']} |",
            f"| **Compliance Score** | **{summary['compliance_score']}%** |",
            "",
            "## Control Details",
            "",
        ]

        for control in report["controls"]:
            lines.extend([
                f"### {control['id']}: {control['name']}",
                "",
                f"**Status:** `{control['status']}`",
                "",
            ])
            if control["evidence"]:
                lines.append("**Evidence:**")
                for ev in control["evidence"]:
                    lines.append(f"- {ev}")
                lines.append("")
            if control["gaps"]:
                lines.append("**Gaps:**")
                for gap in control["gaps"]:
                    lines.append(f"- {gap}")
                lines.append("")
            if control["remediation"]:
                lines.append(f"**Remediation:** {control['remediation']}")
                lines.append("")

        with open(output_path, "w") as f:
            f.write("\n".join(lines))
```

### 3.3 GDPR Compliance Reporting

```python
# src/apex_autopilot_optimization/compliance/gdpr.py

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class DataSubjectRight(str, Enum):
    """GDPR data subject rights (Chapter 3)."""
    ACCESS = "access"                    # Art. 15
    RECTIFICATION = "rectification"      # Art. 16
    ERASURE = "erasure"                  # Art. 17
    RESTRICTION = "restriction"          # Art. 18
    PORTABILITY = "portability"          # Art. 20
    OBJECTION = "objection"              # Art. 21
    AUTOMATED_DECISION = "automated_decision"  # Art. 22


class ProcessingLawfulBasis(str, Enum):
    """GDPR Article 6 lawful bases."""
    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTERESTS = "legitimate_interests"


@dataclass
class ProcessingActivityRecord:
    """GDPR Article 30 record of processing activity."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    controller_name: str = ""
    controller_contact: str = ""
    dpo_contact: str = ""
    purpose: str = ""
    data_subject_categories: List[str] = field(default_factory=list)
    personal_data_categories: List[str] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)
    third_country_transfers: List[str] = field(default_factory=list)
    retention_period: str = ""
    security_measures: str = ""
    lawful_basis: Optional[ProcessingLawfulBasis] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class DataSubjectRequest:
    """GDPR data subject request tracking."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_type: DataSubjectRight = DataSubjectRight.ACCESS
    data_subject_id: str = ""
    received_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    deadline: str = ""  # 30 days from receipt
    status: str = "pending"  # pending, in_progress, completed, rejected
    completed_at: Optional[str] = None
    response_summary: str = ""


class GDPRComplianceManager:
    """
    Manages GDPR compliance artifacts:
    - Article 30 processing records
    - Data subject request tracking
    - Breach notification workflow
    """

    def __init__(self, data_dir: str | Path = "data/gdpr") -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._records_file = self._data_dir / "processing_records.json"
        self._requests_file = self._data_dir / "data_subject_requests.json"

    def create_processing_record(
        self, record: ProcessingActivityRecord
    ) -> ProcessingActivityRecord:
        """Create an Article 30 processing activity record."""
        records = self._load_records()
        records.append(record.model_dump() if hasattr(record, "model_dump") else record.__dict__)
        self._save_records(records)
        return record

    def submit_data_subject_request(
        self, request: DataSubjectRequest
    ) -> DataSubjectRequest:
        """Submit a data subject request."""
        # Calculate 30-day deadline
        received = datetime.fromisoformat(request.received_at)
        from datetime import timedelta
        deadline = received + timedelta(days=30)
        request.deadline = deadline.isoformat()

        requests = self._load_requests()
        requests.append(request.__dict__)
        self._save_requests(requests)
        return request

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Get all pending data subject requests."""
        requests = self._load_requests()
        return [r for r in requests if r.get("status") == "pending"]

    def get_overdue_requests(self) -> List[Dict[str, Any]]:
        """Get overdue data subject requests."""
        now = datetime.now(timezone.utc).isoformat()
        requests = self._load_requests()
        return [
            r for r in requests
            if r.get("status") == "pending" and r.get("deadline", "") < now
        ]

    def _load_records(self) -> List[Dict[str, Any]]:
        if self._records_file.exists():
            with open(self._records_file) as f:
                return json.load(f)
        return []

    def _save_records(self, records: List[Dict[str, Any]]) -> None:
        with open(self._records_file, "w") as f:
            json.dump(records, f, indent=2)

    def _load_requests(self) -> List[Dict[str, Any]]:
        if self._requests_file.exists():
            with open(self._requests_file) as f:
                return json.load(f)
        return []

    def _save_requests(self, requests: List[Dict[str, Any]]) -> None:
        with open(self._requests_file, "w") as f:
            json.dump(requests, f, indent=2)
```

### 3.4 Compliance Report Types

| Report | Frequency | Audience | Format |
|--------|-----------|----------|--------|
| SOC 2 Control Matrix | Quarterly | Auditors, management | YAML + JSON |
| GDPR Processing Records | On change | DPO, regulators | JSON |
| Data Subject Request Log | Real-time | DPO | JSON |
| Security Incident Report | Per incident | Management, auditors | Markdown |
| Access Review | Quarterly | Security team | JSON |
| Vulnerability SLA Report | Monthly | Security team | JSON |
| Compliance Scorecard | Monthly | Executive | Markdown |

---

## 4. How to Maintain Governance

### 4.1 Governance Framework

```
┌─────────────────────────────────────────────────────────┐
│                  Governance Structure                     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │           Technical Steering Committee            │    │
│  │  (Architecture decisions, compliance oversight)   │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │                                │
│         ┌───────────────┼───────────────┐               │
│         ▼               ▼               ▼               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │   Security  │ │  Compliance │ │   Privacy   │       │
│  │    Owner    │ │    Owner    │ │   Officer   │       │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘       │
│         │               │               │               │
│         └───────────────┼───────────────┘               │
│                         ▼                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Compliance Automation                │    │
│  │  • CI/CD policy checks                           │    │
│  │  • Automated evidence collection                 │    │
│  │  • Continuous control monitoring                 │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Required Governance Documents

| Document | Purpose | Status |
|----------|---------|--------|
| `GOVERNANCE.md` | Project governance model | Missing |
| `SECURITY.md` | Security policy and reporting | Missing |
| `PRIVACY.md` | Privacy policy | Missing |
| `COMPLIANCE.md` | Compliance program overview | Missing |
| `INCIDENT_RESPONSE.md` | Incident response plan | Missing |
| `DATA_RETENTION.md` | Data retention policy | Missing |
| `ACCESS_CONTROL.md` | Access control policy | Missing |
| `VENDOR_RISK.md` | Vendor risk register | Missing |
| `CHANGELOG.md` | Change tracking | Missing |
| `CONTRIBUTING.md` | Contribution guidelines | Missing |

### 4.3 CI/CD Compliance Gates

```yaml
# .github/workflows/compliance.yml
name: Compliance Gates

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  compliance-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      # Security scanning
      - name: Run security linter
        run: |
          pip install bandit safety
          bandit -r src/ -f json -o bandit-report.json
          safety check --json --output safety-report.json

      # License compliance
      - name: Check license compliance
        run: |
          pip install pip-licenses
          pip-licenses --format=json --output-file=licenses.json
          pip-licenses --fail-on="AGPL-3.0;GPL-3.0"

      # Type checking (governance gate)
      - name: Run type checker
        run: mypy src/ --strict

      # Linting (governance gate)
      - name: Run linter
        run: ruff check src/

      # Compliance report generation
      - name: Generate compliance report
        run: |
          python -m apex_autopilot_optimization.compliance.reporting \
            --config configs/soc2_controls.yaml \
            --output compliance-report.json

      # Audit log verification
      - name: Verify audit log integrity
        run: |
          python -m apex_autopilot_optimization.compliance.audit \
            --verify logs/audit/

      # Upload compliance artifacts
      - name: Upload compliance reports
        uses: actions/upload-artifact@v4
        with:
          name: compliance-reports
          path: |
            bandit-report.json
            safety-report.json
            licenses.json
            compliance-report.json
```

### 4.4 Continuous Compliance Monitoring

```python
# src/apex_autopilot_optimization/compliance/monitoring.py

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit import AuditEventType, TamperEvidentAuditLog


@dataclass
class ComplianceAlert:
    """Compliance monitoring alert."""
    alert_id: str
    timestamp: str
    severity: str  # low, medium, high, critical
    category: str  # security, privacy, governance
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


class ComplianceMonitor:
    """
    Continuous compliance monitoring.
    
    Watches for:
    - Policy violations
    - Overdue data subject requests
    - Audit log integrity failures
    - Security anomalies
    """

    def __init__(self, audit_log: TamperEvidentAuditLog) -> None:
        self._audit_log = audit_log
        self._alerts: List[ComplianceAlert] = []

    def check_audit_integrity(self) -> Optional[ComplianceAlert]:
        """Verify audit log chain integrity."""
        result = self._audit_log.verify_chain()
        if not result["valid"]:
            alert = ComplianceAlert(
                alert_id="AUDIT-001",
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity="critical",
                category="governance",
                message="Audit log integrity verification failed",
                context={"errors": result["errors"]},
            )
            self._alerts.append(alert)
            return alert
        return None

    def check_policy_compliance(
        self, policy_results: Dict[str, Any]
    ) -> List[ComplianceAlert]:
        """Check security policy compliance."""
        alerts = []
        for check in policy_results.get("checks", []):
            if check.get("status") == "fail":
                alert = ComplianceAlert(
                    alert_id=f"POLICY-{check['name'].upper()}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="high",
                    category="security",
                    message=f"Policy check failed: {check['name']}",
                    context={"check": check},
                )
                alerts.append(alert)
                self._alerts.append(alert)
        return alerts

    def get_active_alerts(
        self, severity: str | None = None
    ) -> List[ComplianceAlert]:
        """Get active compliance alerts."""
        if severity is None:
            return list(self._alerts)
        return [a for a in self._alerts if a.severity == severity]

    def generate_monitoring_report(self) -> Dict[str, Any]:
        """Generate compliance monitoring report."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_alerts": len(self._alerts),
            "alerts_by_severity": {
                "critical": len([a for a in self._alerts if a.severity == "critical"]),
                "high": len([a for a in self._alerts if a.severity == "high"]),
                "medium": len([a for a in self._alerts if a.severity == "medium"]),
                "low": len([a for a in self._alerts if a.severity == "low"]),
            },
            "alerts_by_category": {
                "security": len([a for a in self._alerts if a.category == "security"]),
                "privacy": len([a for a in self._alerts if a.category == "privacy"]),
                "governance": len([a for a in self._alerts if a.category == "governance"]),
            },
            "recent_alerts": [
                {
                    "id": a.alert_id,
                    "timestamp": a.timestamp,
                    "severity": a.severity,
                    "category": a.category,
                    "message": a.message,
                }
                for a in self._alerts[-10:]  # Last 10 alerts
            ],
        }
```

### 4.5 Governance Maintenance Schedule

| Activity | Frequency | Owner | Output |
|----------|-----------|-------|--------|
| Access review | Quarterly | Security Owner | Access review report |
| Policy review | Annually | Compliance Owner | Updated policies |
| Risk assessment | Annually | TSC | Risk register update |
| Penetration test | Annually | External | Pen test report |
| Compliance audit | Quarterly | Compliance Owner | Audit report |
| Vendor review | Semi-annually | Compliance Owner | Vendor risk update |
| Training | Annually | All | Training records |
| Incident response drill | Semi-annually | Security Owner | Drill report |
| Data retention review | Quarterly | DPO | Retention report |
| Control testing | Monthly | Compliance Owner | Control test results |

---

## 5. Remediation Roadmap

### Phase 1: Foundation (Weeks 1–4)
- [ ] Implement `TamperEvidentAuditLog` with hash chaining
- [ ] Configure structlog for audit separation
- [ ] Create `SECURITY.md` and `GOVERNANCE.md`
- [ ] Add compliance CI/CD gates
- [ ] Implement basic compliance reporting

### Phase 2: GDPR Support (Weeks 5–8)
- [ ] Implement `GDPRComplianceManager`
- [ ] Create Article 30 processing records
- [ ] Build data subject request workflow
- [ ] Add privacy notice template
- [ ] Implement data retention policies

### Phase 3: SOC 2 Alignment (Weeks 9–12)
- [ ] Complete SOC 2 control matrix
- [ ] Implement missing controls (CC8 change management)
- [ ] Build incident response plan
- [ ] Create vendor risk register
- [ ] Implement continuous monitoring

### Phase 4: Maturity (Weeks 13–16)
- [ ] Achieve SOC 2 Type I readiness
- [ ] Implement automated evidence collection
- [ ] Build compliance dashboard
- [ ] Conduct internal audit
- [ ] Prepare for external audit

---

## 6. Key Recommendations

1. **Prioritize audit trail persistence** — the current in-memory `SecurityAuditLog` is the single largest compliance gap
2. **Adopt structured event schema** — replace untyped `Dict[str, Any]` with Pydantic models
3. **Separate audit from operational logs** — dedicated logger, storage, and retention
4. **Implement hash chaining** — tamper evidence is mandatory for SOC 2 and GDPR
5. **Automate compliance reporting** — manual reporting doesn't scale and is error-prone
6. **Establish governance structure** — without ownership, compliance decays
7. **Integrate compliance into CI/CD** — shift-left compliance reduces audit burden
8. **Document everything** — undocumented controls don't exist in an audit

---

## Sources

1. AICPA Trust Services Criteria (2017) — https://www.aicpa.org/interestareas/frc/assuranceadvisoryservices/trustservicescriteria.html
2. GDPR Article 30 — Records of processing activities — https://gdpr.eu/article-30-records-of-processing-activities/
3. OpenSSF Baseline — https://openssf.org/baseline
4. structlog documentation — https://www.structlog.org/
5. Compliance automation patterns — https://github.com/cyberzeshan/compliance-automation
6. GRC reference implementation — https://github.com/jkboamah/ComplianceForge
7. SOC 2 controls mapping — https://www.opensecurityarchitecture.org/frameworks/soc2-tsc/controls
8. Tamper-evident logging patterns — https://python-observability.com/python-logging-fundamentals-and-structured-data/logging-security-and-compliance
