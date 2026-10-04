"""SQLite database wrapper for persistence layer."""
from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


class Database:
    """Thin wrapper around sqlite3 with transaction support."""

    def __init__(self) -> None:
        self._connection: sqlite3.Connection | None = None

    def connect(self, path: str) -> None:
        """Connect to a SQLite database file."""
        self._connection = sqlite3.connect(path)

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        """Execute a SQL query."""
        if self._connection is None:
            raise RuntimeError("Database not connected")
        self._connection.execute(query, params)

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Execute a query and return all rows."""
        if self._connection is None:
            raise RuntimeError("Database not connected")
        cursor = self._connection.execute(query, params)
        return cursor.fetchall()

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        """Execute a query and return the first row."""
        if self._connection is None:
            raise RuntimeError("Database not connected")
        cursor = self._connection.execute(query, params)
        return cursor.fetchone()

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager for database transactions."""
        if self._connection is None:
            raise RuntimeError("Database not connected")
        try:
            yield
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
