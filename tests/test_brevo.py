import json
import unittest
import urllib.error

from datetime import datetime, timedelta, timezone

from ptia_engine.brevo import (
    BrevoAPIError,
    BrevoClient,
    BrevoConfig,
    BrevoConfigError,
    brevo_html,
    build_campaign_payload,
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


class BrevoTests(unittest.TestCase):
    def _issue(self):
        return NewsletterIssue(
            issue_id="weekly_test",
            title="PTIA Weekly",
            subject="PTIA Weekly: teste",
            preheader="preheader",
            intro="intro",
            html='<html><a href="{{$unsubscribe}}">Sair</a></html>',
            text="PTIA",
        )

    def _config(self):
        return BrevoConfig(
            api_key="secret",
            list_ids=(123,),
            from_email="weekly@ptia.pt",
            from_name="PTIA",
            reply_to="reply@ptia.pt",
            doi_template_id=88,
            base_url="https://api.brevo.test/v3",
        )

    def test_config_from_env_requires_api_list_and_sender(self):
        with self.assertRaises(BrevoConfigError) as ctx:
            BrevoConfig.from_env({})

        self.assertIn("BREVO_API_KEY", ctx.exception.missing)
        self.assertIn("BREVO_LIST_ID or BREVO_LIST_IDS", ctx.exception.missing)
        self.assertIn("PTIA_NEWSLETTER_FROM_EMAIL", ctx.exception.missing)

    def test_legacy_mailerlite_ledger_fields_are_read_without_duplication_risk(self):
        issue = NewsletterIssue.from_record(
            {
                "issue_id": "weekly_legacy",
                "mailerlite_campaign_id": "old_campaign",
                "mailerlite_status": "sent",
            }
        )

        self.assertEqual(issue.delivery_provider, "mailerlite")
        self.assertEqual(issue.provider_campaign_id, "old_campaign")
        self.assertEqual(issue.provider_status, "sent")

    def test_config_rejects_invalid_list_and_limit(self):
        with self.assertRaises(BrevoConfigError) as ctx:
            BrevoConfig.from_env(
                {
                    "BREVO_API_KEY": "secret",
                    "BREVO_LIST_IDS": "abc,-2",
                    "BREVO_MAX_RECIPIENTS": "zero",
                    "PTIA_NEWSLETTER_FROM_EMAIL": "weekly@ptia.pt",
                }
            )

        self.assertIn("invalid Brevo list ID: abc", ctx.exception.invalid)
        self.assertIn("Brevo list ID must be positive: -2", ctx.exception.invalid)
        self.assertIn("BREVO_MAX_RECIPIENTS must be a positive integer", ctx.exception.invalid)

    def test_build_campaign_payload_contains_html_list_sender_and_preheader(self):
        send_at = datetime(2026, 6, 12, 9, 0, tzinfo=timezone(timedelta(hours=1)))

        payload = build_campaign_payload(self._issue(), self._config(), send_at=send_at)

        self.assertEqual(payload["name"], "PTIA Weekly - 2026-06-12")
        self.assertEqual(payload["recipients"], {"listIds": [123]})
        self.assertEqual(payload["sender"]["email"], "weekly@ptia.pt")
        self.assertEqual(payload["replyTo"], "reply@ptia.pt")
        self.assertEqual(payload["previewText"], "preheader")
        self.assertIn("{{ unsubscribe }}", payload["htmlContent"])
        self.assertEqual(payload["scheduledAt"], "2026-06-12T09:00:00+01:00")

    def test_brevo_html_converts_legacy_mailerlite_tags(self):
        converted = brevo_html("{$unsubscribe} {$url} MailerLite")

        self.assertEqual(converted, "{{ unsubscribe }} {{ mirror }} Brevo")

    def test_client_creates_and_schedules_campaign(self):
        seen = []

        def fake_transport(request, *, timeout):
            payload = json.loads(request.data.decode("utf-8")) if request.data else None
            seen.append((request.method, request.full_url, payload, timeout))
            if request.method == "POST":
                return FakeResponse({"id": 42})
            if request.method == "GET":
                return FakeResponse({"id": 42, "status": "scheduled"})
            return FakeResponse({})

        client = BrevoClient(self._config(), transport=fake_transport, timeout=12)
        send_at = datetime(2026, 6, 12, 9, 0, tzinfo=timezone(timedelta(hours=1)))

        created = client.create_campaign(self._issue(), send_at=send_at)
        scheduled = client.schedule_campaign("42", send_at=send_at)

        self.assertEqual(created["data"]["id"], "42")
        self.assertEqual(scheduled["data"]["status"], "scheduled")
        self.assertEqual(seen[0][0:2], ("POST", "https://api.brevo.test/v3/emailCampaigns"))
        self.assertNotIn("scheduledAt", seen[0][2])
        self.assertEqual(
            seen[1][0:2],
            ("PUT", "https://api.brevo.test/v3/emailCampaigns/42"),
        )
        self.assertEqual(seen[1][2]["scheduledAt"], "2026-06-12T09:00:00+01:00")
        self.assertTrue(seen[2][1].endswith("?excludeHtmlContent=true"))

    def test_client_validates_list_sender_and_free_capacity(self):
        def fake_transport(request, *, timeout):
            if "/contacts/lists" in request.full_url:
                return FakeResponse({"lists": [{"id": 123, "name": "PTIA Weekly"}]})
            if request.full_url.endswith("/senders"):
                return FakeResponse(
                    {"senders": [{"id": 7, "email": "weekly@ptia.pt", "active": True}]}
                )
            if "/contacts?" in request.full_url:
                return FakeResponse({"count": 299, "contacts": []})
            raise AssertionError(request.full_url)

        client = BrevoClient(self._config(), transport=fake_transport)

        self.assertEqual(client.validate_lists()[0]["name"], "PTIA Weekly")
        self.assertEqual(client.validate_sender()["id"], 7)
        self.assertEqual(client.validate_capacity(), 299)

    def test_client_blocks_more_than_free_daily_limit(self):
        def fake_transport(request, *, timeout):
            return FakeResponse({"count": 301, "contacts": []})

        client = BrevoClient(self._config(), transport=fake_transport)

        with self.assertRaises(BrevoConfigError) as ctx:
            client.validate_capacity()

        self.assertIn("recipients (301)", ctx.exception.invalid[0])

    def test_client_rejects_inactive_sender(self):
        def fake_transport(request, *, timeout):
            return FakeResponse(
                {"senders": [{"email": "weekly@ptia.pt", "active": False}]}
            )

        client = BrevoClient(self._config(), transport=fake_transport)

        with self.assertRaises(BrevoConfigError) as ctx:
            client.validate_sender()

        self.assertIn("not active", ctx.exception.invalid[0])

    def test_client_deletes_validation_draft(self):
        seen = []

        def fake_transport(request, *, timeout):
            seen.append((request.method, request.full_url))
            return FakeResponse({})

        client = BrevoClient(self._config(), transport=fake_transport)
        client.delete_campaign("42")

        self.assertEqual(
            seen,
            [("DELETE", "https://api.brevo.test/v3/emailCampaigns/42")],
        )

    def test_client_creates_double_opt_in_contact(self):
        seen = []

        def fake_transport(request, *, timeout):
            seen.append(
                (
                    request.method,
                    request.full_url,
                    json.loads(request.data.decode("utf-8")),
                )
            )
            return FakeResponse({})

        client = BrevoClient(self._config(), transport=fake_transport)
        client.create_doi_contact("reader@example.com", first_name="João")

        self.assertEqual(
            seen[0][0:2],
            ("POST", "https://api.brevo.test/v3/contacts/doubleOptinConfirmation"),
        )
        self.assertEqual(seen[0][2]["templateId"], 88)
        self.assertEqual(seen[0][2]["includeListIds"], [123])
        self.assertEqual(seen[0][2]["attributes"], {"FIRSTNAME": "João"})

    def test_client_validates_double_opt_in_template(self):
        def fake_transport(request, *, timeout):
            return FakeResponse({"id": 88, "isActive": True, "doiTemplate": True})

        client = BrevoClient(self._config(), transport=fake_transport)

        self.assertEqual(client.validate_doi_template()["id"], 88)

    def test_client_rejects_non_doi_template(self):
        def fake_transport(request, *, timeout):
            return FakeResponse({"id": 88, "isActive": True, "doiTemplate": False})

        client = BrevoClient(self._config(), transport=fake_transport)

        with self.assertRaises(BrevoConfigError) as ctx:
            client.validate_doi_template()

        self.assertIn("not double opt-in", ctx.exception.invalid[0])

    def test_client_raises_api_error_without_leaking_token(self):
        def fake_transport(request, *, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                422,
                "Unprocessable",
                {},
                fp=FakeResponse({"message": "bad request"}),
            )

        client = BrevoClient(self._config(), transport=fake_transport)

        with self.assertRaises(BrevoAPIError) as ctx:
            client.create_campaign(self._issue(), send_at=datetime.now(timezone.utc))

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertNotIn("secret", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
