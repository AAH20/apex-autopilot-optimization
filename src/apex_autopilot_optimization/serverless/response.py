"""FaaS response dataclass with cloud-provider format conversion."""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FaaSResponse:
    """Standardized response from a FaaS handler.

    Attributes:
        status_code: HTTP status code.
        body: Response body as a dict.
        headers: Response headers.
    """

    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)

    def to_lambda_response(self) -> dict[str, Any]:
        """Convert to AWS Lambda proxy integration response format.

        Returns:
            Dict with statusCode, headers, and JSON-string body.
        """
        return {
            "statusCode": self.status_code,
            "headers": self.headers,
            "body": json.dumps(self.body),
        }

    def to_azure_response(self) -> dict[str, Any]:
        """Convert to Azure Functions HTTP response format.

        Returns:
            Dict with status_code, body, and headers.
        """
        return {
            "status_code": self.status_code,
            "body": self.body,
            "headers": self.headers,
        }

    def to_gcp_response(self) -> dict[str, Any]:
        """Convert to GCP Cloud Functions HTTP response format.

        Returns:
            Dict with status_code, body, and headers.
        """
        return {
            "status_code": self.status_code,
            "body": self.body,
            "headers": self.headers,
        }
