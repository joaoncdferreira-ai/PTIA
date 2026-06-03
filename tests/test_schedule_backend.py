import unittest
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

from ptia_engine.editorial_board import add_final_post
from ptia_engine.scheduler import ScheduleAction
from ptia_engine.services.schedule_backend import (
    DashboardScheduleBackend,
    ScheduleCapabilities,
    missing_capabilities,
    required_capabilities_for_actions,
)
from ptia_engine.storage import load_final_posts


class ScheduleBackendTests(unittest.TestCase):
    def test_required_capabilities_are_derived_from_actions(self):
        actions = [
            ScheduleAction("a1", "prepare_public_assets", "", "2026-06-04", post_ids=["p1"]),
            ScheduleAction("a2", "schedule_buffer_post", "t1", "2026-06-04T09:00:00+01:00", post_ids=["p1"]),
            ScheduleAction("a3", "schedule_instagram_carousel", "t2", "2026-06-04T21:00:00+01:00", post_ids=["p2"]),
            ScheduleAction("a4", "sync_site_feed", "", "2026-06-04"),
            ScheduleAction("a5", "skip_already_scheduled", "t3", "2026-06-04", status="skipped"),
        ]

        required = required_capabilities_for_actions(actions)

        self.assertEqual(required, {"publish_assets", "send_buffer", "write_site_feed"})

    def test_missing_capabilities_ignore_skipped_actions(self):
        actions = [
            ScheduleAction("a1", "prepare_public_assets", "", "2026-06-04", post_ids=["p1"]),
            ScheduleAction("a2", "skip_already_scheduled", "t3", "2026-06-04", status="skipped"),
        ]

        missing = missing_capabilities(
            actions,
            ScheduleCapabilities(publish_assets=False, send_buffer=False, write_site_feed=False),
        )

        self.assertEqual(missing, ["publish_assets"])

    def test_no_missing_capabilities_when_all_required_are_explicit(self):
        actions = [
            ScheduleAction("a1", "schedule_buffer_post", "t1", "2026-06-04T09:00:00+01:00", post_ids=["p1"]),
            ScheduleAction("a2", "schedule_site_post", "t1", "2026-06-04T09:00:00+01:00", post_ids=["p2"]),
        ]

        missing = missing_capabilities(
            actions,
            ScheduleCapabilities(send_buffer=True, write_site_feed=True),
        )

        self.assertEqual(missing, [])

    def test_site_schedule_adapter_does_not_call_buffer_scheduler(self):
        root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        data_dir = root / "data"
        data_dir.mkdir(parents=True)
        try:
            post = add_final_post(
                data_dir / "final_posts.jsonl",
                topic_id="topic_1",
                channel="site",
                title="Site post",
                body="Texto factual pronto para site.\n\nFonte: https://example.com",
                hashtags="#IA",
                image_prompt="",
                source_urls=["https://example.com"],
            )
            backend = DashboardScheduleBackend(
                repo_root=root,
                data_dir=data_dir,
                capabilities=ScheduleCapabilities(write_site_feed=True),
            )
            action = ScheduleAction(
                "site_1",
                "schedule_site_post",
                "topic_1",
                "2026-06-04T09:00:00+01:00",
                post_ids=[post.post_id],
                channel="site",
            )

            with patch("ptia_engine.dashboard._schedule_post_in_buffer", side_effect=AssertionError("old path")):
                result = backend.schedule_site_post(action)

            updated = load_final_posts(data_dir / "final_posts.jsonl")[0]
            self.assertEqual(result.status, "ok")
            self.assertEqual(updated.status, "scheduled")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
