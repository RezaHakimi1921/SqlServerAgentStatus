"""Email and signed webhook delivery adapters for alert events.

The dispatcher does not read secrets or run on the Dash request thread. A worker
should fetch a destination's secret from the OS secret store, call deliver(),
then persist the result in MonitoringStore's outbox/attempt tables.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Callable, Dict, Optional


MAX_WEBHOOK_BODY_BYTES = 256 * 1024


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    status_code: Optional[int] = None
    sanitized_error: Optional[str] = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_text(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    return text[:limit]


def _safe_evidence(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        result = {}
        blocked = ("password", "secret", "token", "query", "sql",
                   "command", "connection_string", "physical_name", "credential")
        for key, item in value.items():
            safe_key = str(key)[:100]
            if any(part in safe_key.lower() for part in blocked):
                continue
            result[safe_key] = _safe_evidence(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_evidence(item, depth + 1) for item in value[:100]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(value, 500)


def _safe_link(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    # Query strings and fragments often carry access tokens and are not needed in alert links.
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def build_webhook_payload(event: Dict[str, Any]) -> bytes:
    """Build a bounded, redacted event payload; never include raw SQL/credentials."""
    payload = {
        "schema_version": "1.0",
        "event_id": event.get("event_id"),
        "event_type": event.get("rule_id", "alert"),
        "occurred_at_utc": event.get("first_seen_utc"),
        "last_seen_at_utc": event.get("last_seen_utc"),
        "severity": event.get("severity"),
        "status": event.get("status"),
        "instance": {
            "instance_id": event.get("instance_id"),
            "display_name": event.get("instance_name"),
            "environment": event.get("environment"),
        },
        "scope": _safe_evidence(event.get("scope", {})),
        "title": _safe_text(event.get("title"), 300),
        "summary": _safe_text(event.get("summary"), 2000),
        "evidence": _safe_evidence(event.get("evidence", {})),
        "dedup_key": event.get("dedup_key"),
        "url": _safe_link(event.get("url")),
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise ValueError("webhook payload exceeds the configured size limit")
    return body


class NotificationDispatcher:
    def __init__(
        self,
        *,
        smtp_factory: Optional[Callable[..., Any]] = None,
        smtp_ssl_factory: Optional[Callable[..., Any]] = None,
        urlopen: Optional[Callable[..., Any]] = None,
        timeout_seconds: int = 10,
    ) -> None:
        if timeout_seconds < 1 or timeout_seconds > 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        self.timeout_seconds = timeout_seconds
        self._smtp_factory = smtp_factory or smtplib.SMTP
        self._smtp_ssl_factory = smtp_ssl_factory or smtplib.SMTP_SSL
        self._urlopen = urlopen or self._build_urlopen()

    @staticmethod
    def _build_urlopen():
        opener = urllib.request.build_opener(_NoRedirect())
        return opener.open

    def deliver(self, target: Dict[str, Any], event: Dict[str, Any],
                *, secret: Optional[str] = None) -> DeliveryResult:
        channel = target.get("channel")
        config = target.get("config") or {}
        try:
            if channel == "email":
                return self._deliver_email(target, config, event, secret)
            if channel == "webhook":
                return self._deliver_webhook(config, event, secret)
            return DeliveryResult(False, sanitized_error="unsupported notification channel")
        except Exception as exc:  # never forward transport details/secrets to caller
            return DeliveryResult(False, sanitized_error=self._sanitize_exception(exc))

    @staticmethod
    def _sanitize_exception(exc: Exception) -> str:
        if isinstance(exc, (TimeoutError, smtplib.SMTPServerDisconnected)):
            return "notification transport timed out or disconnected"
        if isinstance(exc, urllib.error.HTTPError):
            return f"webhook returned HTTP {exc.code}"
        if isinstance(exc, urllib.error.URLError):
            return "webhook connection failed"
        if isinstance(exc, smtplib.SMTPAuthenticationError):
            return "SMTP authentication failed"
        if isinstance(exc, (ValueError, TypeError)):
            return _safe_text(exc, 300)
        return "notification delivery failed"

    def _deliver_email(self, target: Dict[str, Any], config: Dict[str, Any], event: Dict[str, Any],
                       secret: Optional[str]) -> DeliveryResult:
        host = str(config.get("host", "")).strip()
        port = int(config.get("port", 587))
        sender = str(config.get("from", "")).strip()
        recipients = config.get("to", [])
        if isinstance(recipients, str):
            recipients = [recipients]
        if not isinstance(recipients, (list, tuple)):
            raise ValueError("email recipients must be a list")
        recipients = [str(item).strip() for item in recipients if str(item).strip()]
        if not host or not sender or not recipients:
            raise ValueError("SMTP host, from and at least one recipient are required")
        if port < 1 or port > 65535:
            raise ValueError("invalid SMTP port")
        username = str(config.get("username", "")).strip()
        if username and not secret:
            raise ValueError("SMTP password is not configured in the secret store")

        message = EmailMessage()
        message["Subject"] = f"[{str(event.get('severity', 'info')).upper()}] {_safe_text(event.get('title'), 200)}"
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message_token = hashlib.sha256(
            f"{target.get('target_id', '')}:{event.get('event_id', '')}".encode("utf-8")
        ).hexdigest()
        message["Message-ID"] = f"<{message_token}@sqlserveragentstatus.local>"
        body = [
            f"Severity: {_safe_text(event.get('severity'))}",
            f"Server: {_safe_text(event.get('instance_name') or event.get('instance_id'))}",
            f"Status: {_safe_text(event.get('status'))}",
            f"First seen: {_safe_text(event.get('first_seen_utc'))}",
            f"Last seen: {_safe_text(event.get('last_seen_utc'))}",
            f"Title: {_safe_text(event.get('title'), 300)}",
            f"Summary: {_safe_text(event.get('summary'), 2000)}",
            f"URL: {_safe_text(_safe_link(event.get('url')) or '', 1000)}",
        ]
        message.set_content("\n".join(body))

        use_ssl = bool(config.get("use_ssl", False))
        starttls = bool(config.get("starttls", True))
        if not use_ssl and not starttls:
            raise ValueError("SMTP TLS is required")
        if use_ssl:
            client = self._smtp_ssl_factory(host, port, timeout=self.timeout_seconds,
                                            context=ssl.create_default_context())
        else:
            client = self._smtp_factory(host, port, timeout=self.timeout_seconds)
        try:
            if not use_ssl and starttls:
                client.starttls(context=ssl.create_default_context())
            if username:
                client.login(username, secret)
            client.send_message(message)
        finally:
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass
        return DeliveryResult(True, status_code=250)

    def _deliver_webhook(self, config: Dict[str, Any], event: Dict[str, Any],
                         secret: Optional[str]) -> DeliveryResult:
        url = str(config.get("url", "")).strip()
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("webhook URL must be HTTPS and must not contain embedded credentials")
        if not secret:
            raise ValueError("webhook HMAC secret is not configured in the secret store")

        body = build_webhook_payload(event)
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "SqlServerAgentStatus/0.1",
                "X-SqlAgent-Signature": f"sha256={signature}",
                "X-SqlAgent-Event-Id": _safe_text(event.get("event_id"), 100),
            },
            method="POST",
        )
        response = self._urlopen(request, timeout=self.timeout_seconds)
        try:
            status_value = getattr(response, "status", None)
            status = int(status_value if status_value is not None else response.getcode())
            if not 200 <= status < 300:
                return DeliveryResult(False, status_code=status,
                                      sanitized_error=f"webhook returned HTTP {status}")
            return DeliveryResult(True, status_code=status)
        finally:
            try:
                response.close()
            except Exception:
                pass
