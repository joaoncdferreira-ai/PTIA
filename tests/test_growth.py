import argparse
import io
import shutil
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path

from ptia_engine.cli import cmd_growth_report
from ptia_engine.editorial_board import add_final_post
from ptia_engine.growth import (
    add_utm_parameters,
    build_growth_report,
    tracked_article_url_for_social,
)
from ptia_engine.models import ContentPerformance
from ptia_engine.storage import append_jsonl


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_add_utm_parameters_is_deterministic_and_preserves_url_shape(self):
        url = "https://ptia.pt/artigos/tema?x=1&utm_source=old#section"

        tracked = add_utm_parameters(
            url,
            source="LinkedIn Page",
            campaign="Daily Post",
            content="Post 123",
        )

        self.assertEqual(
            tracked,
            "https://ptia.pt/artigos/tema?x=1&utm_source=linkedin-page"
            "&utm_medium=social&utm_campaign=daily-post&utm_content=post-123#section",
        )

    def test_tracked_article_url_uses_site_post_slug_and_social_channel(self):
        site_post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="site",
            title="IA em Portugal: o que muda?",
            body="Texto",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com"],
        )

        tracked = tracked_article_url_for_social(
            site_post,
            channel="x",
            content="post_social",
            base_url="https://ptia.pt",
        )

        self.assertIn("/artigos/ia-em-portugal-o-que-muda-", tracked)
        self.assertIn("utm_source=x", tracked)
        self.assertIn("utm_content=post-social", tracked)

    def test_growth_report_handles_empty_metrics_with_safe_recommendation(self):
        report = build_growth_report(final_posts=[], performance=[], min_samples=3)

        self.assertEqual(report.performance_count, 0)
        self.assertIn("Amostra insuficiente", report.recommendations[0])

    def test_growth_report_groups_channels_sections_and_top_posts(self):
        linkedin = ContentPerformance(
            performance_id="perf_1",
            draft_id="",
            post_id="post_1",
            channel="linkedin",
            published_at="2026-06-03T09:00:00+01:00",
            topic="Tema A",
            section="builders",
            impressions=100,
            clicks=5,
            likes=10,
            comments=2,
            shares=1,
            site_views=20,
            newsletter_signups=1,
        )
        x = ContentPerformance(
            performance_id="perf_2",
            draft_id="",
            post_id="post_2",
            channel="x",
            published_at="2026-06-03T13:00:00+01:00",
            topic="Tema B",
            section="regulacao",
            impressions=50,
            clicks=1,
            likes=2,
        )

        report = build_growth_report(final_posts=[], performance=[linkedin, x], min_samples=1)

        self.assertEqual(report.performance_count, 2)
        self.assertEqual(report.channel_groups[0].name, "linkedin")
        self.assertEqual(report.section_groups[0].name, "builders")
        self.assertEqual(report.top_posts[0].title, "Tema A")
        self.assertGreater(report.top_posts[0].score, report.top_posts[1].score)

    def test_growth_report_cli_prints_without_writing_by_default(self):
        append_jsonl(
            self.root / "content_performance.jsonl",
            [
                ContentPerformance(
                    performance_id="perf_1",
                    draft_id="",
                    post_id="post_1",
                    channel="linkedin",
                    published_at="2026-06-03T09:00:00+01:00",
                    topic="Tema A",
                    section="builders",
                    likes=1,
                )
            ],
        )
        args = argparse.Namespace(
            final_posts=str(self.root / "final_posts.jsonl"),
            performance=str(self.root / "content_performance.jsonl"),
            top_limit=5,
            min_samples=3,
            out="",
            json=False,
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = cmd_growth_report(args)

        self.assertEqual(result, 0)
        self.assertIn("growth_report", stdout.getvalue())
        self.assertFalse((self.root / "growth_report.md").exists())


if __name__ == "__main__":
    unittest.main()
