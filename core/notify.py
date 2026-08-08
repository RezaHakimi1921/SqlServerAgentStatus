"""Notification channel stubs — email wired in a later phase.

Insights (V2) should emit events through `notify()`. SMTP delivery is optional
and must not block Insight Discovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from core.logging_setup import get_logger

log = get_logger("sqlmonitor.notify")


@dataclass
class NotifyEvent:
    """Minimal event shape for Insight → channel."""

    severity: str  # info | warning | critical
    title: str
    body: str
    rule_id: str = ""
    target_key: str = ""  # per-target cooldown key (e.g. job:BackupNightly)
    meta: Dict[str, Any] = field(default_factory=dict)


class Notifier(Protocol):
    def send(self, event: NotifyEvent) -> bool: ...


class LogNotifier:
    """Default backend — logs only. Safe for V1/V2 without SMTP."""

    def send(self, event: NotifyEvent) -> bool:
        log.info(
            "notify [%s] %s | %s | rule=%s target=%s",
            event.severity,
            event.title,
            event.body,
            event.rule_id,
            event.target_key,
        )
        return True


class EmailNotifier:
    """SMTP stub — not configured until the email phase.

    Keep settings keys ready: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM, SMTP_TO. Implementation fills send() later.
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        self.enabled = bool(self.settings.get("SMTP_HOST") and self.settings.get("SMTP_TO"))

    def send(self, event: NotifyEvent) -> bool:
        if not self.enabled:
            log.debug("email notifier disabled (no SMTP config)")
            return False
        if (event.severity or "").lower() != "critical":
            # Product rule: only Critical emails when channel is on
            return False
        # Placeholder — real SMTP in email phase
        log.warning("email notifier not implemented yet: %s", event.title)
        return False


_default: Notifier = LogNotifier()


def get_notifier() -> Notifier:
    return _default


def notify(event: NotifyEvent) -> bool:
    return get_notifier().send(event)
