import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.editorial_board import add_final_post, update_final_post_status
from ptia_engine.scheduler import (
    NoopScheduleBackend,
    build_schedule_day_plan,
    build_schedule_execution_plan,
    execute_schedule_plan,
    format_schedule_plan,
    load_schedule_slots,
)
from ptia_engine.storage import load_final_posts


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        (self.root / "data").mkdir()
        (self.root / "site" / "assets" / "final").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _post(self, channel: str, topic_id: str = "topic_1", scheduled_time: str = "2026-06-04T09:00:00+01:00"):
        image = self.root / "data" / f"{channel}.jpg"
        image.write_bytes(b"image")
        post = add_final_post(
            self.root / "data" / "final_posts.jsonl",
            topic_id=topic_id,
            channel=channel,
            title=f"Post {channel}",
            body=(
                "Texto factual sobre a noticia, com contexto suficiente para publicar.\n\n"
                "A leitura editorial explica a consequencia para equipas reais.\n\n"
                "Fonte: https://example.com/source"
            ),
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com/source"],
            image_path=str(image),
        )
        return update_final_post_status(
            self.root / "data" / "final_posts.jsonl",
            post.post_id,
            "approved_for_schedule",
            scheduled_time=scheduled_time,
        )

    def test_schedule_day_dry_run_groups_ready_package(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            self._post(channel)

        plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")

        self.assertTrue(plan.ready)
        self.assertEqual(plan.post_count, 4)
        self.assertEqual(len(plan.topics), 1)
        self.assertEqual(plan.topics[0].channels, ["instagram", "linkedin", "site", "x"])
        self.assertIn("would_schedule_buffer", {post.action for post in plan.topics[0].posts})
        self.assertIn("would_schedule_site", {post.action for post in plan.topics[0].posts})

    def test_schedule_day_blocks_missing_channel(self):
        for channel in ("linkedin", "instagram", "site"):
            self._post(channel)

        plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")

        self.assertFalse(plan.ready)
        self.assertIn("missing channels: x", plan.topics[0].issues)

    def test_disabled_x_is_not_required(self):
        (self.root / "data" / "buffer_channels.json").write_text(
            '{"channels":{"linkedin":"1","instagram":"2"},"disabled_channels":["x"]}',
            encoding="utf-8",
        )
        for channel in ("linkedin", "instagram", "site"):
            self._post(channel)

        plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")

        self.assertTrue(plan.ready)
        self.assertEqual(plan.topics[0].channels, ["instagram", "linkedin", "site"])

    def test_dry_run_does_not_modify_final_posts_file(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            self._post(channel)
        path = self.root / "data" / "final_posts.jsonl"
        before = path.read_text(encoding="utf-8")

        plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")
        rendered = format_schedule_plan(plan)

        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertIn("mode=dry-run", rendered)

    def test_explicit_plan_supplies_schedule_time_for_approved_posts(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            self._post(channel, topic_id="topic_planned", scheduled_time="")
        plan_path = self.root / "schedule.json"
        plan_path.write_text(
            '{"topics":[{"topic_id":"topic_planned","scheduled_time":"2026-06-04T13:00:00+01:00"}]}',
            encoding="utf-8",
        )

        plan = build_schedule_day_plan(
            repo_root=self.root,
            date="2026-06-04",
            slots=load_schedule_slots(plan_path),
        )

        self.assertTrue(plan.ready)
        self.assertEqual(plan.topics[0].scheduled_time, "2026-06-04T13:00:00+01:00")
        self.assertEqual({post.scheduled_time for post in plan.topics[0].posts}, {"2026-06-04T13:00:00+01:00"})

    def test_explicit_plan_blocks_unknown_topic(self):
        plan_path = self.root / "schedule.json"
        plan_path.write_text(
            '{"topics":[{"topic_id":"missing_topic","scheduled_time":"2026-06-04T13:00:00+01:00"}]}',
            encoding="utf-8",
        )

        plan = build_schedule_day_plan(
            repo_root=self.root,
            date="2026-06-04",
            slots=load_schedule_slots(plan_path),
        )

        self.assertFalse(plan.ready)
        self.assertIn("plan topics without schedulable posts: missing_topic", plan.issues)

    def test_execution_plan_models_instagram_carousel_once(self):
        for topic_id, scheduled_time in (
            ("topic_morning", "2026-06-04T09:00:00+01:00"),
            ("topic_evening", "2026-06-04T21:00:00+01:00"),
        ):
            for channel in ("linkedin", "instagram", "x", "site"):
                self._post(channel, topic_id=topic_id, scheduled_time="")
        plan_path = self.root / "schedule.json"
        plan_path.write_text(
            '{"topics":['
            '{"topic_id":"topic_morning","scheduled_time":"2026-06-04T09:00:00+01:00"},'
            '{"topic_id":"topic_evening","scheduled_time":"2026-06-04T21:00:00+01:00"}'
            ']}',
            encoding="utf-8",
        )
        day_plan = build_schedule_day_plan(
            repo_root=self.root,
            date="2026-06-04",
            slots=load_schedule_slots(plan_path),
        )

        execution = build_schedule_execution_plan(
            day_plan,
            final_posts=load_final_posts(self.root / "data" / "final_posts.jsonl"),
        )

        carousel = [action for action in execution.actions if action.kind == "schedule_instagram_carousel"]
        self.assertTrue(execution.ready)
        self.assertEqual(len(carousel), 1)
        self.assertEqual(carousel[0].scheduled_time, "2026-06-04T21:00:00+01:00")
        self.assertEqual(len(carousel[0].post_ids), 2)
        self.assertIn("caption", carousel[0].payload)
        self.assertEqual(len([action for action in execution.actions if action.kind == "prepare_public_assets"]), 1)
        self.assertEqual(len([action for action in execution.actions if action.kind == "sync_site_feed"]), 1)

    def test_execution_plan_adds_tracked_article_url_for_social_posts(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            self._post(channel)
        posts_path = self.root / "data" / "final_posts.jsonl"
        before = posts_path.read_text(encoding="utf-8")
        day_plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")

        execution = build_schedule_execution_plan(
            day_plan,
            final_posts=load_final_posts(posts_path),
        )

        linkedin = next(action for action in execution.actions if action.channel == "linkedin")
        x = next(action for action in execution.actions if action.channel == "x")
        self.assertIn("utm_source=linkedin", linkedin.payload["article_url"])
        self.assertIn("utm_source=x", x.payload["article_url"])
        self.assertEqual(posts_path.read_text(encoding="utf-8"), before)

    def test_execution_plan_skips_already_scheduled_without_duplicate_buffer_actions(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            post = self._post(channel)
            update_final_post_status(
                self.root / "data" / "final_posts.jsonl",
                post.post_id,
                "scheduled",
                scheduled_time="2026-06-04T09:00:00+01:00",
                buffer_post_id="buffer_1" if channel != "site" else "",
            )
        day_plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")

        execution = build_schedule_execution_plan(
            day_plan,
            final_posts=load_final_posts(self.root / "data" / "final_posts.jsonl"),
        )

        self.assertTrue(execution.ready)
        self.assertFalse([action for action in execution.actions if action.kind == "schedule_buffer_post"])
        self.assertEqual(len([action for action in execution.actions if action.status == "skipped"]), 4)

    def test_mixed_instagram_schedule_state_blocks_execution_plan(self):
        first = self._post("instagram", topic_id="topic_1", scheduled_time="2026-06-04T09:00:00+01:00")
        self._post("instagram", topic_id="topic_2", scheduled_time="2026-06-04T21:00:00+01:00")
        for channel in ("linkedin", "x", "site"):
            self._post(channel, topic_id="topic_1", scheduled_time="2026-06-04T09:00:00+01:00")
            self._post(channel, topic_id="topic_2", scheduled_time="2026-06-04T21:00:00+01:00")
        update_final_post_status(
            self.root / "data" / "final_posts.jsonl",
            first.post_id,
            "scheduled",
            scheduled_time="2026-06-04T09:00:00+01:00",
            buffer_post_id="buffer_1",
        )
        day_plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")

        execution = build_schedule_execution_plan(
            day_plan,
            final_posts=load_final_posts(self.root / "data" / "final_posts.jsonl"),
        )

        self.assertFalse(execution.ready)
        carousel = next(action for action in execution.actions if action.channel == "instagram")
        self.assertIn("mixed scheduled and unscheduled instagram posts require manual review", carousel.issues)

    def test_execute_requires_matching_confirmation_date(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            self._post(channel)
        day_plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")
        execution = build_schedule_execution_plan(
            day_plan,
            final_posts=load_final_posts(self.root / "data" / "final_posts.jsonl"),
        )

        with self.assertRaisesRegex(ValueError, "Confirmation mismatch"):
            execute_schedule_plan(
                execution,
                backend=NoopScheduleBackend(),
                confirm_date="2026-06-05",
            )

    def test_noop_execution_writes_audit_when_requested(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            self._post(channel)
        day_plan = build_schedule_day_plan(repo_root=self.root, date="2026-06-04")
        execution = build_schedule_execution_plan(
            day_plan,
            final_posts=load_final_posts(self.root / "data" / "final_posts.jsonl"),
            dry_run=False,
        )
        audit_path = self.root / "data" / "schedule_audit.jsonl"

        results = execute_schedule_plan(
            execution,
            backend=NoopScheduleBackend(),
            confirm_date="2026-06-04",
            audit_path=audit_path,
        )

        self.assertTrue(results)
        self.assertTrue(audit_path.exists())
        self.assertIn('"date": "2026-06-04"', audit_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
