"""ROS2 QoS profiles matching the telemetry contract (telemetry-contract.md).

The contract defines four named QoS presets:

    QOS_SENSOR      - best-effort reliability / volatile durability
                      (high-rate sensor streams: odometry, positions, telemetry)
    QOS_STATUS      - reliable reliability / volatile durability
                      (status / battery / GPS topics)
    QOS_MODE        - reliable reliability / transient-local durability
                      (mode / arming state; late joiners get the last value)
    QOS_AGGREGATE   - reliable reliability / transient-local durability
                      (/fleet/telemetry/aggregate)

This module deliberately has no rclpy dependency so the rest of the stack
can be imported and unit-tested without a ROS2 environment. Use
:func:`to_rclpy` to convert a profile when an rclpy node is available.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QoSProfile:
    """ROS2 QoS settings expressed as plain data.

    Attributes:
        reliability: "best_effort" or "reliable".
        durability: "volatile" or "transient_local".
        history: "keep_last" or "keep_all".
        depth: queue depth for keep_last history.
        deadline_sec: optional deadline duration in seconds.
        lifespan_sec: optional message lifespan in seconds.
        liveliness: "system_default", "manual_by_topic", or "automatic".
        liveliness_lease_sec: optional liveliness lease in seconds.
    """

    reliability: str
    durability: str
    history: str = "keep_last"
    depth: int = 10
    deadline_sec: float | None = None
    lifespan_sec: float | None = None
    liveliness: str = "system_default"
    liveliness_lease_sec: float | None = None

    def to_rclpy(self) -> object:
        """Convert to an :class:`rclpy.qos.QoSProfile` when rclpy is installed.

        Returns:
            An rclpy QoSProfile equivalent to this profile.

        Raises:
            ImportError: if rclpy is not installed.
        """
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            ReliabilityPolicy,
        )
        from rclpy.qos import (
            QoSProfile as RclpyQoS,
        )

        reliability = (
            ReliabilityPolicy.BEST_EFFORT
            if self.reliability == "best_effort"
            else ReliabilityPolicy.RELIABLE
        )
        durability = (
            DurabilityPolicy.VOLATILE
            if self.durability == "volatile"
            else DurabilityPolicy.TRANSIENT_LOCAL
        )
        history = HistoryPolicy.KEEP_LAST if self.history == "keep_last" else HistoryPolicy.KEEP_ALL
        return RclpyQoS(
            reliability=reliability,
            durability=durability,
            history=history,
            depth=self.depth,
        )


# Contract presets ───────────────────────────────────────────────────────────

QOS_SENSOR = QoSProfile(
    reliability="best_effort",
    durability="volatile",
    history="keep_last",
    depth=10,
)
QOS_STATUS = QoSProfile(
    reliability="reliable",
    durability="volatile",
    history="keep_last",
    depth=10,
)
QOS_MODE = QoSProfile(
    reliability="reliable",
    durability="transient_local",
    history="keep_last",
    depth=1,
)
QOS_AGGREGATE = QoSProfile(
    reliability="reliable",
    durability="transient_local",
    history="keep_last",
    depth=10,
)


# Topic -> QoS guidance used by the telemetry adapter.  Per the contract,
# vehicle telemetry and YOLO detections are sensor streams (QOS_SENSOR),
# while the fleet aggregate (QOS_AGGREGATE) and status/mode topics use
# reliable profiles with transient-local durability where late joiners
# must recover the latest state.
AGGREGATE_TOPIC = "/fleet/telemetry/aggregate"


def qos_for_topic(topic: str) -> QoSProfile:
    """Return the contract QoS profile for a topic.

    Args:
        topic: ROS2 topic name.

    Returns:
        The QoSProfile that matches the contract for that topic class,
        defaulting to QOS_SENSOR for unknown topics.
    """
    if topic == AGGREGATE_TOPIC:
        return QOS_AGGREGATE
    if topic.endswith("/telemetry/vehicle_telemetry") or topic.endswith("/yolo/detections"):
        return QOS_SENSOR
    if topic.endswith("/fmu/out/vehicle_status"):
        return QOS_STATUS
    if "/fmu/out/" in topic:
        return QOS_MODE
    return QOS_SENSOR
