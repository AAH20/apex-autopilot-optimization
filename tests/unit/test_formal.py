"""Tests for formal verification package."""
from __future__ import annotations

import math

import pytest

from apex_autopilot_optimization.formal import (
    FMEAEntry,
    FMEARiskLevel,
    FaultTree,
    FormalConfig,
    SafetyCase,
    SafetyProperty,
    SafetySeverity,
)


class TestSafetyProperty:
    """Tests for SafetyProperty dataclass and verification."""

    def test_creation(self) -> None:
        prop = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        assert prop.id == "SP-001"
        assert prop.name == "Altitude Limit"
        assert prop.description == "Vehicle must stay below max altitude"
        assert prop.expression == "altitude < 500"
        assert prop.severity == "CRITICAL"

    def test_verify_property_passes(self) -> None:
        prop = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        state = {"altitude": 300.0}
        assert verify_property(prop, state) is True

    def test_verify_property_fails(self) -> None:
        prop = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        state = {"altitude": 600.0}
        assert verify_property(prop, state) is False

    def test_get_property_status(self) -> None:
        prop = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        status = get_property_status(prop)
        assert status == "UNVERIFIED"

    def test_safety_severity_enum(self) -> None:
        assert SafetySeverity.CRITICAL == "CRITICAL"
        assert SafetySeverity.HIGH == "HIGH"
        assert SafetySeverity.MEDIUM == "MEDIUM"
        assert SafetySeverity.LOW == "LOW"
        assert len(SafetySeverity) == 4


class TestSafetyCase:
    """Tests for SafetyCase dataclass."""

    def test_creation(self) -> None:
        case = SafetyCase(
            id="SC-001",
            title="Flight Safety Case",
            properties=[],
            status="DRAFT",
            created_at=1000.0,
        )
        assert case.id == "SC-001"
        assert case.title == "Flight Safety Case"
        assert case.properties == []
        assert case.status == "DRAFT"
        assert case.created_at == 1000.0

    def test_add_property(self) -> None:
        case = SafetyCase(
            id="SC-001",
            title="Flight Safety Case",
            properties=[],
            status="DRAFT",
            created_at=1000.0,
        )
        prop = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        case.add_property(prop)
        assert len(case.properties) == 1
        assert case.properties[0] == prop

    def test_remove_property(self) -> None:
        prop = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        case = SafetyCase(
            id="SC-001",
            title="Flight Safety Case",
            properties=[prop],
            status="DRAFT",
            created_at=1000.0,
        )
        case.remove_property(prop)
        assert len(case.properties) == 0

    def test_verify_all(self) -> None:
        prop1 = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        prop2 = SafetyProperty(
            id="SP-002",
            name="Speed Limit",
            description="Vehicle must stay below max speed",
            expression="speed < 50",
            severity="HIGH",
        )
        case = SafetyCase(
            id="SC-001",
            title="Flight Safety Case",
            properties=[prop1, prop2],
            status="DRAFT",
            created_at=1000.0,
        )
        state = {"altitude": 300.0, "speed": 30.0}
        results = case.verify_all(state)
        assert results["SP-001"] is True
        assert results["SP-002"] is True

    def test_get_case_status(self) -> None:
        case = SafetyCase(
            id="SC-001",
            title="Flight Safety Case",
            properties=[],
            status="DRAFT",
            created_at=1000.0,
        )
        assert case.get_case_status() == "DRAFT"

    def test_get_failure_count(self) -> None:
        prop1 = SafetyProperty(
            id="SP-001",
            name="Altitude Limit",
            description="Vehicle must stay below max altitude",
            expression="altitude < 500",
            severity="CRITICAL",
        )
        prop2 = SafetyProperty(
            id="SP-002",
            name="Speed Limit",
            description="Vehicle must stay below max speed",
            expression="speed < 50",
            severity="HIGH",
        )
        case = SafetyCase(
            id="SC-001",
            title="Flight Safety Case",
            properties=[prop1, prop2],
            status="DRAFT",
            created_at=1000.0,
        )
        state = {"altitude": 600.0, "speed": 30.0}
        assert case.get_failure_count(state) == 1


