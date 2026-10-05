"""FaaS configuration dataclass."""

from dataclasses import dataclass


@dataclass
class FaaSConfig:
    """Configuration for a serverless/FaaS deployment.

    Attributes:
        provider: Cloud provider name (aws, azure, gcp).
        region: Deployment region.
        memory_mb: Memory allocation in MB.
        timeout_seconds: Maximum execution time in seconds.
        concurrency: Maximum concurrent executions.
    """

    provider: str = "aws"
    region: str = "us-east-1"
    memory_mb: int = 128
    timeout_seconds: int = 30
    concurrency: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")
        if not isinstance(self.region, str):
            raise TypeError("region must be a string")
        if not isinstance(self.memory_mb, int) or self.memory_mb <= 0:
            raise ValueError("memory_mb must be a positive integer")
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        if not isinstance(self.concurrency, int) or self.concurrency <= 0:
            raise ValueError("concurrency must be a positive integer")
