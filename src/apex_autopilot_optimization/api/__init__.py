"""API layer for apex-autopilot-optimization."""

from apex_autopilot_optimization.api.auth import APIKeyAuth, require_auth
from apex_autopilot_optimization.api.error import APIError
from apex_autopilot_optimization.api.request import APIRequest
from apex_autopilot_optimization.api.response import APIResponse
from apex_autopilot_optimization.api.router import APIRouter, api_route
from apex_autopilot_optimization.api.versioning import APIVersion, get_version, version_route

__all__ = [
    "APIRouter",
    "APIRequest",
    "APIResponse",
    "APIError",
    "APIVersion",
    "APIKeyAuth",
    "api_route",
    "require_auth",
    "version_route",
    "get_version",
]
