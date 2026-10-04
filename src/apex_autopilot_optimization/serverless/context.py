"""FaaS context dataclass."""

import uuid
from dataclasses import dataclass, field


@dataclass
class FaaSContext:
    """Execution context for a FaaS invocation.

    Attributes:
        request_id: Unique identifier for this request.
        function_name: Name of the executing function.
        memory_limit_mb: Memory limit for this invocation.
        time_remaining_ms: Remaining execution time in milliseconds.
        trace_id: Distributed tracing identifier.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    function_name: str = "unknown"
    memory_limit_mb: int = 128
    time_remaining_ms: int = 30000
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
