"""Unit tests for serverless/FaaS integration package."""

import json

import pytest

from apex_autopilot_optimization.serverless import (
    ControlHandler,
    EstimationHandler,
    FaaSConfig,
    FaaSContext,
    FaaSHandler,
    FaaSResponse,
    OptimizationHandler,
    PlanningHandler,
    SafetyHandler,
)

# ---------------------------------------------------------------------------
# FaaSHandler ABC
# ---------------------------------------------------------------------------


class TestFaaSHandler:
    """Tests for the FaaSHandler abstract base class."""

    def test_cannot_instantiate_abc(self):
        """FaaSHandler is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            FaaSHandler()

    def test_subclass_can_instantiate(self):
        """A concrete subclass of FaaSHandler can be instantiated."""

        class MyHandler(FaaSHandler):
            def handle(self, event, context):
                return FaaSResponse(status_code=200, body={"ok": True})

        handler = MyHandler()
        assert handler is not None

    def test_subclass_must_implement_handle(self):
        """A subclass without handle() cannot be instantiated."""

        class IncompleteHandler(FaaSHandler):
            pass

        with pytest.raises(TypeError):
            IncompleteHandler()

    def test_handle_returns_faas_response(self):
        """handle() returns a FaaSResponse instance."""

        class EchoHandler(FaaSHandler):
            def handle(self, event, context):
                return FaaSResponse(status_code=200, body=event)

        handler = EchoHandler()
        result = handler.handle({"key": "value"}, None)
        assert isinstance(result, FaaSResponse)
        assert result.status_code == 200
        assert result.body == {"key": "value"}


# ---------------------------------------------------------------------------
# FaaSConfig
# ---------------------------------------------------------------------------


class TestFaaSConfig:
    """Tests for the FaaSConfig dataclass."""

    def test_create_with_defaults(self):
        """FaaSConfig can be created with sensible defaults."""
        config = FaaSConfig()
        assert config.provider == "aws"
        assert config.region == "us-east-1"
        assert config.memory_mb == 128
        assert config.timeout_seconds == 30
        assert config.concurrency == 100

    def test_create_with_custom_values(self):
        """FaaSConfig accepts custom values."""
        config = FaaSConfig(
            provider="azure",
            region="westeurope",
            memory_mb=512,
            timeout_seconds=60,
            concurrency=50,
        )
        assert config.provider == "azure"
        assert config.region == "westeurope"
        assert config.memory_mb == 512
        assert config.timeout_seconds == 60
        assert config.concurrency == 50

    def test_provider_must_be_string(self):
        """Provider must be a string."""
        with pytest.raises(TypeError):
            FaaSConfig(provider=123)

    def test_memory_must_be_positive(self):
        """Memory must be a positive integer."""
        with pytest.raises(ValueError):
            FaaSConfig(memory_mb=0)
        with pytest.raises(ValueError):
            FaaSConfig(memory_mb=-1)

    def test_timeout_must_be_positive(self):
        """Timeout must be a positive integer."""
        with pytest.raises(ValueError):
            FaaSConfig(timeout_seconds=0)

    def test_concurrency_must_be_positive(self):
        """Concurrency must be a positive integer."""
        with pytest.raises(ValueError):
            FaaSConfig(concurrency=0)


# ---------------------------------------------------------------------------
# FaaSResponse
# ---------------------------------------------------------------------------


class TestFaaSResponse:
    """Tests for the FaaSResponse dataclass and its conversion methods."""

    def test_create_with_defaults(self):
        """FaaSResponse can be created with defaults."""
        resp = FaaSResponse(status_code=200, body={"result": "ok"})
        assert resp.status_code == 200
        assert resp.body == {"result": "ok"}
        assert resp.headers == {}

    def test_create_with_custom_headers(self):
        """FaaSResponse accepts custom headers."""
        resp = FaaSResponse(
            status_code=201,
            body={"id": 1},
            headers={"Content-Type": "application/json"},
        )
        assert resp.headers["Content-Type"] == "application/json"

    def test_to_lambda_response(self):
        """to_lambda_response returns AWS Lambda-compatible dict."""
        resp = FaaSResponse(
            status_code=200,
            body={"message": "hello"},
            headers={"X-Custom": "value"},
        )
        result = resp.to_lambda_response()
        assert result["statusCode"] == 200
        assert result["headers"] == {"X-Custom": "value"}
        assert "body" in result
        body = json.loads(result["body"])
        assert body == {"message": "hello"}

    def test_to_lambda_response_is_base64_safe(self):
        """to_lambda_response body is a JSON string (Lambda requirement)."""
        resp = FaaSResponse(status_code=200, body={"data": [1, 2, 3]})
        result = resp.to_lambda_response()
        assert isinstance(result["body"], str)
        parsed = json.loads(result["body"])
        assert parsed == {"data": [1, 2, 3]}

    def test_to_azure_response(self):
        """to_azure_response returns Azure Functions-compatible dict."""
        resp = FaaSResponse(
            status_code=200,
            body={"result": "azure"},
            headers={"Content-Type": "application/json"},
        )
        result = resp.to_azure_response()
        assert result["status_code"] == 200
        assert result["body"] == {"result": "azure"}
        assert result["headers"]["Content-Type"] == "application/json"

    def test_to_gcp_response(self):
        """to_gcp_response returns GCP Cloud Functions-compatible dict."""
        resp = FaaSResponse(
            status_code=200,
            body={"result": "gcp"},
            headers={"Content-Type": "application/json"},
        )
        result = resp.to_gcp_response()
        assert result["status_code"] == 200
        assert result["body"] == {"result": "gcp"}
        assert result["headers"]["Content-Type"] == "application/json"

    def test_to_lambda_response_with_empty_body(self):
        """to_lambda_response handles empty body."""
        resp = FaaSResponse(status_code=204, body={})
        result = resp.to_lambda_response()
        assert result["statusCode"] == 204
        assert json.loads(result["body"]) == {}


# ---------------------------------------------------------------------------
# FaaSContext
# ---------------------------------------------------------------------------


class TestFaaSContext:
    """Tests for the FaaSContext dataclass."""

    def test_create_with_all_fields(self):
        """FaaSContext can be created with all fields."""
        ctx = FaaSContext(
            request_id="req-123",
            function_name="my-function",
            memory_limit_mb=256,
            time_remaining_ms=15000,
            trace_id="trace-abc",
        )
        assert ctx.request_id == "req-123"
        assert ctx.function_name == "my-function"
        assert ctx.memory_limit_mb == 256
        assert ctx.time_remaining_ms == 15000
        assert ctx.trace_id == "trace-abc"

    def test_create_with_defaults(self):
        """FaaSContext has sensible defaults."""
        ctx = FaaSContext()
        assert ctx.request_id is not None
        assert ctx.function_name is not None
        assert ctx.memory_limit_mb > 0
        assert ctx.time_remaining_ms > 0
        assert ctx.trace_id is not None

    def test_request_id_is_unique(self):
        """Each FaaSContext gets a unique request_id by default."""
        ctx1 = FaaSContext()
        ctx2 = FaaSContext()
        assert ctx1.request_id != ctx2.request_id


# ---------------------------------------------------------------------------
# Concrete Handler Implementations
# ---------------------------------------------------------------------------


class TestPlanningHandler:
    """Tests for PlanningHandler."""

    def test_handle_returns_faas_response(self):
        """PlanningHandler.handle returns a FaaSResponse."""
        handler = PlanningHandler()
        result = handler.handle({"task": "plan"}, None)
        assert isinstance(result, FaaSResponse)
        assert result.status_code == 200

    def test_handle_returns_plan_in_body(self):
        """PlanningHandler returns a plan in the response body."""
        handler = PlanningHandler()
        result = handler.handle({"task": "plan"}, None)
        assert "plan" in result.body
        assert result.body["plan"] is not None

    def test_handle_with_empty_event(self):
        """PlanningHandler handles empty event gracefully."""
        handler = PlanningHandler()
        result = handler.handle({}, None)
        assert result.status_code == 200
        assert "plan" in result.body


class TestOptimizationHandler:
    """Tests for OptimizationHandler."""

    def test_handle_returns_faas_response(self):
        """OptimizationHandler.handle returns a FaaSResponse."""
        handler = OptimizationHandler()
        result = handler.handle({"objective": "minimize"}, None)
        assert isinstance(result, FaaSResponse)
        assert result.status_code == 200

    def test_handle_returns_optimization_result(self):
        """OptimizationHandler returns optimization result in body."""
        handler = OptimizationHandler()
        result = handler.handle({"objective": "minimize"}, None)
        assert "result" in result.body
        assert result.body["result"] is not None


class TestEstimationHandler:
    """Tests for EstimationHandler."""

    def test_handle_returns_faas_response(self):
        """EstimationHandler.handle returns a FaaSResponse."""
        handler = EstimationHandler()
        result = handler.handle({"estimate": "cost"}, None)
        assert isinstance(result, FaaSResponse)
        assert result.status_code == 200

    def test_handle_returns_estimate_in_body(self):
        """EstimationHandler returns an estimate in the response body."""
        handler = EstimationHandler()
        result = handler.handle({"estimate": "cost"}, None)
        assert "estimate" in result.body
        assert result.body["estimate"] is not None


class TestControlHandler:
    """Tests for ControlHandler."""

    def test_handle_returns_faas_response(self):
        """ControlHandler.handle returns a FaaSResponse."""
        handler = ControlHandler()
        result = handler.handle({"action": "start"}, None)
        assert isinstance(result, FaaSResponse)
        assert result.status_code == 200

    def test_handle_returns_control_status(self):
        """ControlHandler returns control status in body."""
        handler = ControlHandler()
        result = handler.handle({"action": "start"}, None)
        assert "status" in result.body
        assert result.body["status"] is not None


class TestSafetyHandler:
    """Tests for SafetyHandler."""

    def test_handle_returns_faas_response(self):
        """SafetyHandler.handle returns a FaaSResponse."""
        handler = SafetyHandler()
        result = handler.handle({"check": "bounds"}, None)
        assert isinstance(result, FaaSResponse)
        assert result.status_code == 200

    def test_handle_returns_safety_status(self):
        """SafetyHandler returns safety status in body."""
        handler = SafetyHandler()
        result = handler.handle({"check": "bounds"}, None)
        assert "safe" in result.body
        assert isinstance(result.body["safe"], bool)
