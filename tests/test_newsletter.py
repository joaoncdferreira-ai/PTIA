import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ptia_engine.editorial import add_performance_record
from ptia_engine.editorial_board import add_final_post, add_radar_signal
from ptia_engine.models import ContentPerformance
from ptia_engine.newsletter import (
    generate_weekly_issue,
    update_newsletter_status,
    weekly_candidates,
    weekly_owned_post_candidates,
)
from ptia_engine.storage import load_final_posts, load_newsletter_issues, load_radar_signals


class NewsletterTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.today = datetime.now(timezone.utc).date().isoformat()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _signal(self, title: str, score: int):
        return add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title=title,
            url=f"https://example.com/{score}",
            published_at=self.today,
            engagement_score=score,
            summary=f"{title} summary.",
            why_it_matters=f"{title} matters.",
            status="verified",
        )

    def test_weekly_candidates_select_top_five(self):
        for index in range(7):
            self._signal(f"Story {index}", index)

        candidates = weekly_candidates(load_radar_signals(self.root / "radar_signals.jsonl"), [], [])

        self.assertEqual(len(candidates), 5)
        self.assertEqual(candidates[0].score, 6)

    def test_generate_weekly_issue_outputs_email_ready_html_and_text(self):
        for index in range(5):
            post = add_final_post(
                self.root / "final_posts.jsonl",
                topic_id=f"topic_{index}",
                channel="linkedin",
                title=f"AI story {index}",
                body=f"Texto do post {index}.",
                hashtags="#IA",
                image_prompt="",
                source_urls=[f"https://example.com/source/{index}"],
            )
            add_performance_record(
                self.root / "content_performance.jsonl",
                ContentPerformance(
                    performance_id=f"perf_{index}",
                    draft_id=post.post_id,
                    post_id=f"https://linkedin.com/posts/{index}",
                    channel="linkedin",
                    published_at=self.today,
                    topic=post.title,
                    section="business",
                    likes=10 + index,
                    comments=index,
                    shares=index,
                    saves=index,
                    clicks=index,
                ),
            )

        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=load_radar_signals(self.root / "radar_signals.jsonl"),
            trend_signals=[],
            final_posts=load_final_posts(self.root / "final_posts.jsonl"),
            performance=[
                ContentPerformance.from_record(record)
                for record in [
                    {
                        "performance_id": f"manual_{index}",
                        "draft_id": load_final_posts(self.root / "final_posts.jsonl")[index].post_id,
                        "post_id": f"https://linkedin.com/posts/manual-{index}",
                        "channel": "linkedin",
                        "published_at": self.today,
                        "topic": f"AI story {index}",
                        "section": "business",
                        "likes": 10 + index,
                        "comments": index,
                        "shares": index,
                        "saves": index,
                        "clicks": index,
                    }
                    for index in range(5)
                ]
            ],
        )

        self.assertIn("PTIA Weekly", issue.html)
        self.assertIn("Fonte original", issue.html)
        self.assertIn("Importa para Portugal", issue.text)
        self.assertNotIn("Ângulo Portugal", issue.text)
        self.assertEqual(len(issue.item_ids), 5)
        self.assertEqual(load_newsletter_issues(self.root / "newsletter_issues.jsonl")[0].issue_id, issue.issue_id)

    def test_weekly_owned_post_candidates_rank_by_tracking(self):
        posts = []
        performance = []
        for index in range(6):
            post = add_final_post(
                self.root / "final_posts.jsonl",
                topic_id=f"topic_{index}",
                channel="instagram",
                title=f"Post {index}",
                body=f"Body {index}",
                hashtags="#IA",
                image_prompt="",
                source_urls=["https://example.com"],
            )
            posts.append(post)
            performance.append(
                ContentPerformance(
                    performance_id=f"perf_rank_{index}",
                    draft_id=post.post_id,
                    post_id=f"https://instagram.com/p/{index}",
                    channel="instagram",
                    published_at=self.today,
                    topic=post.title,
                    section="tools",
                    likes=index,
                    shares=index * 2,
                    saves=index * 3,
                )
            )

        candidates = weekly_owned_post_candidates(performance, posts)

        self.assertEqual(len(candidates), 5)
        self.assertEqual(candidates[0].title, "Post 5")
        self.assertEqual(candidates[0].kind, "owned_post")

    def test_update_newsletter_status(self):
        for index in range(5):
            self._signal(f"AI story {index}", 50 + index)
        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=load_radar_signals(self.root / "radar_signals.jsonl"),
            trend_signals=[],
            final_posts=[],
        )

        updated = update_newsletter_status(
            self.root / "newsletter_issues.jsonl",
            issue.issue_id,
            "scheduled",
            "2026-05-22T08:00:00+01:00",
        )

        self.assertEqual(updated.status, "scheduled")
        self.assertEqual(updated.send_at, "2026-05-22T08:00:00+01:00")


if __name__ == "__main__":
    unittest.main()
