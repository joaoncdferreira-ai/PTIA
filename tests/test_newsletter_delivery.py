import shutil
import unittest
import uuid

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ptia_engine.editorial_board import add_radar_signal
from ptia_engine.models import NewsletterIssue
from ptia_engine.newsletter_delivery import (
    next_friday_send_at,
    ptia_timezone,
    schedule_weekly_newsletter,
)
from ptia_engine.storage import append_jsonl, load_newsletter_issues


class FakeBrevoClient:
    def __init__(self):
        self.created = 0
        self.scheduled = 0

    def create_campaign(self, issue, *, send_at):
        self.created += 1
        return {"data": {"id": f"campaign_{self.created}", "status": "draft"}}

    def schedule_campaign(self, campaign_id, *, send_at):
        self.scheduled += 1
        return {"data": {"id": campaign_id, "status": "ready"}}

    def find_weekly_campaign(self, send_at):
        return None


class NewsletterDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _add_signal(self):
        today = datetime.now(timezone.utc).date().isoformat()
        return add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="AI story",
            url="https://example.com/ai-story",
            published_at=today,
            engagement_score=50,
            summary="Summary.",
            why_it_matters="Matters.",
            status="verified",
        )

    def test_next_friday_send_at_keeps_today_before_nine(self):
        tz = ptia_timezone()
        before = datetime(2026, 6, 5, 8, 30, tzinfo=tz)
        after = datetime(2026, 6, 5, 9, 1, tzinfo=tz)
        saturday = datetime(2026, 6, 6, 12, 0, tzinfo=tz)

        # Before 09:00 on Friday, targets today at 09:00
        self.assertEqual(next_friday_send_at(before).date().isoformat(), "2026-06-05")
        self.assertEqual(next_friday_send_at(before).hour, 9)

        # After 09:00 on Friday, targets today for immediate-ish delivery (today's date)
        self.assertEqual(next_friday_send_at(after).date().isoformat(), "2026-06-05")
        self.assertEqual(next_friday_send_at(after).minute, 3)

        # On Saturday, targets next Friday
        self.assertEqual(next_friday_send_at(saturday).date().isoformat(), "2026-06-12")

    def test_next_friday_send_at_does_not_recover_after_deadline(self):
        tz = ptia_timezone()
        friday_evening = datetime(2026, 6, 5, 18, 1, tzinfo=tz)

        target = next_friday_send_at(friday_evening)

        self.assertEqual(target.isoformat(), "2026-06-12T09:00:00+01:00")

    def test_scheduler_ignores_recent_issue_without_target_send_at(self):
        self._add_signal()
        append_jsonl(
            self.root / "newsletter_issues.jsonl",
            [
                NewsletterIssue(
                    issue_id="weekly_old",
                    title="Old",
                    subject="Old",
                    preheader="",
                    intro="",
                    html="",
                    text="",
                    status="draft",
                    created_at=(datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
                )
            ],
        )
        send_at = next_friday_send_at()
        client = FakeBrevoClient()

        result = schedule_weekly_newsletter(self.root, send_at=send_at, client=client)

        issues = load_newsletter_issues(self.root / "newsletter_issues.jsonl")
        self.assertEqual(result.action, "scheduled")
        self.assertEqual(result.issue.status, "scheduled")
        self.assertEqual(result.issue.send_at, send_at.isoformat())
        self.assertEqual(result.issue.delivery_provider, "brevo")
        self.assertEqual(result.issue.provider_campaign_id, "campaign_1")
        self.assertEqual(client.created, 1)
        self.assertEqual(client.scheduled, 1)
        self.assertEqual(len(issues), 2)

    def test_scheduler_regenerates_outdated_local_draft(self):
        self._add_signal()
        send_at = next_friday_send_at()
        append_jsonl(
            self.root / "newsletter_issues.jsonl",
            [
                NewsletterIssue(
                    issue_id="weekly_outdated",
                    title="Outdated",
                    subject="Outdated",
                    preheader="",
                    intro="",
                    html="<html>PRIVATE DRAFT CONTENT</html>",
                    text="PRIVATE DRAFT CONTENT",
                    item_ids=["old"],
                    send_at=send_at.isoformat(),
                )
            ],
        )

        result = schedule_weekly_newsletter(self.root, send_at=send_at, dry_run=True)

        self.assertEqual(result.action, "dry_run")
        self.assertEqual(result.issue.generator_version, "3")
        self.assertNotEqual(result.issue.issue_id, "weekly_outdated")
        self.assertNotIn("PRIVATE DRAFT CONTENT", result.issue.html)

    def test_scheduler_skips_existing_scheduled_issue_for_same_friday(self):
        send_at = next_friday_send_at()
        append_jsonl(
            self.root / "newsletter_issues.jsonl",
            [
                NewsletterIssue(
                    issue_id="weekly_existing",
                    title="Existing",
                    subject="Existing",
                    preheader="",
                    intro="",
                    html="",
                    text="",
                    status="scheduled",
                    send_at=send_at.isoformat(),
                    delivery_provider="brevo",
                    provider_campaign_id="campaign_existing",
                )
            ],
        )
        client = FakeBrevoClient()

        result = schedule_weekly_newsletter(self.root, send_at=send_at, client=client)

        self.assertEqual(result.action, "skipped_already_scheduled")
        self.assertEqual(result.campaign_id, "campaign_existing")
        self.assertEqual(client.created, 0)
        self.assertEqual(client.scheduled, 0)

    def test_force_does_not_duplicate_existing_scheduled_campaign(self):
        send_at = next_friday_send_at()
        append_jsonl(
            self.root / "newsletter_issues.jsonl",
            [
                NewsletterIssue(
                    issue_id="weekly_existing",
                    title="Existing",
                    subject="Existing",
                    preheader="",
                    intro="",
                    html="<html>{{ unsubscribe }}</html>",
                    text="Existing",
                    item_ids=["item_1"],
                    status="scheduled",
                    send_at=send_at.isoformat(),
                    delivery_provider="brevo",
                    provider_campaign_id="campaign_existing",
                )
            ],
        )
        client = FakeBrevoClient()

        result = schedule_weekly_newsletter(
            self.root,
            send_at=send_at,
            force=True,
            client=client,
        )

        self.assertEqual(result.action, "skipped_already_scheduled")
        self.assertEqual(client.created, 0)
        self.assertEqual(client.scheduled, 0)

    def test_scheduler_reuses_campaign_id_after_schedule_failure(self):
        send_at = next_friday_send_at()
        append_jsonl(
            self.root / "newsletter_issues.jsonl",
            [
                NewsletterIssue(
                    issue_id="weekly_retry",
                    title="Retry",
                    subject="Retry",
                    preheader="",
                    intro="",
                    html="<html>{{ unsubscribe }}</html>",
                    text="Retry",
                    item_ids=["item_1"],
                    generator_version="3",
                    status="failed",
                    send_at=send_at.isoformat(),
                    delivery_provider="brevo",
                    provider_campaign_id="campaign_retry",
                )
            ],
        )
        client = FakeBrevoClient()

        result = schedule_weekly_newsletter(self.root, send_at=send_at, client=client)

        self.assertEqual(result.action, "scheduled")
        self.assertEqual(result.campaign_id, "campaign_retry")
        self.assertEqual(client.created, 0)
        self.assertEqual(client.scheduled, 1)

    def test_scheduler_recovers_existing_remote_campaign_without_local_ledger(self):
        self._add_signal()
        send_at = next_friday_send_at()
        client = FakeBrevoClient()

        def existing_campaign(_send_at):
            return {
                "id": "campaign_remote",
                "name": f"PTIA Weekly - {send_at.date().isoformat()}",
                "status": "scheduled",
            }

        client.find_weekly_campaign = existing_campaign

        result = schedule_weekly_newsletter(self.root, send_at=send_at, client=client)

        self.assertEqual(result.action, "skipped_already_scheduled")
        self.assertEqual(result.campaign_id, "campaign_remote")
        self.assertEqual(result.issue.provider_campaign_id, "campaign_remote")
        self.assertEqual(client.created, 0)
        self.assertEqual(client.scheduled, 0)


if __name__ == "__main__":
    unittest.main()
