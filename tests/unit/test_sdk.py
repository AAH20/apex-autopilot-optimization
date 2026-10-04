"""Tests for the SDK client library."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from apex_autopilot_optimization.sdk import (
    ApexClient,
    ApexConfig,
    ApexError,
    ApexResponse,
)


class TestApexConfig(unittest.TestCase):
    """Tests for ApexConfig dataclass."""

    def test_config_defaults(self) -> None:
        config = ApexConfig(base_url="https://api.example.com", api_key="key123")
        assert config.base_url == "https://api.example.com"
        assert config.api_key == "key123"
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 3
        assert config.verify_ssl is True

    def test_config_custom_values(self) -> None:
        config = ApexConfig(
            base_url="https://api.example.com",
            api_key="key123",
            timeout_seconds=60.0,
            max_retries=5,
            verify_ssl=False,
        )
        assert config.timeout_seconds == 60.0
        assert config.max_retries == 5
        assert config.verify_ssl is False


class TestApexResponse(unittest.TestCase):
    """Tests for ApexResponse dataclass."""

    def test_response_success(self) -> None:
        resp = ApexResponse(status=200, data={"result": "ok"}, request_id="req-1")
        assert resp.is_success() is True
        assert resp.get_error() is None

    def test_response_error(self) -> None:
        resp = ApexResponse(
            status=400, data={"error": "bad request"}, request_id="req-2"
        )
        assert resp.is_success() is False
        assert resp.get_error() == "bad request"

    def test_response_created_is_success(self) -> None:
        resp = ApexResponse(status=201, data={"id": 1})
        assert resp.is_success() is True

    def test_response_server_error(self) -> None:
        resp = ApexResponse(status=500, data={"error": "internal error"})
        assert resp.is_success() is False
        assert resp.get_error() == "internal error"

    def test_response_error_no_message(self) -> None:
        resp = ApexResponse(status=500, data={})
        assert resp.get_error() == "Unknown error"


class TestApexError(unittest.TestCase):
    """Tests for ApexError exception."""

    def test_error_basic(self) -> None:
        err = ApexError("something went wrong")
        assert err.status_code == 400
        assert err.message == "something went wrong"
        assert err.details is None
        assert err.request_id == ""
        assert str(err) == "something went wrong"

    def test_error_with_details(self) -> None:
        err = ApexError(
            "validation failed",
            status_code=422,
            details={"field": "name"},
            request_id="req-99",
        )
        assert err.status_code == 422
        assert err.details == {"field": "name"}
        assert err.request_id == "req-99"

    def test_error_is_exception(self) -> None:
        err = ApexError("test")
        assert isinstance(err, Exception)


class TestApexClientConnection(unittest.TestCase):
    """Tests for client connection lifecycle."""

    def test_connect(self) -> None:
        client = ApexClient()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"connected": True}, request_id="r1"
            )
            resp = client.connect("https://api.example.com", "key123")
            assert resp.is_success() is True
            assert client.is_connected() is True

    def test_disconnect(self) -> None:
        client = ApexClient()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(status=200, data={})
            client.connect("https://api.example.com", "key123")
            assert client.is_connected() is True
            client.disconnect()
            assert client.is_connected() is False

    def test_is_connected_initially_false(self) -> None:
        client = ApexClient()
        assert client.is_connected() is False

    def test_connect_sets_config(self) -> None:
        client = ApexClient()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(status=200, data={})
            client.connect("https://api.example.com", "my-key")
            assert client._config.base_url == "https://api.example.com"
            assert client._config.api_key == "my-key"


class TestApexClientCalls(unittest.TestCase):
    """Tests for client API calls (mocked)."""

    def _make_client(self) -> ApexClient:
        client = ApexClient()
        client._connected = True
        return client

    def test_plan(self) -> None:
        client = self._make_client()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"path": [(0, 0), (1, 1)]}, request_id="p1"
            )
            resp = client.plan({"start": [0, 0], "goal": [1, 1]})
            assert resp.is_success() is True
            assert resp.data["path"] == [(0, 0), (1, 1)]
            mock_req.assert_called_once()
            args = mock_req.call_args
            assert args[0][0] == "POST"
            assert args[0][1] == "/plan"

    def test_optimize(self) -> None:
        client = self._make_client()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"trajectory": "optimized"}, request_id="o1"
            )
            resp = client.optimize({"objective": "minimum_snap"})
            assert resp.is_success() is True
            assert resp.data["trajectory"] == "optimized"
            mock_req.assert_called_once()

    def test_estimate(self) -> None:
        client = self._make_client()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"state": [1.0, 2.0]}, request_id="e1"
            )
            resp = client.estimate({"measurements": [0.1, 0.2]})
            assert resp.is_success() is True
            assert resp.data["state"] == [1.0, 2.0]
            mock_req.assert_called_once()

    def test_control(self) -> None:
        client = self._make_client()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"control_input": [0.5, 0.3]}, request_id="c1"
            )
            resp = client.control({"x": 1.0}, {"x": 2.0})
            assert resp.is_success() is True
            assert resp.data["control_input"] == [0.5, 0.3]
            mock_req.assert_called_once()
            args = mock_req.call_args
            assert args[0][0] == "POST"
            assert args[0][1] == "/control"

    def test_filter(self) -> None:
        client = self._make_client()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"safe": True}, request_id="f1"
            )
            resp = client.filter({"x": 0}, {"u": 1}, [{"x": 5, "y": 5}])
            assert resp.is_success() is True
            assert resp.data["safe"] is True
            mock_req.assert_called_once()
            args = mock_req.call_args
            assert args[0][0] == "POST"
            assert args[0][1] == "/filter"

    def test_health(self) -> None:
        client = self._make_client()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"status": "healthy"}, request_id="h1"
            )
            resp = client.health()
            assert resp.is_success() is True
            assert resp.data["status"] == "healthy"
            mock_req.assert_called_once()
            args = mock_req.call_args
            assert args[0][0] == "GET"
            assert args[0][1] == "/health"

    def test_diagnostics(self) -> None:
        client = self._make_client()
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={"diagnostics": "all good"}, request_id="d1"
            )
            resp = client.diagnostics()
            assert resp.is_success() is True
            assert resp.data["diagnostics"] == "all good"
            mock_req.assert_called_once()
            args = mock_req.call_args
            assert args[0][0] == "GET"
            assert args[0][1] == "/diagnostics"


class TestApexClientRequestId(unittest.TestCase):
    """Tests for request ID propagation."""

    def test_request_id_propagated(self) -> None:
        client = ApexClient()
        client._connected = True
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={}, request_id="req-abc-123"
            )
            resp = client.plan({"start": [0, 0]})
            assert resp.request_id == "req-abc-123"

    def test_request_id_from_response(self) -> None:
        client = ApexClient()
        client._connected = True
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(
                status=200, data={}, request_id="xyz-789"
            )
            resp = client.health()
            assert resp.request_id == "xyz-789"


class TestApexClientWithConfig(unittest.TestCase):
    """Tests for client initialized with config."""

    def test_client_with_config(self) -> None:
        config = ApexConfig(
            base_url="https://api.example.com",
            api_key="key123",
            timeout_seconds=10.0,
        )
        client = ApexClient(config=config)
        assert client._config.base_url == "https://api.example.com"
        assert client._config.api_key == "key123"
        assert client._config.timeout_seconds == 10.0

    def test_client_config_used_in_requests(self) -> None:
        config = ApexConfig(
            base_url="https://api.example.com",
            api_key="key123",
        )
        client = ApexClient(config=config)
        client._connected = True
        with patch.object(client, "_make_request") as mock_req:
            mock_req.return_value = ApexResponse(status=200, data={})
            client.health()
            mock_req.assert_called_once()


if __name__ == "__main__":
    unittest.main()
