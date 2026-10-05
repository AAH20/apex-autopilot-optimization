"""API authentication — decorator and key management."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from functools import wraps

from apex_autopilot_optimization.api.request import APIRequest
from apex_autopilot_optimization.api.response import APIResponse


def require_auth(func: Callable[[APIRequest], APIResponse]) -> Callable[[APIRequest], APIResponse]:
    """Decorator that rejects requests with no authenticated user.

    If request.user is None, returns 401 Unauthorized.
    Otherwise, calls the wrapped handler.
    """

    @wraps(func)
    def wrapper(request: APIRequest) -> APIResponse:
        if request.user is None:
            return APIResponse.unauthorized("Authentication required")
        return func(request)

    return wrapper


class APIKeyAuth:
    """Manages API keys for authentication.

    Keys are stored in memory. Use generate_key() to create,
    validate_key() to check, and revoke_key() to invalidate.
    """

    def __init__(self) -> None:
        self._keys: set[str] = set()

    def generate_key(self) -> str:
        """Generate and store a new API key."""
        key = secrets.token_urlsafe(32)
        self._keys.add(key)
        return key

    def validate_key(self, key: str) -> bool:
        """Check if a key is valid (previously generated and not revoked)."""
        return key in self._keys

    def revoke_key(self, key: str) -> None:
        """Revoke a key so it can no longer be used."""
        self._keys.discard(key)
