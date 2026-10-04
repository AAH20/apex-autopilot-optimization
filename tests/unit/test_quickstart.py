"""Tests for quickstart module."""

from apex_autopilot_optimization.quickstart import (
    DemoScenario,
    QuickstartRunner,
    get_recommended_scenario,
    list_scenarios,
    run_demo,
)


class TestDemoScenario:
    """Tests for DemoScenario dataclass."""

    def test_scenario_creation(self):
        scenario = DemoScenario(
            name="test",
            description="Test scenario",
            scale="startup",
            modules=["core_types", "astar"],
            steps=["step1", "step2"],
        )
        assert scenario.name == "test"
        assert scenario.scale == "startup"
        assert len(scenario.modules) == 2
        assert len(scenario.steps) == 2


class TestQuickstartRunner:
    """Tests for QuickstartRunner class."""

    def test_runner_creation(self):
        runner = QuickstartRunner()
        assert runner is not None

    def test_list_scenarios(self):
        scenarios = list_scenarios()
        assert len(scenarios) > 0
        assert all(isinstance(s, DemoScenario) for s in scenarios)

    def test_get_recommended_scenario_startup(self):
        scenario = get_recommended_scenario("startup")
        assert scenario is not None
        assert scenario.scale == "startup"

    def test_get_recommended_scenario_smb(self):
        scenario = get_recommended_scenario("smb")
        assert scenario is not None
        assert scenario.scale == "smb"

    def test_get_recommended_scenario_mid_market(self):
        scenario = get_recommended_scenario("mid_market")
        assert scenario is not None
        assert scenario.scale == "mid_market"

    def test_get_recommended_scenario_enterprise(self):
        scenario = get_recommended_scenario("enterprise")
        assert scenario is not None
        assert scenario.scale == "enterprise"

    def test_get_recommended_scenario_large(self):
        scenario = get_recommended_scenario("large")
        assert scenario is not None
        assert scenario.scale == "large"

    def test_get_recommended_scenario_invalid(self):
        scenario = get_recommended_scenario("invalid")
        assert scenario is None

    def test_run_demo(self):
        result = run_demo("startup")
        assert result is not None
        assert "scenario" in result
        assert "steps_completed" in result
        assert "modules_used" in result

    def test_run_demo_invalid(self):
        result = run_demo("invalid")
        assert result is not None
        assert "error" in result


class TestRunDemo:
    """Tests for run_demo function."""

    def test_run_demo_returns_dict(self):
        result = run_demo("startup")
        assert isinstance(result, dict)

    def test_run_demo_has_required_keys(self):
        result = run_demo("startup")
        required_keys = {"scenario", "steps_completed", "modules_used"}
        assert required_keys.issubset(result.keys())

    def test_run_demo_scenario_name(self):
        result = run_demo("startup")
        assert result["scenario"] == "startup"

    def test_run_demo_steps_completed(self):
        result = run_demo("startup")
        assert result["steps_completed"] > 0

    def test_run_demo_modules_used(self):
        result = run_demo("startup")
        assert len(result["modules_used"]) > 0
