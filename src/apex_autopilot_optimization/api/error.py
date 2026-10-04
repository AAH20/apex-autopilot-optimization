"""API error types."""

from __future__ import annotations

from typing import Any


class APIError(Exception):
    """Exception raised for API errors.

    Attributes:
        status_code: HTTP status code for the error.
        message: Human-readable error message.
        details: Optional additional error details.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details
