"""Load balancing: strategies and backend management."""

from __future__ import annotations

import random
import threading
from typing import Protocol


class Strategy(Protocol):
    """Protocol for load balancing strategies."""

    def select(
        self, backends: list[str], connections: dict[str, int] | None = None
    ) -> str:
        ...


class RoundRobinStrategy:
    """Cycles through backends in order."""

    def __init__(self) -> None:
        self._index = 0

    def select(
        self, backends: list[str], connections: dict[str, int] | None = None
    ) -> str:
        if not backends:
            raise RuntimeError("No backends available")
        backend = backends[self._index % len(backends)]
        self._index += 1
        return backend


class LeastConnectionsStrategy:
    """Selects the backend with the fewest active connections."""

    def select(
        self, backends: list[str], connections: dict[str, int] | None = None
    ) -> str:
        if not backends:
            raise RuntimeError("No backends available")
        if connections:
            return min(backends, key=lambda b: connections.get(b, 0))
        return backends[0]


class RandomStrategy:
    """Selects a backend uniformly at random."""

    def select(
        self, backends: list[str], connections: dict[str, int] | None = None
    ) -> str:
        if not backends:
            raise RuntimeError("No backends available")
        return random.choice(backends)


class LoadBalancer:
    """Distributes requests across backends using a strategy.

    Tracks backend health and active connections. Thread-safe.
    """

    def __init__(self, strategy: Strategy | None = None) -> None:
        self._backends: list[str] = []
        self._healthy: dict[str, bool] = {}
        self._connections: dict[str, int] = {}
        self._strategy: Strategy = strategy or RoundRobinStrategy()
        self._lock = threading.Lock()

    def add_backend(self, backend: str) -> None:
        """Add a backend to the pool."""
        with self._lock:
            if backend not in self._backends:
                self._backends.append(backend)
                self._healthy[backend] = True
                self._connections[backend] = 0

    def remove_backend(self, backend: str) -> None:
        """Remove a backend from the pool."""
        with self._lock:
            if backend in self._backends:
                self._backends.remove(backend)
                self._healthy.pop(backend, None)
                self._connections.pop(backend, None)

    def get_all_backends(self) -> list[str]:
        """Return all registered backends."""
        with self._lock:
            return list(self._backends)

    def get_healthy_backends(self) -> list[str]:
        """Return only healthy backends."""
        with self._lock:
            return [b for b in self._backends if self._healthy[b]]

    def set_backend_health(self, backend: str, healthy: bool) -> None:
        """Set health status for a backend."""
        with self._lock:
            if backend in self._healthy:
                self._healthy[backend] = healthy

    def increment_connections(self, backend: str) -> None:
        """Increment active connection count for a backend."""
        with self._lock:
            if backend in self._connections:
                self._connections[backend] += 1

    def release_connection(self, backend: str) -> None:
        """Decrement active connection count for a backend."""
        with self._lock:
            if backend in self._connections and self._connections[backend] > 0:
                self._connections[backend] -= 1

    def get_backend(self) -> str:
        """Select a backend using the configured strategy."""
        with self._lock:
            healthy = self.get_healthy_backends()
            return self._strategy.select(healthy, self._connections)
