"""Webhook event delivery with HMAC-SHA256 signature verification."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class WebhookEvent:
    """A webhook event with type, payload, timestamp, and signature."""

    event_type: str
    payload: dict[str, Any]
    timestamp: float
    signature: str

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: dict[str, Any],
        secret: str = "",
    ) -> WebhookEvent:
        """Create a webhook event, signing it when a secret is provided."""
        timestamp = time.time()
        signature = ""
        if secret:
            body = json.dumps(payload, sort_keys=True).encode()
            signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return cls(
            event_type=event_type,
            payload=payload,
            timestamp=timestamp,
            signature=signature,
        )


class WebhookManager:
    """Register webhook subscriptions and dispatch signed events to them."""

    def __init__(self, secret: str = "") -> None:
        self._secret = secret
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._delivery_handler: Callable[[dict[str, Any], WebhookEvent], None] | None = None
        self._delivery_stats: dict[str, Any] = {
            "total_deliveries": 0,
            "failed_deliveries": 0,
            "per_subscription": {},
        }

    def register(self, url: str, events: list[str]) -> str:
        """Register a webhook URL for the given event types."""
        sub_id = str(uuid.uuid4())
        self._subscriptions[sub_id] = {"url": url, "events": events}
        self._delivery_stats["per_subscription"][sub_id] = 0
        return sub_id

    def unregister(self, subscription_id: str) -> None:
        """Remove a webhook subscription by ID."""
        del self._subscriptions[subscription_id]
        self._delivery_stats["per_subscription"].pop(subscription_id, None)

    def dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        """Create a signed event and deliver it to all matching subscriptions."""
        event = WebhookEvent.create(event_type, payload, secret=self._secret)
        for sub_id, sub in self._subscriptions.items():
            if "*" in sub["events"] or event_type in sub["events"]:
                self._deliver(sub_id, sub, event)

    def get_subscriptions(self) -> dict[str, dict[str, Any]]:
        """Return all registered subscriptions."""
        return dict(self._subscriptions)

    def get_delivery_stats(self) -> dict[str, Any]:
        """Return delivery statistics."""
        return {
            "total_deliveries": self._delivery_stats["total_deliveries"],
            "failed_deliveries": self._delivery_stats["failed_deliveries"],
            "per_subscription": dict(self._delivery_stats["per_subscription"]),
        }

    def verify_signature(self, payload: dict[str, Any], signature: str, secret: str) -> bool:
        """Verify an HMAC-SHA256 signature against a payload and secret."""
        if not signature:
            return False
        body = json.dumps(payload, sort_keys=True).encode()
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def set_delivery_handler(
        self,
        handler: Callable[[dict[str, Any], WebhookEvent], None],
    ) -> None:
        """Set the callable used to deliver events to subscriptions."""
        self._delivery_handler = handler

    def _deliver(self, sub_id: str, sub: dict[str, Any], event: WebhookEvent) -> None:
        self._delivery_stats["total_deliveries"] += 1
        self._delivery_stats["per_subscription"][sub_id] += 1
        if self._delivery_handler is not None:
            try:
                self._delivery_handler(sub, event)
            except Exception:
                self._delivery_stats["failed_deliveries"] += 1
