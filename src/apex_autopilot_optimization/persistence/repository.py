"""Repository pattern for entity persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from apex_autopilot_optimization.persistence.database import Database


class Repository(ABC):
    """Abstract base class for entity repositories."""

    @abstractmethod
    def save(self, entity: dict[str, Any]) -> int:
        """Save an entity and return its ID."""
        ...

    @abstractmethod
    def get(self, id: int) -> dict[str, Any] | None:
        """Get an entity by ID."""
        ...

    @abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        """List all entities."""
        ...

    @abstractmethod
    def delete(self, id: int) -> None:
        """Delete an entity by ID."""
        ...

    @abstractmethod
    def update(self, entity: dict[str, Any]) -> None:
        """Update an entity."""
        ...


class PlanningResultRepository(Repository):
    """Repository for planning results stored in SQLite."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, entity: dict[str, Any]) -> int:
        """Save a planning result and return its ID."""
        self.db.execute(
            "INSERT INTO planning_results (success, cost, message) VALUES (?, ?, ?)",
            (entity.get("success", False), entity.get("cost", 0.0), entity.get("message", "")),
        )
        row = self.db.fetchone("SELECT last_insert_rowid()")
        assert row is not None
        return int(row[0])

    def get(self, id: int) -> dict[str, Any] | None:
        """Get a planning result by ID."""
        row = self.db.fetchone(
            "SELECT id, success, cost, message FROM planning_results WHERE id = ?", (id,)
        )
        if row is None:
            return None
        return {"id": row[0], "success": bool(row[1]), "cost": row[2], "message": row[3]}

    def list_all(self) -> list[dict[str, Any]]:
        """List all planning results."""
        rows = self.db.fetchall("SELECT id, success, cost, message FROM planning_results")
        return [
            {"id": row[0], "success": bool(row[1]), "cost": row[2], "message": row[3]}
            for row in rows
        ]

    def delete(self, id: int) -> None:
        """Delete a planning result by ID."""
        self.db.execute("DELETE FROM planning_results WHERE id = ?", (id,))

    def update(self, entity: dict[str, Any]) -> None:
        """Update a planning result."""
        self.db.execute(
            "UPDATE planning_results SET success = ?, cost = ?, message = ? WHERE id = ?",
            (
                entity.get("success", False),
                entity.get("cost", 0.0),
                entity.get("message", ""),
                entity["id"],
            ),
        )
