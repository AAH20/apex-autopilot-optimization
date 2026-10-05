"""Secret store implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SecretStore(ABC):
    """Abstract base class for secret storage backends."""

    @abstractmethod
    def store(self, key: str, value: bytes) -> None:
        """Store a secret value under the given key."""
        ...

    @abstractmethod
    def get(self, key: str) -> bytes | None:
        """Retrieve a secret value by key, or None if not found."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a secret by key."""
        ...

    @abstractmethod
    def list_secrets(self) -> list[str]:
        """List all stored secret keys."""
        ...


class InMemorySecretStore(SecretStore):
    """In-memory implementation of SecretStore."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def store(self, key: str, value: bytes) -> None:
        self._data[key] = value

    def get(self, key: str) -> bytes | None:
        return self._data.get(key)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def list_secrets(self) -> list[str]:
        return list(self._data.keys())
