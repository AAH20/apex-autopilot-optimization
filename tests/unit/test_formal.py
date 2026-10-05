"""Tests for formal verification package."""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.formal import (
    FaultTree,
    FMEAEntry,
    FMEARiskLevel,
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
from apex_autopilot_optimization.formal.property import get_property_status, verify_property


class TestSafetyPropertyEdgeCases:
    """Edge-case tests for SafetyProperty verification."""

    def test_verify_complex_expression(self) -> None:
        prop = SafetyProperty(
            id="SP-003",
            name="Composite Check",
            description="Altitude and speed within bounds",
            expression="altitude < 500 and speed < 50",
            severity="HIGH",
        )
        assert verify_property(prop, {"altitude": 300, "speed": 30}) is True
        assert verify_property(prop, {"altitude": 600, "speed": 30}) is False

    def test_verify_missing_state_variable(self) -> None:
        prop = SafetyProperty(
            id="SP-004",
            name="Missing Var",
            description="Expression references missing state key",
            expression="nonexistent < 100",
            severity="LOW",
        )
        assert verify_property(prop, {"altitude": 300}) is False

    def test_verify_invalid_expression(self) -> None:
        prop = SafetyProperty(
            id="SP-005",
            name="Invalid Expr",
            description="Expression with syntax error",
            expression="altitude < ",
            severity="LOW",
        )
        assert verify_property(prop, {"altitude": 300}) is False

    def test_verify_non_boolean_result(self) -> None:
        prop = SafetyProperty(
            id="SP-006",
            name="Non-bool",
            description="Expression returns non-boolean",
            expression="altitude + 10",
            severity="LOW",
        )
        assert verify_property(prop, {"altitude": 300}) is True

    def test_verify_empty_state(self) -> None:
        prop = SafetyProperty(
            id="SP-007",
            name="Empty State",
            description="Expression with empty state dict",
            expression="True",
            severity="LOW",
        )
        assert verify_property(prop, {}) is True

    def test_verify_with_arithmetic(self) -> None:
        prop = SafetyProperty(
            id="SP-008",
            name="Arithmetic",
            description="Expression using arithmetic",
            expression="altitude * 2 < 1000",
            severity="MEDIUM",
        )
        assert verify_property(prop, {"altitude": 400}) is True
        assert verify_property(prop, {"altitude": 600}) is False

    def test_get_property_status_with_status_attr(self) -> None:
        prop = SafetyProperty(
            id="SP-009",
            name="With Status",
            description="Property with status attribute set",
            expression="True",
            severity="LOW",
        )
        object.__setattr__(prop, "status", "VERIFIED")
        assert get_property_status(prop) == "VERIFIED"


class TestSafetyCaseEdgeCases:
    """Edge-case tests for SafetyCase."""

    def test_verify_all_empty_properties(self) -> None:
        case = SafetyCase(id="SC-002", title="Empty Case")
        results = case.verify_all({"altitude": 300})
        assert results == {}

    def test_get_failure_count_all_pass(self) -> None:
        prop = SafetyProperty(
            id="SP-010",
            name="Always True",
            description="Always passes",
            expression="True",
            severity="LOW",
        )
        case = SafetyCase(id="SC-003", title="All Pass", properties=[prop])
        assert case.get_failure_count({}) == 0

    def test_get_failure_count_all_fail(self) -> None:
        prop = SafetyProperty(
            id="SP-011",
            name="Always False",
            description="Always fails",
            expression="False",
            severity="LOW",
        )
        case = SafetyCase(id="SC-004", title="All Fail", properties=[prop])
        assert case.get_failure_count({}) == 1

    def test_add_multiple_properties(self) -> None:
        case = SafetyCase(id="SC-005", title="Multi")
        for i in range(5):
            case.add_property(
                SafetyProperty(
                    id=f"SP-{i}",
                    name=f"Prop {i}",
                    description="Test",
                    expression="True",
                    severity="LOW",
                )
            )
        assert len(case.properties) == 5

    def test_remove_nonexistent_property_raises(self) -> None:
        case = SafetyCase(id="SC-006", title="Remove Test")
        prop = SafetyProperty(
            id="SP-012",
            name="Orphan",
            description="Not in case",
            expression="True",
            severity="LOW",
        )
        with pytest.raises(ValueError, match="not in list"):
            case.remove_property(prop)

    def test_verify_all_mixed_results(self) -> None:
        prop_pass = SafetyProperty(
            id="SP-013",
            name="Pass",
            description="Passes",
            expression="x > 0",
            severity="LOW",
        )
        prop_fail = SafetyProperty(
            id="SP-014",
            name="Fail",
            description="Fails",
            expression="x < 0",
            severity="LOW",
        )
        case = SafetyCase(id="SC-007", title="Mixed", properties=[prop_pass, prop_fail])
        results = case.verify_all({"x": 5})
        assert results == {"SP-013": True, "SP-014": False}


class TestFMEAEdgeCases:
    """Edge-case tests for FMEAEntry."""

    def test_rpn_boundary_low_medium(self) -> None:
        entry = FMEAEntry(
            id="FMEA-B1",
            component="C",
            failure_mode="FM",
            effect="E",
            cause="CA",
            severity=10,
            occurrence=10,
            detection=1,
            rpn=100,
        )
        assert entry.get_risk_level() == FMEARiskLevel.MEDIUM

    def test_rpn_boundary_medium_high(self) -> None:
        entry = FMEAEntry(
            id="FMEA-B2",
            component="C",
            failure_mode="FM",
            effect="E",
            cause="CA",
            severity=10,
            occurrence=10,
            detection=2,
            rpn=200,
        )
        assert entry.get_risk_level() == FMEARiskLevel.HIGH

    def test_rpn_boundary_high_critical(self) -> None:
        entry = FMEAEntry(
            id="FMEA-B3",
            component="C",
            failure_mode="FM",
            effect="E",
            cause="CA",
            severity=10,
            occurrence=10,
            detection=5,
            rpn=500,
        )
        assert entry.get_risk_level() == FMEARiskLevel.CRITICAL

    def test_calculate_rpn_overrides_stored(self) -> None:
        entry = FMEAEntry(
            id="FMEA-B4",
            component="C",
            failure_mode="FM",
            effect="E",
            cause="CA",
            severity=3,
            occurrence=3,
            detection=3,
            rpn=999,
        )
        assert entry.calculate_rpn() == 27

    def test_get_risk_level_uses_calculate_when_rpn_zero(self) -> None:
        entry = FMEAEntry(
            id="FMEA-B5",
            component="C",
            failure_mode="FM",
            effect="E",
            cause="CA",
            severity=5,
            occurrence=5,
            detection=5,
            rpn=0,
        )
        assert entry.get_risk_level() == FMEARiskLevel.MEDIUM


class TestFaultTreeEdgeCases:
    """Edge-case tests for FaultTree."""

    def test_nested_gates(self) -> None:
        tree = FaultTree(
            id="FT-002",
            name="Nested",
            top_event="Top",
            gates=[
                {"id": "G1", "type": "OR", "inputs": ["G2", "E3"]},
                {"id": "G2", "type": "AND", "inputs": ["E1", "E2"]},
            ],
            basic_events=[
                {"id": "E1", "probability": 0.1},
                {"id": "E2", "probability": 0.2},
                {"id": "E3", "probability": 0.3},
            ],
        )
        assert tree.evaluate_tree({"E1": True, "E2": True, "E3": False}) is True
        assert tree.evaluate_tree({"E1": False, "E2": False, "E3": True}) is True
        assert tree.evaluate_tree({"E1": False, "E2": True, "E3": False}) is False

    def test_minimal_cuts_or_gate(self) -> None:
        tree = FaultTree(
            id="FT-003",
            name="OR Cuts",
            top_event="Top",
            gates=[{"id": "G1", "type": "OR", "inputs": ["E1", "E2", "E3"]}],
            basic_events=[
                {"id": "E1", "probability": 0.1},
                {"id": "E2", "probability": 0.2},
                {"id": "E3", "probability": 0.3},
            ],
        )
        cuts = tree.get_minimal_cuts()
        assert len(cuts) == 3
        assert {"E1"} in cuts
        assert {"E2"} in cuts
        assert {"E3"} in cuts

    def test_probability_or_gate(self) -> None:
        tree = FaultTree(
            id="FT-004",
            name="OR Prob",
            top_event="Top",
            gates=[{"id": "G1", "type": "OR", "inputs": ["E1", "E2"]}],
            basic_events=[
                {"id": "E1", "probability": 0.5},
                {"id": "E2", "probability": 0.5},
            ],
        )
        prob = tree.get_probability({"E1": 0.5, "E2": 0.5})
        assert prob == pytest.approx(0.75)

    def test_empty_gates(self) -> None:
        tree = FaultTree(
            id="FT-005",
            name="Empty",
            top_event="Top",
            gates=[],
            basic_events=[{"id": "E1", "probability": 0.1}],
        )
        assert tree.evaluate_tree({"E1": True}) is False
        assert tree.get_minimal_cuts() == []
        assert tree.get_probability({"E1": 0.5}) == 0.0

    def test_probability_nested_gates(self) -> None:
        tree = FaultTree(
            id="FT-006",
            name="Nested Prob",
            top_event="Top",
            gates=[
                {"id": "G1", "type": "AND", "inputs": ["G2", "E3"]},
                {"id": "G2", "type": "OR", "inputs": ["E1", "E2"]},
            ],
            basic_events=[
                {"id": "E1", "probability": 0.5},
                {"id": "E2", "probability": 0.5},
                {"id": "E3", "probability": 0.8},
            ],
        )
        # P(G2) = 0.75, P(G1) = 0.75 * 0.8 = 0.6
        prob = tree.get_probability({"E1": 0.5, "E2": 0.5, "E3": 0.8})
        assert prob == pytest.approx(0.6)

    def test_evaluate_tree_default_false_for_missing_inputs(self) -> None:
        tree = FaultTree(
            id="FT-007",
            name="Defaults",
            top_event="Top",
            gates=[{"id": "G1", "type": "AND", "inputs": ["E1", "E2"]}],
            basic_events=[
                {"id": "E1", "probability": 0.1},
                {"id": "E2", "probability": 0.2},
            ],
        )
        assert tree.evaluate_tree({}) is False


class TestModuleImports:
    """Tests verifying canonical module locations."""

    def test_property_module_exports(self) -> None:
        from apex_autopilot_optimization.formal.property import (
            SafetyProperty,
            SafetySeverity,
            get_property_status,
            verify_property,
        )

        assert SafetyProperty is not None
        assert SafetySeverity is not None
        assert callable(verify_property)
        assert callable(get_property_status)

    def test_case_module_exports(self) -> None:
        from apex_autopilot_optimization.formal.case import SafetyCase

        assert SafetyCase is not None

    def test_safety_module_compat_shim(self) -> None:
        from apex_autopilot_optimization.formal.case import (
            SafetyCase as SC2,  # noqa: N814
        )
        from apex_autopilot_optimization.formal.property import (
            SafetyProperty as SP2,  # noqa: N814
        )
        from apex_autopilot_optimization.formal.property import (
            SafetySeverity as SS2,  # noqa: N814
        )
        from apex_autopilot_optimization.formal.safety import (
            SafetyCase,
            SafetyProperty,
            SafetySeverity,
        )

        assert SafetyCase is SC2
        assert SafetyProperty is SP2
        assert SafetySeverity is SS2

    def test_fmea_module_exports(self) -> None:
        from apex_autopilot_optimization.formal.fmea import FMEAEntry, FMEARiskLevel

        assert FMEAEntry is not None
        assert FMEARiskLevel is not None

    def test_fault_tree_module_exports(self) -> None:
        from apex_autopilot_optimization.formal.fault_tree import FaultTree

        assert FaultTree is not None

    def test_config_module_exports(self) -> None:
        from apex_autopilot_optimization.formal.config import FormalConfig

        assert FormalConfig is not None

    def test_package_all_exports(self) -> None:
        import apex_autopilot_optimization.formal as formal

        expected = {
            "FMEAEntry",
            "FMEARiskLevel",
            "FaultTree",
            "FormalConfig",
            "SafetyCase",
            "SafetyProperty",
            "SafetySeverity",
            "get_property_status",
            "verify_property",
        }
        assert expected <= set(formal.__all__)
