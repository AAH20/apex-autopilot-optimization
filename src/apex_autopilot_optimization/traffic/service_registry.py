"""Service discovery and health tracking."""

from __future__ import annotations

import threading


class ServiceRegistry:
    """Registry for service instances with health tracking.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._services: dict[str, list[str]] = {}
        self._health: dict[tuple[str, str], bool] = {}
        self._lock = threading.Lock()

    def register(self, service_name: str, instance: str) -> None:
        """Register a service instance."""
        with self._lock:
            if service_name not in self._services:
                self._services[service_name] = []
            if instance not in self._services[service_name]:
                self._services[service_name].append(instance)
            self._health[(service_name, instance)] = True

    def deregister(self, service_name: str, instance: str) -> None:
        """Deregister a service instance."""
        with self._lock:
            if service_name in self._services:
                if instance in self._services[service_name]:
                    self._services[service_name].remove(instance)
                    self._health.pop((service_name, instance), None)
                if not self._services[service_name]:
                    del self._services[service_name]

    def discover(self, service_name: str) -> str | None:
        """Discover a healthy instance of a service."""
        with self._lock:
            if service_name not in self._services:
                return None
            instances = self._services[service_name]
            healthy = [
                i for i in instances if self._health.get((service_name, i), True)
            ]
            if healthy:
                return healthy[0]
            return instances[0] if instances else None

    def list_services(self) -> list[str]:
        """List all registered service names."""
        with self._lock:
            return list(self._services.keys())

    def health_check(self, service_name: str) -> bool:
        """Check if any instance of the service is healthy."""
        with self._lock:
            if service_name not in self._services:
                return False
            return any(
                self._health.get((service_name, i), True)
                for i in self._services[service_name]
            )

    def set_health(self, service_name: str, instance: str, healthy: bool) -> None:
        """Set health status for a specific instance."""
        with self._lock:
            self._health[(service_name, instance)] = healthy
