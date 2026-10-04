"""Network policy and firewall rule definitions with enforcement logic."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NetworkPolicy:
    """Allow/deny policy for network connections."""

    name: str
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_ports: list[int] = field(default_factory=list)
    denied_hosts: list[str] = field(default_factory=list)
    denied_ports: list[int] = field(default_factory=list)


def check_allowed(policy: NetworkPolicy, host: str, port: int) -> bool:
    """Check whether a connection to (host, port) is permitted by the policy.

    Deny rules take precedence. If allow lists are non-empty, the host/port
    must be present in them.
    """
    if host in policy.denied_hosts:
        return False
    if port in policy.denied_ports:
        return False
    if policy.allowed_hosts and host not in policy.allowed_hosts:
        return False
    if policy.allowed_ports and port not in policy.allowed_ports:
        return False
    return True


@dataclass
class FirewallRule:
    """A single firewall rule matching traffic flows."""

    action: str
    protocol: str
    source: str
    destination: str
    port: int

    def matches(self, source: str, destination: str, port: int, protocol: str) -> bool:
        """Return True if the given flow matches this rule exactly."""
        return (
            self.source == source
            and self.destination == destination
            and self.port == port
            and self.protocol == protocol
        )