class TestFMEAEntry:
    """Tests for FMEAEntry dataclass."""

    def test_creation(self) -> None:
        entry = FMEAEntry(
            id="FMEA-001",
            component="Motor",
            failure_mode="Overheating",
            effect="Loss of thrust",
            cause="Cooling failure",
            severity=8,
            occurrence=4,
            detection=3,
            rpn=96,
        )
        assert entry.id == "FMEA-001"
        assert entry.component == "Motor"
        assert entry.failure_mode == "Overheating"
        assert entry.effect == "Loss of thrust"
        assert entry.cause == "Cooling failure"
        assert entry.severity == 8
        assert entry.occurrence == 4
        assert entry.detection == 3
        assert entry.rpn == 96

    def test_calculate_rpn(self) -> None:
        entry = FMEAEntry(
            id="FMEA-001",
            component="Motor",
            failure_mode="Overheating",
            effect="Loss of thrust",
            cause="Cooling failure",
            severity=8,
            occurrence=4,
            detection=3,
            rpn=0,
        )
        assert entry.calculate_rpn() == 96

    def test_get_risk_level_low(self) -> None:
        entry = FMEAEntry(
            id="FMEA-001",
            component="Motor",
            failure_mode="Overheating",
            effect="Loss of thrust",
            cause="Cooling failure",
            severity=2,
            occurrence=2,
            detection=2,
            rpn=8,
        )
        assert entry.get_risk_level() == FMEARiskLevel.LOW

    def test_get_risk_level_medium(self) -> None:
        entry = FMEAEntry(
            id="FMEA-001",
            component="Motor",
            failure_mode="Overheating",
            effect="Loss of thrust",
            cause="Cooling failure",
            severity=5,
            occurrence=5,
            detection=4,
            rpn=100,
        )
        assert entry.get_risk_level() == FMEARiskLevel.MEDIUM

    def test_get_risk_level_high(self) -> None:
        entry = FMEAEntry(
            id="FMEA-001",
            component="Motor",
            failure_mode="Overheating",
            effect="Loss of thrust",
            cause="Cooling failure",
            severity=8,
            occurrence=7,
            detection=5,
            rpn=280,
        )
        assert entry.get_risk_level() == FMEARiskLevel.HIGH

    def test_get_risk_level_critical(self) -> None:
        entry = FMEAEntry(
            id="FMEA-001",
            component="Motor",
            failure_mode="Overheating",
            effect="Loss of thrust",
            cause="Cooling failure",
            severity=10,
            occurrence=9,
            detection=9,
            rpn=810,
        )
        assert entry.get_risk_level() == FMEARiskLevel.CRITICAL

    def test_fmea_risk_level_enum(self) -> None:
        assert FMEARiskLevel.LOW == "LOW"
        assert FMEARiskLevel.MEDIUM == "MEDIUM"
        assert FMEARiskLevel.HIGH == "HIGH"
        assert FMEARiskLevel.CRITICAL == "CRITICAL"
        assert len(FMEARiskLevel) == 4


class TestFaultTree:
    """Tests for FaultTree dataclass."""

    def test_creation(self) -> None:
        tree = FaultTree(
            id="FT-001",
            name="Motor Failure",
            top_event="Motor stops",
            gates=[{"id": "G1", "type": "AND", "inputs": ["E1", "E2"]}],
            basic_events=[{"id": "E1", "probability": 0.1}, {"id": "E2", "probability": 0.2}],
        )
        assert tree.id == "FT-001"
        assert tree.name == "Motor Failure"
        assert tree.top_event == "Motor stops"
        assert len(tree.gates) == 1
        assert len(tree.basic_events) == 2

    def test_evaluate_tree_and_gate(self) -> None:
        tree = FaultTree(
            id="FT-001",
            name="Motor Failure",
            top_event="Motor stops",
            gates=[{"id": "G1", "type": "AND", "inputs": ["E1", "E2"]}],
            basic_events=[{"id": "E1", "probability": 0.1}, {"id": "E2", "probability": 0.2}],
        )
        inputs = {"E1": True, "E2": True}
        assert tree.evaluate_tree(inputs) is True

    def test_evaluate_tree_and_gate_fails(self) -> None:
        tree = FaultTree(
            id="FT-001",
            name="Motor Failure",
            top_event="Motor stops",
            gates=[{"id": "G1", "type": "AND", "inputs": ["E1", "E2"]}],
            basic_events=[{"id": "E1", "probability": 0.1}, {"id": "E2", "probability": 0.2}],
        )
        inputs = {"E1": True, "E2": False}
        assert tree.evaluate_tree(inputs) is False

    def test_evaluate_tree_or_gate(self) -> None:
        tree = FaultTree(
            id="FT-001",
            name="Motor Failure",
            top_event="Motor stops",
            gates=[{"id": "G1", "type": "OR", "inputs": ["E1", "E2"]}],
            basic_events=[{"id": "E1", "probability": 0.1}, {"id": "E2", "probability": 0.2}],
        )
        inputs = {"E1": False, "E2": True}
        assert tree.evaluate_tree(inputs) is True

    def test_get_minimal_cuts(self) -> None:
        tree = FaultTree(
            id="FT-001",
            name="Motor Failure",
            top_event="Motor stops",
            gates=[{"id": "G1", "type": "AND", "inputs": ["E1", "E2"]}],
            basic_events=[{"id": "E1", "probability": 0.1}, {"id": "E2", "probability": 0.2}],
        )
        cuts = tree.get_minimal_cuts()
        assert len(cuts) == 1
        assert set(cuts[0]) == {"E1", "E2"}

    def test_get_probability(self) -> None:
        tree = FaultTree(
            id="FT-001",
            name="Motor Failure",
            top_event="Motor stops",
            gates=[{"id": "G1", "type": "AND", "inputs": ["E1", "E2"]}],
            basic_events=[{"id": "E1", "probability": 0.1}, {"id": "E2", "probability": 0.2}],
        )
        inputs = {"E1": 0.1, "E2": 0.2}
        prob = tree.get_probability(inputs)
        assert prob == pytest.approx(0.02)


class TestFormalConfig:
    """Tests for FormalConfig dataclass."""

    def test_creation(self) -> None:
        config = FormalConfig(
            enabled=True,
            verification_level="strict",
            auto_verify=True,
            report_format="json",
        )
        assert config.enabled is True
        assert config.verification_level == "strict"
        assert config.auto_verify is True
        assert config.report_format == "json"

    def test_defaults(self) -> None:
        config = FormalConfig()
        assert config.enabled is False
        assert config.verification_level == "basic"
        assert config.auto_verify is False
        assert config.report_format == "text"


# Import functions that need to be tested
from apex_autopilot_optimization.formal.property import verify_property, get_property_status
