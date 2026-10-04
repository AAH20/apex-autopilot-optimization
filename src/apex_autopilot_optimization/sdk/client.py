"""SDK client for apex-autopilot-optimization."""

from __future__ import annotations

from typing import Any

from apex_autopilot_optimization.sdk.config import ApexConfig
from apex_autopilot_optimization.sdk.error import ApexError
from apex_autopilot_optimization.sdk.response import ApexResponse


class ApexClient:
    """Client for the Apex Autopilot Optimization API.

    Provides methods for planning, optimization, estimation, control,
    filtering, health checks, and diagnostics.
    """

    def __init__(self, config: ApexConfig | None = None) -> None:
        self._config = config or ApexConfig(base_url="", api_key="")
        self._connected = False

    def connect(self, url: str, api_key: str) -> ApexResponse:
        """Connect to the API server.

        Args:
            url: The base URL of the API server.
            api_key: API key for authentication.

        Returns:
            ApexResponse indicating success or failure.
        """
        self._config.base_url = url.rstrip("/")
        self._config.api_key = api_key
        resp = self._make_request("GET", "/health")
        if resp.is_success():
            self._connected = True
        return resp

    def disconnect(self) -> None:
        """Disconnect from the API server."""
        self._connected = False

    def is_connected(self) -> bool:
        """Return True if the client is connected."""
        return self._connected

    def plan(self, problem: dict[str, Any]) -> ApexResponse:
        """Submit a planning problem.

        Args:
            problem: Planning problem definition.

        Returns:
            ApexResponse with the planning result.
        """
        return self._make_request("POST", "/plan", body=problem)

    def optimize(self, problem: dict[str, Any]) -> ApexResponse:
        """Submit an optimization problem.

        Args:
            problem: Optimization problem definition.

        Returns:
            ApexResponse with the optimization result.
        """
        return self._make_request("POST", "/optimize", body=problem)

    def estimate(self, measurements: dict[str, Any]) -> ApexResponse:
        """Submit measurements for state estimation.

        Args:
            measurements: Sensor measurements.

        Returns:
            ApexResponse with the estimated state.
        """
        return self._make_request("POST", "/estimate", body=measurements)

    def control(self, state: dict[str, Any], target: dict[str, Any]) -> ApexResponse:
        """Compute control input for a given state and target.

        Args:
            state: Current state.
            target: Target state.

        Returns:
            ApexResponse with the control input.
        """
        body = {"state": state, "target": target}
        return self._make_request("POST", "/control", body=body)

    def filter(
        self,
        state: dict[str, Any],
        control: dict[str, Any],
        obstacles: list[dict[str, Any]],
    ) -> ApexResponse:
        """Apply safety filter to a control input.

        Args:
            state: Current state.
            control: Proposed control input.
            obstacles: List of obstacles.

        Returns:
            ApexResponse with the filtered control input.
        """
        body = {"state": state, "control": control, "obstacles": obstacles}
        return self._make_request("POST", "/filter", body=body)

    def health(self) -> ApexResponse:
        """Check API server health.

        Returns:
            ApexResponse with health status.
        """
        return self._make_request("GET", "/health")

    def diagnostics(self) -> ApexResponse:
        """Get API server diagnostics.

        Returns:
            ApexResponse with diagnostic information.
        """
        return self._make_request("GET", "/diagnostics")

    def _make_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> ApexResponse:
        """Make an HTTP request to the API server.

        This method should be overridden or mocked in tests.

        Args:
            method: HTTP method.
            path: Request path.
            body: Optional request body.

        Returns:
            ApexResponse from the server.

        Raises:
            ApexError: If the request fails.
        """
        raise ApexError("Network requests not implemented in base client")
