import importlib.util
import shutil
import sys
import unittest
import uuid

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from ptia_engine.models import NewsletterIssue
from ptia_engine.newsletter_delivery import NewsletterDeliveryResult
from ptia_engine.newsletter_delivery import ptia_timezone


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "github_newsletter_runner",
    ROOT / "scripts" / "github_newsletter_runner.py",
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class GitHubNewsletterRunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_schedule_guard_accepts_only_summer_cron_during_dst(self):
        tz = ptia_timezone()

        self.assertTrue(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 6, 12, 8, 35, tzinfo=tz),
                RUNNER.SUMMER_SCHEDULE,
            )
        )
        self.assertFalse(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 6, 12, 9, 35, tzinfo=tz),
                RUNNER.WINTER_SCHEDULE,
            )
        )

    def test_schedule_guard_accepts_only_winter_cron_outside_dst(self):
        tz = ptia_timezone()

        self.assertTrue(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 12, 11, 8, 35, tzinfo=tz),
                RUNNER.WINTER_SCHEDULE,
            )
        )
        self.assertFalse(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 12, 11, 7, 35, tzinfo=tz),
                RUNNER.SUMMER_SCHEDULE,
            )
        )

    def test_schedule_guard_rejects_non_friday_and_late_recovery(self):
        tz = ptia_timezone()

        self.assertFalse(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 6, 13, 8, 35, tzinfo=tz),
                RUNNER.SUMMER_SCHEDULE,
            )
        )
        self.assertFalse(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 6, 12, 18, 0, tzinfo=tz),
                RUNNER.SUMMER_SCHEDULE,
            )
        )

    def test_runner_creates_missing_optional_datasets(self):
        (self.root / "final_posts.jsonl").write_text("", encoding="utf-8")

        RUNNER.ensure_runner_datasets(self.root)

        self.assertTrue(
            all((self.root / filename).exists() for filename in RUNNER.REQUIRED_DATASETS)
        )

    def test_scheduled_trigger_outside_window_is_successful_noop(self):
        tz = ptia_timezone()

        exit_code = RUNNER.main(
            [
                "--data-dir",
                str(self.root),
                "--scheduled-trigger",
                "--scheduled-cron",
                RUNNER.WINTER_SCHEDULE,
                "--json",
            ],
            now=datetime(2026, 6, 12, 7, 35, tzinfo=tz),
        )

        self.assertEqual(exit_code, 0)
        self.assertFalse((self.root / "newsletter_issues.jsonl").exists())

    def test_live_run_with_empty_list_does_not_create_campaign(self):
        tz = ptia_timezone()
        issue = NewsletterIssue(
            issue_id="weekly_empty",
            title="Weekly",
            subject="Weekly",
            preheader="",
            intro="",
            html="<html>{{ unsubscribe }}</html>",
            text="Weekly",
            item_ids=["post_1"],
            generator_version="3",
        )

        class EmptyBrevoClient:
            def __init__(self, config):
                self.config = config

            def validate_lists(self):
                return [{"id": 1, "name": "PTIA Weekly"}]

            def validate_sender(self):
                return {"email": "info@ptia.pt", "active": True}

            def validate_capacity(self):
                return 0

        with (
            patch.object(RUNNER.BrevoConfig, "from_env", return_value=object()),
            patch.object(RUNNER, "BrevoClient", EmptyBrevoClient),
            patch.object(
                RUNNER,
                "schedule_weekly_newsletter",
                return_value=NewsletterDeliveryResult(
                    action="dry_run",
                    issue=issue,
                    send_at=datetime(2026, 6, 12, 9, 0, tzinfo=tz),
                ),
            ) as schedule,
        ):
            exit_code = RUNNER.main(
                ["--data-dir", str(self.root), "--live", "--json"],
                now=datetime(2026, 6, 12, 8, 35, tzinfo=tz),
            )

        self.assertEqual(exit_code, 0)
        schedule.assert_called_once()
        self.assertTrue(schedule.call_args.kwargs["dry_run"])

    def test_workflow_covers_summer_winter_and_is_read_only(self):
        workflow = (ROOT / ".github" / "workflows" / "weekly-newsletter.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('cron: "35 7 * * 5"', workflow)
        self.assertIn('cron: "35 8 * * 5"', workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("--scheduled-trigger", workflow)
        self.assertIn('--scheduled-cron "${{ github.event.schedule }}"', workflow)
        self.assertNotIn("firebase", workflow.casefold())


if __name__ == "__main__":
    unittest.main()
