import json
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
    has_suspicious_encoding,
    update_newsletter_delivery,
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

    def test_weekly_candidates_dedupe_same_named_news_event(self):
        add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="MSN",
            title="Primeiro modelo portugues de inteligencia artificial AMALIA vai ser lancado em julho",
            url="https://example.com/amalia-msn",
            published_at=self.today,
            engagement_score=80,
            summary="AMALIA sera lancado em codigo aberto.",
            why_it_matters="Modelo portugues de IA.",
            status="verified",
        )
        add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="TSF",
            title="Amalia: ferramenta de Inteligencia Artificial portuguesa vai ser apresentada daqui a um mes",
            url="https://example.com/amalia-tsf",
            published_at=self.today,
            engagement_score=70,
            summary="Ferramenta portuguesa de IA apresentada em breve.",
            why_it_matters="Mesmo evento noticiado por outra fonte.",
            status="verified",
        )

        candidates = weekly_candidates(load_radar_signals(self.root / "radar_signals.jsonl"), [], [], limit=5)

        self.assertEqual(len(candidates), 1)
        self.assertIn("AMALIA", candidates[0].title.upper())

    def test_newsletter_read_more_links_match_news_urls(self):
        for index in range(5):
            self._signal(f"AI source story {index}", 50 + index)

        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=load_radar_signals(self.root / "radar_signals.jsonl"),
            trend_signals=[],
            final_posts=[],
        )

        for score in range(50, 55):
            self.assertIn(f'href="https://example.com/{score}"', issue.html)
        self.assertNotIn('href="https://ptia.pt" style="color:#1B1A17;text-decoration:none;">AI source story', issue.html)

    def test_newsletter_repairs_legacy_question_mark_encoding(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="encoding_topic",
            channel="site",
            title="Zhipu AI lan?ou modelo que refor?a competi??o",
            body="A press?o sobre a??es ligadas ? intelig?ncia artificial mudou a efici?ncia do mercado.",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com/zhipu"],
        )
        performance = [
            ContentPerformance(
                performance_id="perf_encoding",
                draft_id=post.post_id,
                post_id="https://linkedin.com/posts/encoding",
                channel="site",
                published_at=self.today,
                topic=post.title,
                section="global",
                likes=10,
            )
        ]

        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=[],
            trend_signals=[],
            final_posts=load_final_posts(self.root / "final_posts.jsonl"),
            performance=performance,
            limit=1,
        )

        self.assertIn("lan\u00e7ou", issue.html)
        self.assertIn("refor\u00e7a", issue.html)
        self.assertIn("competi\u00e7\u00e3o", issue.html)
        self.assertIn("press\u00e3o", issue.html)
        self.assertIn("a\u00e7\u00f5es", issue.html)
        self.assertIn("intelig\u00eancia", issue.html)
        self.assertFalse(has_suspicious_encoding(issue.html))
        self.assertFalse(has_suspicious_encoding(issue.text))

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

        self.assertIn("PTIA", issue.html)
        self.assertIn("Weekly", issue.html)
        self.assertIn("Ler mais", issue.html)
        self.assertIn("ptia-wordmark-navy-transparent.png", issue.html)
        self.assertIn("#051A3B", issue.html)
        self.assertNotIn("#BF4A2E", issue.html)
        self.assertNotIn("Fonte original", issue.html)
        self.assertNotIn("O que isto significa para Portugal", issue.html)
        self.assertNotIn("O que isto significa para Portugal", issue.text)
        for broken in ["Edi??o", "Jo?o", "M?todo", "C?mara", "ru?do", "?til", "subscri??o", "prefer?ncias"]:
            self.assertNotIn(broken, issue.html)
        self.assertIn("Edi\u00e7\u00e3o", issue.html)
        self.assertIn("Jo\u00e3o Ferreira", issue.html)
        self.assertIn("M\u00e9todo", issue.html)
        self.assertEqual(len(issue.item_ids), 5)
        self.assertEqual(issue.selection_mode, "performance")
        self.assertEqual(load_newsletter_issues(self.root / "newsletter_issues.jsonl")[0].issue_id, issue.issue_id)

    def test_newsletter_links_to_ptia_and_uses_selected_story_image(self):
        lead_post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="lead_topic",
            channel="site",
            title="Lead AI Story",
            body="Texto editorial do lead.",
            hashtags="",
            image_prompt="",
            source_urls=["https://example.com/original-lead"],
            image_path=str(self.root / "lead-image.jpg"),
        )
        other_post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="other_topic",
            channel="site",
            title="Quantum Chips Funding",
            body="Financiamento para chips quanticos.",
            hashtags="",
            image_prompt="",
            source_urls=["https://example.com/original-other"],
            image_path=str(self.root / "wrong-image.jpg"),
        )
        performance = [
            ContentPerformance(
                performance_id="perf_lead",
                draft_id=lead_post.post_id,
                post_id="https://linkedin.com/posts/lead",
                channel="site",
                published_at=self.today,
                topic=lead_post.title,
                section="site",
                likes=100,
            ),
            ContentPerformance(
                performance_id="perf_other",
                draft_id=other_post.post_id,
                post_id="https://linkedin.com/posts/other",
                channel="site",
                published_at=self.today,
                topic=other_post.title,
                section="site",
                likes=1,
            ),
        ]

        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=[],
            trend_signals=[],
            final_posts=load_final_posts(self.root / "final_posts.jsonl"),
            performance=performance,
            limit=2,
        )

        self.assertIn("lead-image.jpg", issue.html)
        self.assertIn("wrong-image.jpg", issue.html)
        self.assertIn("ptia-news-thumb", issue.html)
        self.assertIn("Ler mais", issue.html)
        self.assertIn("https://ptia.pt/artigos/lead-ai-story-", issue.html)
        self.assertNotIn("https://example.com/original-lead", issue.html)
        self.assertNotIn("Fonte original", issue.html)

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

    def test_weekly_owned_post_candidates_dedupe_same_topic(self):
        first = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="same_ai_event",
            channel="linkedin",
            title="AI company announces same product",
            body="Primeira versao do mesmo evento.",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com/a"],
        )
        duplicate = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="same_ai_event",
            channel="site",
            title="Same AI product gets second writeup",
            body="Segunda versao do mesmo evento.",
            hashtags="",
            image_prompt="",
            source_urls=["https://example.com/b"],
        )
        performance = [
            ContentPerformance(
                performance_id="perf_first",
                draft_id=first.post_id,
                post_id="https://linkedin.com/posts/a",
                channel="linkedin",
                published_at=self.today,
                topic=first.title,
                section="business",
                likes=20,
            ),
            ContentPerformance(
                performance_id="perf_duplicate",
                draft_id=duplicate.post_id,
                post_id="https://ptia.pt/artigos/b",
                channel="site",
                published_at=self.today,
                topic=duplicate.title,
                section="business",
                likes=10,
            ),
        ]

        candidates = weekly_owned_post_candidates(performance, [first, duplicate], limit=5)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].event_key, "same_ai_event")

    def test_site_readership_metrics_are_valid_performance_signals(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_site",
            channel="site",
            title="Artigo PTIA",
            body="Leitura editorial.",
            hashtags="",
            image_prompt="",
            source_urls=["https://example.com/source"],
        )
        performance = ContentPerformance(
            performance_id="perf_site",
            draft_id=post.post_id,
            post_id=post.post_id,
            channel="site",
            published_at=self.today,
            topic=post.title,
            section="site",
            site_views=25,
            unique_visitors=15,
        )

        candidates = weekly_owned_post_candidates([performance], [post])

        self.assertEqual(len(candidates), 1)
        self.assertGreater(candidates[0].score, 0)

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

    def test_generate_weekly_issue_accepts_target_send_time(self):
        for index in range(5):
            self._signal(f"AI story {index}", 50 + index)

        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=load_radar_signals(self.root / "radar_signals.jsonl"),
            trend_signals=[],
            final_posts=[],
            send_at="2026-06-05T09:00:00+01:00",
            issue_date=datetime(2026, 6, 5, tzinfo=timezone.utc).date(),
        )

        self.assertEqual(issue.send_at, "2026-06-05T09:00:00+01:00")
        self.assertEqual(issue.selection_mode, "editorial")
        self.assertNotIn("melhor tracking", issue.intro.lower())
        self.assertNotIn("a nossa audiência mostrou", issue.intro.lower())
        self.assertIn("Sexta-feira", issue.html)
        self.assertIn("05 JUN 2026", issue.html)

    def test_newsletter_includes_only_recent_published_linkedin_debates(self):
        self._signal("AI story", 50)
        created_at = datetime.now(timezone.utc).isoformat()
        records = [
            {
                "status": "commented",
                "profile_name": f"Published {index}",
                "post_body": f"Post {index}",
                "comment_text": f"Public comment {index}",
                "post_url": f"https://linkedin.com/posts/{index}",
                "created_at": created_at,
            }
            for index in range(4)
        ]
        records.append(
            {
                "status": "draft",
                "profile_name": "Private draft",
                "post_body": "Unpublished post",
                "comment_text": "PRIVATE DRAFT CONTENT",
                "post_url": "https://linkedin.com/posts/draft",
                "created_at": created_at,
            }
        )
        comments_path = self.root / "linkedin_comments.jsonl"
        comments_path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )

        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=load_radar_signals(self.root / "radar_signals.jsonl"),
            trend_signals=[],
            final_posts=[],
        )

        self.assertNotIn("PRIVATE DRAFT CONTENT", issue.html)
        self.assertNotIn("PRIVATE DRAFT CONTENT", issue.text)
        self.assertEqual(issue.text.count("Discussão com Published"), 3)

    def test_update_newsletter_delivery_fields(self):
        for index in range(5):
            self._signal(f"AI story {index}", 50 + index)
        issue = generate_weekly_issue(
            self.root / "newsletter_issues.jsonl",
            radar_signals=load_radar_signals(self.root / "radar_signals.jsonl"),
            trend_signals=[],
            final_posts=[],
        )

        updated = update_newsletter_delivery(
            self.root / "newsletter_issues.jsonl",
            issue.issue_id,
            status="scheduled",
            send_at="2026-06-05T09:00:00+01:00",
            delivery_provider="brevo",
            provider_campaign_id="campaign_123",
            provider_status="ready",
            delivery_error="",
        )

        self.assertEqual(updated.status, "scheduled")
        self.assertEqual(updated.delivery_provider, "brevo")
        self.assertEqual(updated.provider_campaign_id, "campaign_123")
        self.assertEqual(updated.provider_status, "ready")


if __name__ == "__main__":
    unittest.main()
