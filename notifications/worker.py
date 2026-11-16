"""Outbox worker for Email/Webhook alert delivery.

Call run_once() from a controlled background worker/scheduler, never from a
Dash callback. No destination is contacted unless a delivery was queued.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from fleet.store import MonitoringStore
from notifications.dispatcher import NotificationDispatcher


SecretProvider = Callable[[str], str]


def keyring_secret_provider(target_id: str) -> str:
    from secrets_store import get_notification_secret
    return get_notification_secret(target_id)


class NotificationWorker:
    def __init__(self, store: MonitoringStore,
                 dispatcher: Optional[NotificationDispatcher] = None,
                 secret_provider: SecretProvider = keyring_secret_provider,
                 max_attempts: int = 5) -> None:
        self.store = store
        self.dispatcher = dispatcher or NotificationDispatcher()
        self.secret_provider = secret_provider
        self.max_attempts = max(1, int(max_attempts))

    def run_once(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        stale_before = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.store.recover_stale_sending(stale_before_utc=stale_before)
        deliveries = self.store.claim_notifications(limit=limit)
        for delivery in deliveries:
            started_at = delivery["updated_at_utc"]
            try:
                target = self.store.get_notification_target(delivery["target_id"])
                event = self.store.get_alert(delivery["event_id"])
                if target is None or event is None:
                    result = None
                else:
                    secret = self.secret_provider(delivery["target_id"])
                    result = self.dispatcher.deliver(target, event, secret=secret)
            except Exception:
                result = None

            outcome = self.store.record_delivery_attempt(
                delivery["delivery_id"],
                success=bool(result and result.success),
                status_code=result.status_code if result else None,
                sanitized_error=(result.sanitized_error if result else "notification worker failed"),
                max_attempts=self.max_attempts,
                started_at_utc=started_at,
            )
            results.append(outcome)
        return results
