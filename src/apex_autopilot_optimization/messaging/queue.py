"""Message queue implementation."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Message:
    """A message in the queue."""

    id: str
    topic: str
    payload: dict[str, Any]
    timestamp: str
    priority: int = 0
    headers: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueueConfig:
    """Configuration for a message queue."""

    name: str
    max_size: int = 1000
    durable: bool = False
    ttl_seconds: int = 3600


class MessageQueue:
    """In-process message queue with pub/sub semantics."""

    def __init__(self, config: QueueConfig) -> None:
        self._config = config
        self._queues: dict[str, deque[Message]] = defaultdict(deque)
        self._subscribers: dict[str, list[Callable[[Message], None]]] = defaultdict(list)
        self._published = 0
        self._delivered = 0

    def publish(self, message: Message) -> None:
        """Publish a message to its topic."""
        queue = self._queues[message.topic]
        if len(queue) >= self._config.max_size:
            raise RuntimeError(
                f"Queue '{message.topic}' is full (max_size={self._config.max_size})"
            )
        queue.append(message)
        self._published += 1
        for handler in self._subscribers.get(message.topic, []):
            handler(message)
            self._delivered += 1

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe a handler to a topic."""
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Unsubscribe a handler from a topic."""
        if topic in self._subscribers and handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)

    def get_queue_size(self, topic: str) -> int:
        """Get the number of undelivered messages for a topic."""
        return len(self._queues.get(topic, deque()))

    def get_queue_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        return {
            "published": self._published,
            "delivered": self._delivered,
            "topics": {t: len(q) for t, q in self._queues.items()},
            "subscribers": {t: len(s) for t, s in self._subscribers.items()},
        }

    def purge(self, topic: str) -> None:
        """Remove all messages for a topic."""
        if topic in self._queues:
            self._queues[topic].clear()

    def clear(self) -> None:
        """Remove all messages and reset stats."""
        self._queues.clear()
        self._published = 0
        self._delivered = 0
