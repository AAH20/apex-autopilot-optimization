"""API request dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class APIRequest:
    """Represents an incoming API request.

    Attributes:
        method: HTTP method (GET, POST, PUT, DELETE, etc.).
        path: Request path.
        headers: Request headers.
        body: Request body as a dict.
        query_params: Query parameters as a dict.
        user: Authenticated user identifier, or None if unauthenticated.
    """

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    user: str | None = None
