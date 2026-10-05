"""Fog node: aggregation and task offloading across edge nodes."""
from __future__ import annotations

import threading
from typing import Any

from apex_autopilot_optimization.edge.node import EdgeNode


class FogNode:
    """A fog computing layer sitting between edge nodes and the cloud.

    Responsibilities:
        * maintain a registry of edge nodes,
        * aggregate pending data across all registered nodes,
        * offload tasks to specific edge nodes.
    """

    def __init__(self, fog_id: str) -> None:
        if not isinstance(fog_id, str) or not fog_id.strip():
            raise ValueError("fog_id must be a non-empty string")
        self.fog_id = fog_id
        self._nodes: dict[str, EdgeNode] = {}
        self._tasks: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------
    def register_edge_node(self, node: EdgeNode) -> bool:
        """Register an edge node. Returns False if already registered."""
        node_id = node.config.node_id
        with self._lock:
            if node_id in self._nodes:
                return False
            self._nodes[node_id] = node
            self._tasks[node_id] = []
        return True

    def unregister_edge_node(self, node_id: str) -> bool:
        """Remove an edge node. Returns False if it was not registered."""
        with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            del self._tasks[node_id]
        return True

    def get_edge_nodes(self) -> list[EdgeNode]:
        """Return all registered edge nodes."""
        with self._lock:
            return list(self._nodes.values())

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    def aggregate_data(self) -> dict[str, Any]:
        """Aggregate pending sensor data across all registered nodes.

        Returns per-node record counts, total record count, and the mean
        of any numeric ``value`` field found in the buffered records.
        """
        per_node: dict[str, int] = {}
        values: list[float] = []
        with self._lock:
            nodes = list(self._nodes.values())
        for node in nodes:
            pending = node.get_pending_data()
            per_node[node.config.node_id] = len(pending)
            for record in pending:
                value = record.get("value")
                if isinstance(value, int | float):
                    values.append(float(value))
        return {
            "fog_id": self.fog_id,
            "node_count": len(nodes),
            "per_node_records": per_node,
            "total_records": sum(per_node.values()),
            "mean_value": (sum(values) / len(values)) if values else None,
        }

    # ------------------------------------------------------------------
    # Task offloading
    # ------------------------------------------------------------------
    def offload_task(self, task: dict[str, Any], node_id: str) -> dict[str, Any]:
        """Assign ``task`` to the edge node identified by ``node_id``.

        Raises KeyError if no node with that id is registered, or
        ValueError if the task is not a mapping.
        """
        if not isinstance(task, dict):
            raise ValueError("task must be a dict")
        with self._lock:
            if node_id not in self._nodes:
                raise KeyError(f"edge node {node_id!r} is not registered")
            assignment = {
                "task_id": task.get("id"),
                "assigned_to": node_id,
                "status": "assigned",
            }
            self._tasks[node_id].append(assignment)
        return assignment

    def get_tasks(self, node_id: str | None = None) -> list[dict[str, Any]]:
        """Return tasks assigned to one node, or all tasks if node_id is None."""
        with self._lock:
            if node_id is not None:
                return list(self._tasks.get(node_id, []))
            return [t for tasks in self._tasks.values() for t in tasks]
