"""API response dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class APIResponse:
    """Represents an API response.

    Attributes:
        status: HTTP status code.
        body: Response body as a dict.
        headers: Response headers.
    """

    status: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def success(cls, data: dict[str, Any], status: int = 200) -> APIResponse:
        """Create a successful response."""
        return cls(status=status, body=data)

    @classmethod
    def error(cls, message: str, status: int = 400) -> APIResponse:
        """Create an error response."""
        return cls(status=status, body={"error": message})

    @classmethod
    def not_found(cls, message: str = "Not found") -> APIResponse:
        """Create a 404 Not Found response."""
        return cls(status=404, body={"error": message})

    @classmethod
    def unauthorized(cls, message: str = "Unauthorized") -> APIResponse:
        """Create a 401 Unauthorized response."""
        return cls(status=401, body={"error": message})
