import json
import unittest
import urllib.error

from datetime import datetime, timedelta, timezone

from ptia_engine.mailerlite import (
    MailerLiteAPIError,
    MailerLiteClient,
    MailerLiteConfig,
    MailerLiteConfigError,
    build_campaign_payload,
    build_schedule_payload,
)
from ptia_engine.models import NewsletterIssue


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        return None


class MailerLiteTests(unittest.TestCase):
    def _issue(self):
        return NewsletterIssue(
            issue_id="weekly_test",
            title="PTIA Weekly",
            subject="PTIA Weekly: teste",
            preheader="preheader",
            intro="intro",
            html="<html><body>PTIA</body></html>",
            text="PTIA",
        )

    def _config(self):
        return MailerLiteConfig(
            api_key="secret",
            group_ids=("123",),
            from_email="weekly@ptia.pt",
            from_name="PTIA",
            reply_to="reply@ptia.pt",
            timezone_id=1,
            base_url="https://connect.mailerlite.test/api",
        )

    def test_config_from_env_requires_api_group_and_sender(self):
        with self.assertRaises(MailerLiteConfigError) as ctx:
            MailerLiteConfig.from_env({})

        self.assertIn("MAILERLITE_API_KEY", ctx.exception.missing)
        self.assertIn("MAILERLITE_GROUP_ID or MAILERLITE_GROUP_IDS", ctx.exception.missing)
        self.assertIn("PTIA_NEWSLETTER_FROM_EMAIL or MAILERLITE_FROM_EMAIL", ctx.exception.missing)

    def test_build_campaign_payload_contains_content_group_and_sender(self):
        send_at = datetime(2026, 6, 12, 9, 0, tzinfo=timezone(timedelta(hours=1)))

        payload = build_campaign_payload(self._issue(), self._config(), send_at=send_at)

        self.assertEqual(payload["name"], "PTIA Weekly - 2026-06-12")
        self.assertEqual(payload["type"], "regular")
        self.assertEqual(payload["groups"], ["123"])
        self.assertEqual(payload["emails"][0]["from"], "weekly@ptia.pt")
        self.assertEqual(payload["emails"][0]["reply_to"], "reply@ptia.pt")
        self.assertEqual(payload["emails"][0]["content"], "<html><body>PTIA</body></html>")

    def test_config_from_env_rejects_non_numeric_api_ids(self):
        with self.assertRaises(MailerLiteConfigError) as ctx:
            MailerLiteConfig.from_env(
                {
                    "MAILERLITE_API_KEY": "secret",
                    "MAILERLITE_GROUP_ID": "123",
                    "MAILERLITE_FROM_EMAIL": "weekly@ptia.pt",
                    "MAILERLITE_TIMEZONE_ID": "Europe/Lisbon",
                    "MAILERLITE_LANGUAGE_ID": "pt",
                }
            )

        self.assertIn("MAILERLITE_TIMEZONE_ID must be an integer", ctx.exception.invalid)
        self.assertIn("MAILERLITE_LANGUAGE_ID must be an integer", ctx.exception.invalid)

    def test_build_schedule_payload_targets_exact_hour(self):
        send_at = datetime(2026, 6, 12, 9, 0, tzinfo=timezone(timedelta(hours=1)))

        payload = build_schedule_payload(send_at, self._config())

        self.assertEqual(payload["delivery"], "scheduled")
        self.assertEqual(payload["schedule"]["date"], "2026-06-12")
        self.assertEqual(payload["schedule"]["hours"], "09")
        self.assertEqual(payload["schedule"]["minutes"], "00")
        self.assertEqual(payload["schedule"]["timezone_id"], 1)

    def test_client_posts_create_and_schedule_requests(self):
        seen = []

        def fake_transport(request, *, timeout):
            seen.append((request.full_url, json.loads(request.data.decode("utf-8")), timeout))
            if request.full_url.endswith("/schedule"):
                return FakeResponse({"data": {"id": "campaign_1", "status": "ready"}})
            return FakeResponse({"data": {"id": "campaign_1", "status": "draft"}})

        client = MailerLiteClient(self._config(), transport=fake_transport, timeout=12)
        send_at = datetime(2026, 6, 12, 9, 0, tzinfo=timezone(timedelta(hours=1)))

        created = client.create_campaign(self._issue(), send_at=send_at)
        scheduled = client.schedule_campaign("campaign_1", send_at=send_at)

        self.assertEqual(created["data"]["id"], "campaign_1")
        self.assertEqual(scheduled["data"]["status"], "ready")
        self.assertEqual(seen[0][0], "https://connect.mailerlite.test/api/campaigns")
        self.assertEqual(seen[0][1]["emails"][0]["content"], "<html><body>PTIA</body></html>")
        self.assertEqual(seen[1][0], "https://connect.mailerlite.test/api/campaigns/campaign_1/schedule")
        self.assertEqual(seen[1][1]["schedule"]["hours"], "09")

    def test_client_validates_configured_groups(self):
        def fake_transport(request, *, timeout):
            self.assertTrue(request.full_url.endswith("/groups?limit=1000"))
            return FakeResponse(
                {
                    "data": [
                        {"id": "123", "name": "PTIA Weekly"},
                        {"id": "999", "name": "Other"},
                    ]
                }
            )

        client = MailerLiteClient(self._config(), transport=fake_transport)

        groups = client.validate_groups()

        self.assertEqual(groups, [{"id": "123", "name": "PTIA Weekly"}])

    def test_client_rejects_unknown_configured_group(self):
        def fake_transport(request, *, timeout):
            return FakeResponse({"data": [{"id": "999", "name": "Other"}]})

        client = MailerLiteClient(self._config(), transport=fake_transport)

        with self.assertRaises(MailerLiteConfigError) as ctx:
            client.validate_groups()

        self.assertIn("unknown MailerLite group IDs: 123", ctx.exception.invalid)

    def test_client_resolves_lisbon_timezone_id(self):
        def fake_transport(request, *, timeout):
            self.assertTrue(request.full_url.endswith("/timezones"))
            return FakeResponse(
                {
                    "data": [
                        {"id": "370", "name": "Europe/Vilnius"},
                        {"id": "321", "name": "Europe/Lisbon"},
                    ]
                }
            )

        client = MailerLiteClient(self._config(), transport=fake_transport)

        self.assertEqual(client.resolve_timezone_id("Europe/Lisbon"), 321)

    def test_client_deletes_validation_draft(self):
        seen = []

        def fake_transport(request, *, timeout):
            seen.append((request.method, request.full_url))
            return FakeResponse({})

        client = MailerLiteClient(self._config(), transport=fake_transport)
        client.delete_campaign("campaign_test")

        self.assertEqual(
            seen,
            [
                (
                    "DELETE",
                    "https://connect.mailerlite.test/api/campaigns/campaign_test",
                )
            ],
        )

    def test_client_raises_api_error_without_leaking_token(self):
        def fake_transport(request, *, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                422,
                "Unprocessable",
                {},
                fp=FakeResponse({"message": "bad request"}),
            )

        client = MailerLiteClient(self._config(), transport=fake_transport)

        with self.assertRaises(MailerLiteAPIError) as ctx:
            client.create_campaign(self._issue(), send_at=datetime.now(timezone.utc))

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertNotIn("secret", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
