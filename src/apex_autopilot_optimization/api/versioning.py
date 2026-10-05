"""API versioning support."""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import Enum

from apex_autopilot_optimization.api.request import APIRequest
from apex_autopilot_optimization.api.response import APIResponse


class APIVersion(Enum):
    """Supported API versions."""

    V1 = "v1"
    V2 = "v2"


def version_route(
    version: APIVersion, path: str
) -> Callable[[Callable[[APIRequest], APIResponse]], Callable[[APIRequest], APIResponse]]:
    """Decorator that tags a handler with a version and path.

    The decorated function is returned unchanged; the version and path
    are stored as attributes for introspection.

    Usage:
        @version_route(APIVersion.V1, "/status")
        def status_handler(request):
            return APIResponse.success({"version": "v1"})
    """

    def decorator(func: Callable[[APIRequest], APIResponse]) -> Callable[[APIRequest], APIResponse]:
        func._api_version = version  # type: ignore[attr-defined]
        func._api_path = path  # type: ignore[attr-defined]
        return func

    return decorator


def get_version(path: str) -> APIVersion | None:
    """Extract the API version from a path.

    Returns APIVersion.V1 for "/v1/...", APIVersion.V2 for "/v2/...",
    or None if no version prefix is found.
    """
    match = re.search(r"/v(\d+)(?:/|$)", path)
    if match is None:
        return None
    version_num = match.group(1)
    for v in APIVersion:
        if v.value == f"v{version_num}":
            return v
    return None
