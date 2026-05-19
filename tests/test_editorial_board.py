import base64
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ptia_engine.buffer_api import BufferPostResult
from ptia_engine.editorial_board import (
    add_editorial_topic,
    add_final_post,
    add_radar_signal,
    update_final_post_copy,
    update_final_post_status,
    update_signal_status,
)
from ptia_engine.dashboard import (
    DashboardState,
    _build_final_pack_from_signal,
    _generate_final_image,
    _normalise_hashtags,
    _schedule_post_in_buffer,
    _site_feed,
    _upload_final_image,
)
from ptia_engine.storage import load_editorial_topics, load_final_posts, load_radar_signals


class EditorialBoardTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_new_flow_creates_signal_topic_and_final_post(self):
        signal = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Google",
            title="Gemini Intelligence",
            url="https://example.com",
            published_at=datetime.now(timezone.utc).date().isoformat(),
            summary="Fresh AI news.",
        )
        topic = add_editorial_topic(
            self.root / "editorial_topics.jsonl",
            title="Android turns into an AI layer",
            thesis="The phone is becoming an assistant, not just an app launcher.",
            portugal_angle="Portuguese companies should revisit mobile workflows.",
            audience="business",
            source_signal_ids=[signal.signal_id],
            urgency_score=8,
        )
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id=topic.topic_id,
            channel="linkedin",
            title="O telemovel vai trabalhar mais por ti",
            body="Texto final.",
            hashtags="#IA #Portugal",
            image_prompt="Clean editorial image.",
            source_urls=["https://example.com"],
        )
        update_final_post_status(self.root / "final_posts.jsonl", post.post_id, "approved_for_schedule")

        self.assertEqual(len(load_radar_signals(self.root / "radar_signals.jsonl")), 1)
        self.assertEqual(len(load_editorial_topics(self.root / "editorial_topics.jsonl")), 1)
        self.assertEqual(load_final_posts(self.root / "final_posts.jsonl")[0].status, "approved_for_schedule")

    def test_signal_requires_exact_recent_date(self):
        with self.assertRaises(ValueError):
            add_radar_signal(
                self.root / "radar_signals.jsonl",
                source_type="instagram",
                source_name="Ranking",
                title="Vague month is not enough",
                url="https://example.com",
                published_at="2026-05",
            )

    def test_verifying_signal_can_wait_for_date(self):
        signal = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Unverified",
            title="Needs verification",
            url="https://example.com/story",
            status="verifying",
            require_recent=False,
        )

        self.assertEqual(signal.status, "verifying")

    def test_build_final_pack_from_verified_signal(self):
        signal = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="AI changes enterprise workflows",
            url="https://www.reuters.com/technology/ai/story",
            published_at=datetime.now(timezone.utc).date().isoformat(),
            summary="Companies are adopting AI in practical workflows.",
            why_it_matters="Relevant for Portuguese companies tracking productivity.",
            status="verified",
        )

        result = _build_final_pack_from_signal(DashboardState(self.root), signal.signal_id)

        self.assertEqual(len(result["posts"]), 3)
        self.assertEqual({post["channel"] for post in result["posts"]}, {"linkedin", "instagram", "site"})
        linkedin = next(post for post in result["posts"] if post["channel"] == "linkedin")
        self.assertNotIn("A notícia", linkedin["body"])
        self.assertNotIn("A leitura PTIA", linkedin["body"])
        self.assertNotIn("O que observar", linkedin["body"])
        self.assertIn("Fonte original:", linkedin["body"])
        self.assertNotIn("separar sinal de ruído", linkedin["body"].casefold())
        self.assertEqual(load_radar_signals(self.root / "radar_signals.jsonl")[0].status, "used")

    def test_update_final_post_copy_records_feedback(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Old",
            body="Old body",
            hashtags="#IA",
            image_prompt="Prompt",
            source_urls=["https://example.com"],
        )

        updated = update_final_post_copy(
            self.root / "final_posts.jsonl",
            post.post_id,
            title="New",
            body="New body",
            notes="Feedback: mais ponto de vista",
        )

        self.assertEqual(updated.title, "New")
        self.assertIn("mais ponto de vista", updated.editor_notes)

    def test_generate_final_image_updates_post(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
        )

        updated = _generate_final_image(DashboardState(self.root), post.post_id, feedback="mais contraste")

        self.assertTrue(Path(updated.image_path).exists())
        self.assertEqual(updated.image_status, "needs_review")

    def test_upload_final_image_formats_channel_variants_for_package(self):
        linkedin = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
        )
        instagram = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
        )
        image = Image.new("RGB", (1400, 900), (18, 54, 92))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

        updated = _upload_final_image(DashboardState(self.root), linkedin.post_id, "master.png", data_url)

        self.assertIn("linkedin", updated.image_variants)
        self.assertIn("instagram", updated.image_variants)
        self.assertTrue(Path(updated.image_variants["linkedin"]).exists())
        self.assertTrue(Path(updated.image_variants["instagram"]).exists())

        posts = {post.post_id: post for post in load_final_posts(self.root / "final_posts.jsonl")}
        self.assertEqual(posts[instagram.post_id].image_path, updated.image_path)
        self.assertIn("instagram", posts[instagram.post_id].image_variants)

    def test_instagram_with_local_image_gets_public_url_for_buffer(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
            image_path=str(self.root / "image.png"),
        )
        Path(post.image_path).write_bytes(b"not-a-real-image-but-present")
        (self.root / "buffer_channels.json").write_text(
            '{"channels":{"instagram":"chan_instagram"}}',
            encoding="utf-8",
        )

        with patch("ptia_engine.dashboard.BufferClient") as client_cls:
            client_cls.return_value.create_scheduled_post.return_value = BufferPostResult(id="buffer_1")
            updated = _schedule_post_in_buffer(
                DashboardState(self.root),
                post.post_id,
                "2026-05-19T09:00:00+01:00",
            )

        self.assertEqual(updated.status, "scheduled")
        self.assertEqual(updated.buffer_post_id, "buffer_1")
        call_kwargs = client_cls.return_value.create_scheduled_post.call_args.kwargs
        self.assertEqual(call_kwargs["image_url"], "https://ptia.pt/assets/final/image.png")
        self.assertTrue((self.root.parent / "site" / "assets" / "final" / "image.png").exists())

    def test_site_feed_uses_scheduled_site_posts(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="site",
            title="Entrada site",
            body="Texto site",
            hashtags="",
            image_prompt="",
            source_urls=["https://example.com"],
        )
        update_final_post_status(
            self.root / "final_posts.jsonl",
            post.post_id,
            "scheduled",
            scheduled_time="2026-05-15T09:00:00+01:00",
        )

        feed = _site_feed(DashboardState(self.root))

        self.assertEqual(feed["posts"][0]["title"], "Entrada site")

    def test_dashboard_radar_count_only_counts_radar_stage(self):
        today = datetime.now(timezone.utc).date().isoformat()
        active = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="Active radar",
            url="https://example.com/active-radar",
            published_at=today,
            status="new",
            require_recent=False,
        )
        verified = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="Verified",
            url="https://example.com/verified",
            published_at=today,
            status="verified",
        )
        used = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="Used",
            url="https://example.com/used",
            published_at=today,
            status="verified",
        )
        update_signal_status(self.root / "radar_signals.jsonl", used.signal_id, "used")

        snapshot = DashboardState(self.root).snapshot()

        self.assertEqual(snapshot["counts"]["radar_signals_v2"], 1)
        self.assertEqual(snapshot["radar_inbox_signals"][0]["signal_id"], active.signal_id)
        self.assertEqual(snapshot["counts"]["verified_selection"], 1)
        self.assertEqual(snapshot["verified_signals"][0]["signal_id"], verified.signal_id)

    def test_normalise_hashtags_removes_python_list_syntax(self):
        hashtags = _normalise_hashtags(
            "['#InteligenciaArtificial', '#IA', '#Portugal', '#MercadoDeTrabalho', '#PTIA']",
            "linkedin",
        )

        self.assertEqual(hashtags, "#InteligenciaArtificial #IA #Portugal #MercadoDeTrabalho")

    def test_due_scheduled_posts_move_to_published_on_snapshot(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Post antigo",
            body="Texto",
            hashtags="['#IA', '#Portugal']",
            image_prompt="",
            source_urls=[],
        )
        update_final_post_status(
            self.root / "final_posts.jsonl",
            post.post_id,
            "scheduled",
            scheduled_time="2000-01-01T09:00:00+00:00",
        )

        snapshot = DashboardState(self.root).snapshot()

        self.assertEqual(snapshot["counts"]["final_scheduled"], 0)
        self.assertEqual(snapshot["counts"]["final_published"], 1)
        published = load_final_posts(self.root / "final_posts.jsonl")[0]
        self.assertEqual(published.status, "published")
        self.assertEqual(published.hashtags, "#IA #Portugal")


if __name__ == "__main__":
    unittest.main()
