"""SDK response dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast


@dataclass
class ApexResponse:
    """Represents an API response.

    Attributes:
        status: HTTP status code.
        data: Response body as a dict.
        headers: Response headers.
        request_id: Unique request identifier for tracing.
    """

    status: int
    data: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    request_id: str = ""

    def is_success(self) -> bool:
        """Return True if the response indicates success (2xx status)."""
        return 200 <= self.status < 300

    def get_error(self) -> str | None:
        """Return the error message if the response indicates an error."""
        if self.is_success():
            return None
        return cast(str, self.data.get("error", "Unknown error"))
