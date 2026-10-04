"""Tests for setup wizard module."""

from apex_autopilot_optimization.setup_wizard import (
    SetupWizard,
    WizardStep,
    get_default_steps,
    run_setup,
)


class TestWizardStep:
    """Tests for WizardStep dataclass."""

    def test_step_creation(self):
        step = WizardStep(
            name="test",
            description="Test step",
            action=lambda: "done",
        )
        assert step.name == "test"
        assert step.description == "Test step"
        assert callable(step.action)

    def test_step_with_optional_fields(self):
        step = WizardStep(
            name="test",
            description="Test step",
            action=lambda: "done",
            skippable=True,
            condition=lambda: True,
        )
        assert step.skippable is True
        assert callable(step.condition)


class TestSetupWizard:
    """Tests for SetupWizard class."""

    def test_wizard_creation(self):
        wizard = SetupWizard()
        assert wizard is not None

    def test_wizard_with_steps(self):
        steps = get_default_steps()
        wizard = SetupWizard(steps=steps)
        assert len(wizard.steps) == len(steps)

    def test_wizard_run_all(self):
        steps = get_default_steps()
        wizard = SetupWizard(steps=steps)
        result = wizard.run()
        assert result is not None
        assert "completed" in result
        assert "total" in result

    def test_wizard_run_with_skip(self):
        steps = get_default_steps()
        wizard = SetupWizard(steps=steps)
        result = wizard.run(skip_first=True)
        assert result is not None
        assert result["completed"] == result["total"]
        assert result["total"] < len(steps)

    def test_wizard_progress(self):
        steps = get_default_steps()
        wizard = SetupWizard(steps=steps)
        progress = wizard.get_progress()
        assert "completed" in progress
        assert "total" in progress
        assert "percent" in progress

    def test_wizard_reset(self):
        steps = get_default_steps()
        wizard = SetupWizard(steps=steps)
        wizard.run()
        wizard.reset()
        progress = wizard.get_progress()
        assert progress["completed"] == 0


class TestGetDefaultSteps:
    """Tests for get_default_steps function."""

    def test_returns_list(self):
        steps = get_default_steps()
        assert isinstance(steps, list)
        assert len(steps) > 0

    def test_all_steps_have_names(self):
        steps = get_default_steps()
        for step in steps:
            assert step.name is not None
            assert len(step.name) > 0

    def test_all_steps_have_actions(self):
        steps = get_default_steps()
        for step in steps:
            assert callable(step.action)


class TestRunSetup:
    """Tests for run_setup function."""

    def test_run_setup_returns_dict(self):
        result = run_setup()
        assert isinstance(result, dict)

    def test_run_setup_has_required_keys(self):
        result = run_setup()
        required_keys = {"completed", "total", "status"}
        assert required_keys.issubset(result.keys())

    def test_run_setup_status(self):
        result = run_setup()
        assert result["status"] in ("completed", "partial", "failed")
