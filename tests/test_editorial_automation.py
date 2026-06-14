import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ptia_engine.editorial_automation import EditorialAutomationService
from ptia_engine.models import RadarSignal
from ptia_engine.services.image_generation import GeneratedEditorialImage
from ptia_engine.storage import load_final_posts, write_jsonl


class _UnavailableSearch:
    available = False


class _FakeImageGenerator:
    def generate(self, post, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{post.topic_id}.jpg"
        path.write_bytes(b"image")
        return GeneratedEditorialImage(path=path, provider="test", model="test")


class EditorialAutomationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.data_dir = self.root / "data"
        self.data_dir.mkdir(parents=True)
        (self.data_dir / "buffer_channels.json").write_text(
            '{"disabled_channels": ["x"], "channels": {}}',
            encoding="utf-8",
        )
        write_jsonl(
            self.data_dir / "radar_signals.jsonl",
            [
                RadarSignal(
                    signal_id="signal_1",
                    source_type="news",
                    source_name="Lusa",
                    title="Centro português lança plataforma de IA para hospitais",
                    url="https://example.com/saude",
                    published_at="2026-06-14T08:00:00+00:00",
                    engagement_score=75,
                    summary=(
                        "Um centro português lançou uma plataforma de inteligência artificial "
                        "que ajuda hospitais a organizar informação clínica. A solução foi "
                        "testada por equipas médicas em contexto real."
                    ),
                    why_it_matters=(
                        "A adoção pode reduzir trabalho administrativo e libertar tempo clínico."
                    ),
                    status="verified",
                )
            ],
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _service(self):
        return EditorialAutomationService(
            repo_root=self.root,
            data_dir=self.data_dir,
            search_provider=_UnavailableSearch(),
            image_generator=_FakeImageGenerator(),
        )

    @patch("ptia_engine.use_cases.curation.GeminiGroundedSearchProvider")
    def test_run_stops_at_review_and_does_not_duplicate_a_full_queue(self, provider_cls):
        provider_cls.return_value.available = False

        first = self._service().run(limit=1, scout=False)
        posts = load_final_posts(self.data_dir / "final_posts.jsonl")

        self.assertEqual(first.status, "completed")
        self.assertEqual(len(first.created_topic_ids), 1)
        self.assertEqual({post.status for post in posts}, {"needs_final_review"})
        self.assertTrue(all(post.image_path for post in posts))
        self.assertTrue(all(not post.buffer_post_id for post in posts))
        self.assertTrue(all(not post.scheduled_time for post in posts))

        second = self._service().run(limit=1, scout=False)
        posts_after = load_final_posts(self.data_dir / "final_posts.jsonl")

        self.assertEqual(second.status, "completed")
        self.assertEqual(second.created_topic_ids, [])
        self.assertEqual(len(posts_after), len(posts))

    @patch("ptia_engine.use_cases.curation.GeminiGroundedSearchProvider")
    def test_replacement_bypasses_queue_capacity_but_remains_in_review(self, provider_cls):
        provider_cls.return_value.available = False
        service = self._service()
        first = service.run(limit=1, scout=False)
        original_topic = first.created_topic_ids[0]

        write_jsonl(
            self.data_dir / "radar_signals.jsonl",
            [
                *service.signal_repo.load_all(),
                RadarSignal(
                    signal_id="signal_2",
                    source_type="news",
                    source_name="Reuters",
                    title="Novo modelo reduz energia usada por agentes de IA",
                    url="https://example.com/energia",
                    published_at="2026-06-14T09:00:00+00:00",
                    engagement_score=72,
                    summary=(
                        "Um novo modelo reduziu a energia utilizada por agentes de inteligência "
                        "artificial durante testes independentes. Os resultados foram publicados "
                        "com a metodologia e as limitações do ensaio."
                    ),
                    why_it_matters=(
                        "A eficiência pode reduzir custos de operação para produtos com muitos agentes."
                    ),
                    status="verified",
                ),
            ],
        )

        replacement = service.replace_topic(original_topic)
        active = [
            post
            for post in load_final_posts(self.data_dir / "final_posts.jsonl")
            if post.status == "needs_final_review"
        ]

        self.assertEqual(replacement.status, "completed")
        self.assertEqual(len(replacement.created_topic_ids), 1)
        self.assertNotEqual(replacement.created_topic_ids[0], original_topic)
        self.assertTrue(active)
        self.assertEqual({post.topic_id for post in active}, set(replacement.created_topic_ids))


if __name__ == "__main__":
    unittest.main()
