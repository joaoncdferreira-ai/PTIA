import importlib.util
import os
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

    def test_schedule_guard_accepts_thursday_preparation(self):
        tz = ptia_timezone()

        self.assertTrue(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 6, 11, 19, 35, tzinfo=tz),
                RUNNER.PREPARE_SCHEDULE,
            )
        )
        self.assertFalse(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 6, 12, 19, 35, tzinfo=tz),
                RUNNER.PREPARE_SCHEDULE,
            )
        )

    def test_schedule_guard_accepts_early_friday_recovery(self):
        tz = ptia_timezone()

        self.assertTrue(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 12, 11, 2, 5, tzinfo=tz),
                RUNNER.RECOVERY_SCHEDULE,
            )
        )
        self.assertFalse(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 12, 11, 9, 0, tzinfo=tz),
                RUNNER.RECOVERY_SCHEDULE,
            )
        )

    def test_schedule_guard_rejects_unknown_cron(self):
        tz = ptia_timezone()

        self.assertFalse(
            RUNNER.scheduled_window_is_open(
                datetime(2026, 6, 12, 8, 0, tzinfo=tz),
                "0 0 * * *",
            )
        )

    def test_explicit_send_at_uses_lisbon_timezone(self):
        tz = ptia_timezone()

        send_at = RUNNER.resolve_send_at(
            "2026-06-12T17:00:00+01:00",
            datetime(2026, 6, 12, 15, 0, tzinfo=tz),
        )

        self.assertEqual(send_at.isoformat(), "2026-06-12T17:00:00+01:00")

    def test_runner_creates_missing_optional_datasets(self):
        (self.root / "final_posts.jsonl").write_text("", encoding="utf-8")

        RUNNER.ensure_runner_datasets(self.root)

        self.assertTrue(
            all((self.root / filename).exists() for filename in RUNNER.REQUIRED_DATASETS)
        )

    def test_runner_hydrates_cloud_state_before_compilation(self):
        with (
            patch.dict(os.environ, {"PTIA_CLOUD_STATE_ENABLED": "true"}),
            patch.object(RUNNER.CloudStateConfig, "from_env", return_value=object()),
            patch.object(RUNNER, "hydrate_cloud_state") as hydrate,
        ):
            RUNNER.prepare_runner_state(self.root)

        hydrate.assert_called_once_with(self.root)
        self.assertTrue(
            all((self.root / filename).exists() for filename in RUNNER.REQUIRED_DATASETS)
        )

    def test_runner_rejects_enabled_cloud_state_without_credentials(self):
        with (
            patch.dict(os.environ, {"PTIA_CLOUD_STATE_ENABLED": "true"}),
            patch.object(RUNNER.CloudStateConfig, "from_env", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "PTIA_STATE_TOKEN"):
                RUNNER.prepare_runner_state(self.root)

    def test_scheduled_trigger_outside_window_is_successful_noop(self):
        tz = ptia_timezone()

        exit_code = RUNNER.main(
            [
                "--data-dir",
                str(self.root),
                "--scheduled-trigger",
                "--scheduled-cron",
                RUNNER.PREPARE_SCHEDULE,
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

        self.assertIn('cron: "35 18 * * 4"', workflow)
        self.assertIn('cron: "5 2 * * 5"', workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("--scheduled-trigger", workflow)
        self.assertIn('--scheduled-cron "${{ github.event.schedule }}"', workflow)
        self.assertIn("PTIA_SEND_AT: ${{ inputs.send_at }}", workflow)
        self.assertIn('--send-at "$PTIA_SEND_AT"', workflow)
        self.assertIn('PTIA_CLOUD_STATE_ENABLED: "true"', workflow)
        self.assertIn("PTIA_STATE_TOKEN: ${{ secrets.PTIA_STATE_TOKEN }}", workflow)
        self.assertNotIn("firebase", workflow.casefold())


if __name__ == "__main__":
    unittest.main()
