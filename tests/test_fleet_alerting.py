import hashlib
import hmac
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from fleet.service import FleetService
from fleet.store import MonitoringStore
from notifications.dispatcher import NotificationDispatcher
from notifications.worker import NotificationWorker


class _Cursor:
    timeout = None

    def execute(self, _sql):
        return self

    def fetchone(self):
        return ("SQL01", "16.0.1000", "msdb")

    def close(self):
        pass


class _Connection:
    def cursor(self):
        return _Cursor()

    def close(self):
        pass


class MonitoringStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MonitoringStore(Path(self.tmp.name) / "monitoring.sqlite3")
        self.instance = self.store.add_instance(
            display_name="Production SQL",
            server="sql01.example.test",
            database_name="msdb",
            user_name="monitor",
            instance_id="prod-1",
            environment="production",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_per_instance_health_and_fleet_summary(self):
        self.store.record_health("prod-1", status="healthy", server_name="SQL01", product_version="16.0")
        self.store.record_health("prod-1", status="unreachable", error_code="timeout",
                                 error_summary="Connection timed out")
        [server] = self.store.list_instances()
        self.assertEqual(server["health_status"], "unreachable")
        self.assertIsNotNone(server["last_success_at_utc"])
        self.assertEqual(len(self.store.list_health_checks("prod-1")), 2)
        summary = self.store.fleet_summary()
        self.assertEqual(summary["instances"]["unreachable"], 1)

    def test_repeated_observation_updates_one_open_alert(self):
        first = self.store.upsert_alert(
            dedup_key="prod-1:connection:timeout", rule_id="connection_timeout",
            severity="critical", title="Server unavailable", summary="Probe failed",
            instance_id="prod-1", evidence={"count": 1},
        )
        second = self.store.upsert_alert(
            dedup_key="prod-1:connection:timeout", rule_id="connection_timeout",
            severity="critical", title="Server unavailable", summary="Probe still failing",
            instance_id="prod-1", evidence={"count": 2},
        )
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(second["occurrences"], 2)
        self.assertEqual(second["evidence"], {"count": 2})
        self.assertTrue(self.store.resolve_alert(first["event_id"]))
        third = self.store.upsert_alert(
            dedup_key="prod-1:connection:timeout", rule_id="connection_timeout",
            severity="critical", title="Server unavailable", summary="Failure recurred",
            instance_id="prod-1",
        )
        self.assertNotEqual(first["event_id"], third["event_id"])

    def test_secret_fields_are_rejected_from_target_metadata(self):
        with self.assertRaises(ValueError):
            self.store.add_notification_target(
                channel="webhook", name="Ops", config={"url": "https://example.test", "secret": "oops"}
            )

    def test_outbox_is_durable_and_retries_with_backoff(self):
        event = self.store.upsert_alert(
            dedup_key="prod-1:job:backup", rule_id="job_failure", severity="high",
            title="Backup failed", summary="Job failed", instance_id="prod-1",
        )
        target = self.store.add_notification_target(
            channel="webhook", name="Ops", config={"url": "https://hooks.example.test/alerts"}
        )
        self.assertTrue(self.store.enqueue_notification(event["event_id"], target["target_id"]))
        self.assertFalse(self.store.enqueue_notification(event["event_id"], target["target_id"]))
        [delivery] = self.store.claim_notifications()
        attempt_time = datetime.now(timezone.utc)
        failed = self.store.record_delivery_attempt(
            delivery["delivery_id"], success=False, status_code=503,
            sanitized_error="webhook returned HTTP 503", now=attempt_time,
        )
        self.assertEqual(failed["status"], "retry")
        self.assertEqual(failed["attempt_count"], 1)
        self.assertEqual(self.store.claim_notifications(now_utc=attempt_time.isoformat()), [])
        [retry] = self.store.claim_notifications(now_utc=failed["next_attempt_at_utc"])
        final = self.store.record_delivery_attempt(retry["delivery_id"], success=True, status_code=204)
        self.assertEqual(final["status"], "delivered")

    def test_probe_all_isolates_instance_failures(self):
        other = self.store.add_instance(
            display_name="Staging SQL", server="sql02.example.test", database_name="msdb",
            user_name="monitor", instance_id="stage-1", environment="staging",
        )

        def factory_builder(instance):
            if instance["instance_id"] == "stage-1":
                def fail():
                    raise RuntimeError("08S01: secret must never escape")
                return fail
            return _Connection

        service = FleetService(self.store, connection_factory_builder=factory_builder)
        results = service.probe_enabled_instances()
        self.assertEqual([row["status"] for row in results], ["healthy", "degraded"])
        self.assertNotIn("secret", results[1]["error_summary"])
        states = {row["instance_id"]: row["health_status"] for row in self.store.list_instances()}
        self.assertEqual(states["prod-1"], "healthy")
        self.assertEqual(states["stage-1"], "degraded")

    def test_unreachable_requires_three_consecutive_connection_failures(self):
        def failing_builder(_instance):
            def fail():
                raise RuntimeError("08S01: sensitive driver detail")
            return fail

        service = FleetService(self.store, connection_factory_builder=failing_builder)
        self.assertEqual(service.probe_instance("prod-1")["status"], "degraded")
        self.assertEqual(service.probe_instance("prod-1")["status"], "degraded")
        third = service.probe_instance("prod-1")
        self.assertEqual(third["status"], "unreachable")
        self.assertNotIn("sensitive", third["error_summary"])

    def test_instance_password_is_sent_only_to_secret_store(self):
        captured = []
        service = FleetService(self.store, credential_setter=lambda server, user, password:
                               captured.append((server, user, password)))
        service.set_credential("prod-1", "do-not-persist")
        self.assertEqual(captured, [("sql01.example.test", "monitor", "do-not-persist")])
        metadata = self.store.list_instances()[0]
        self.assertNotIn("password", metadata)
        self.assertNotIn("do-not-persist", repr(metadata))


class DispatcherTests(unittest.TestCase):
    def test_webhook_signs_exact_payload_and_posts_https(self):
        response = Mock()
        response.status = 202
        response.getcode.return_value = 202
        response.close = Mock()
        transport = Mock(return_value=response)
        dispatcher = NotificationDispatcher(urlopen=transport)
        event = {
            "event_id": "evt-1", "rule_id": "job_failure", "severity": "critical",
            "status": "new", "title": "Job failed", "summary": "Step failed",
            "instance_id": "prod-1", "first_seen_utc": "2026-11-16T10:00:00Z",
            "evidence": {"step": 2, "query_text": "sensitive SQL", "password": "secret"},
        }
        result = dispatcher.deliver(
            {"channel": "webhook", "config": {"url": "https://hooks.example.test/x"}},
            event, secret="test-secret",
        )
        self.assertTrue(result.success)
        request = transport.call_args.args[0]
        body = request.data
        expected = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        self.assertEqual(request.get_header("X-sqlagent-signature"), expected)
        payload = json.loads(body)
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["evidence"], {"step": 2})
        self.assertEqual(transport.call_args.kwargs["timeout"], 10)

    def test_http_webhook_is_rejected_before_send(self):
        transport = Mock()
        dispatcher = NotificationDispatcher(urlopen=transport)
        result = dispatcher.deliver(
            {"channel": "webhook", "config": {"url": "http://example.test/hook"}},
            {"event_id": "x"}, secret="secret",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.sanitized_error, "webhook URL must be HTTPS and must not contain embedded credentials")
        transport.assert_not_called()

    def test_email_uses_starttls_and_sends_message(self):
        client = Mock()
        client.send_message.return_value = {}
        factory = Mock(return_value=client)
        dispatcher = NotificationDispatcher(smtp_factory=factory)
        result = dispatcher.deliver(
            {"channel": "email", "config": {
                "host": "smtp.example.test", "port": 587,
                "from": "monitor@example.test", "to": ["dba@example.test"],
                "username": "monitor", "starttls": True,
            }},
            {"severity": "high", "title": "Job failed", "summary": "Failure"},
            secret="smtp-password",
        )
        self.assertTrue(result.success)
        client.starttls.assert_called_once()
        client.login.assert_called_once_with("monitor", "smtp-password")
        client.send_message.assert_called_once()

    def test_worker_claims_and_delivers_pending_outbox(self):
        with tempfile.TemporaryDirectory() as folder:
            store = MonitoringStore(Path(folder) / "state.sqlite3")
            server = store.add_instance(display_name="S", server="sql", database_name="msdb",
                                        user_name="monitor", instance_id="s1")
            event = store.upsert_alert(dedup_key="s1:test", rule_id="test", severity="high",
                                       title="Test", summary="Alert", instance_id="s1")
            target = store.add_notification_target(channel="webhook", name="Ops",
                                                   config={"url": "https://hooks.example.test"})
            store.enqueue_notification(event["event_id"], target["target_id"])
            fake_dispatcher = Mock()
            fake_dispatcher.deliver.return_value = type("Result", (), {
                "success": True, "status_code": 202, "sanitized_error": None
            })()
            worker = NotificationWorker(store, dispatcher=fake_dispatcher,
                                        secret_provider=lambda _target: "hmac-secret")
            [result] = worker.run_once()
            self.assertEqual(result["status"], "delivered")
            fake_dispatcher.deliver.assert_called_once()


if __name__ == "__main__":
    unittest.main()
