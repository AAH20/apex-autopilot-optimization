"""SDK configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApexConfig:
    """Configuration for the ApexClient.

    Attributes:
        base_url: The base URL of the API server.
        api_key: API key for authentication.
        timeout_seconds: Request timeout in seconds.
        max_retries: Maximum number of retries for failed requests.
        verify_ssl: Whether to verify SSL certificates.
    """

    base_url: str
    api_key: str
    timeout_seconds: float = 30.0
    max_retries: int = 3
    verify_ssl: bool = True
