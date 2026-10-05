"""Edge node: sensing, local inference, and store-and-forward buffering."""

from __future__ import annotations

import threading
import time
from typing import Any

from apex_autopilot_optimization.edge.ai import EdgeAI
from apex_autopilot_optimization.edge.config import EdgeConfig


class EdgeNode:
    """A single edge computing node.

    Responsibilities:
        * maintain connectivity state with the cloud,
        * ingest and timestamp sensor data,
        * run on-device AI inference via :class:`EdgeAI`,
        * buffer data locally and forward it when connected
          (store-and-forward with a bounded, oldest-dropped buffer).
    """

    def __init__(self, config: EdgeConfig, ai: EdgeAI | None = None) -> None:
        self.config = config
        self._ai = ai if ai is not None else EdgeAI()
        self._connected = False
        self._buffer: list[dict[str, Any]] = []
        self._dropped = 0
        self._forwarded = 0
        self._sequence = 0
        self._last_connect_time: float | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Mark the node as connected to the cloud."""
        with self._lock:
            self._connected = True
            self._last_connect_time = time.time()
        return True

    def disconnect(self) -> bool:
        """Mark the node as disconnected. Buffered data is retained."""
        with self._lock:
            was_connected = self._connected
            self._connected = False
        return was_connected

    def is_connected(self) -> bool:
        """Return True if the node is currently connected."""
        with self._lock:
            return self._connected

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of node status and buffer statistics."""
        with self._lock:
            return {
                "node_id": self.config.node_id,
                "connected": self._connected,
                "offline_mode": self.config.offline_mode,
                "power_profile": self.config.power_profile,
                "buffer_size": len(self._buffer),
                "max_buffer_size": self.config.max_buffer_size,
                "dropped_records": self._dropped,
                "forwarded_records": self._forwarded,
                "model_loaded": self._ai.is_model_loaded(),
                "last_connect_time": self._last_connect_time,
            }

    # ------------------------------------------------------------------
    # Sensor data ingestion
    # ------------------------------------------------------------------
    def process_sensor_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate, timestamp, and buffer a sensor reading.

        The record is appended to the store-and-forward buffer. When the
        buffer is full the oldest record is dropped (and counted).
        Raises ValueError if ``data`` is not a mapping.
        """
        if not isinstance(data, dict):
            raise ValueError("sensor data must be a dict")
        with self._lock:
            self._sequence += 1
            record = dict(data)
            record.update(
                {
                    "node_id": self.config.node_id,
                    "sequence": self._sequence,
                    "timestamp": time.time(),
                }
            )
            self._buffer.append(record)
            if len(self._buffer) > self.config.max_buffer_size:
                self._buffer.pop(0)
                self._dropped += 1
        return record

    def get_pending_data(self) -> list[dict[str, Any]]:
        """Return a copy of the records currently waiting to be forwarded."""
        with self._lock:
            return list(self._buffer)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def run_inference(self, model: str, input_data: Any) -> dict[str, Any]:
        """Run inference for ``model`` against ``input_data``.

        The model must already be loaded in this node's EdgeAI and must
        match ``model``. Raises RuntimeError otherwise.
        """
        info = self._ai.get_model_info()
        if info is None or info.get("path") != model:
            raise RuntimeError(f"model {model!r} is not loaded on node {self.config.node_id!r}")
        return self._ai.run_inference(input_data)

    # ------------------------------------------------------------------
    # Store and forward
    # ------------------------------------------------------------------
    def store_and_forward(self, data: dict[str, Any]) -> int:
        """Buffer ``data`` and forward the buffer when connected.

        Returns the number of records forwarded (0 when offline or
        disconnected — records remain buffered for the next attempt).
        """
        self.process_sensor_data(data)
        with self._lock:
            if not self._connected or self.config.offline_mode:
                return 0
            forwarded = len(self._buffer)
            self._buffer.clear()
            self._forwarded += forwarded
        return forwarded
