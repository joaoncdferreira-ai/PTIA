import shutil
import unittest
import uuid
from datetime import date
from pathlib import Path

from ptia_engine.resources_posts import build_saturday_resource_posts, upsert_saturday_resource_posts
from ptia_engine.storage import load_final_posts


class SaturdayResourcesPostsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.index = {
            "edition": "2026-W26",
            "people": [
                {"rank": 1, "name": "Daniela Braga", "score": 82.0},
                {"rank": 2, "name": "Vasco Pedro", "score": 80.4},
                {"rank": 3, "name": "Nuno Sebastião", "score": 78.7},
                {"rank": 4, "name": "Arlindo Oliveira", "score": 77.1},
                {"rank": 5, "name": "Ana Paiva", "score": 75.4},
            ],
            "companies": [
                {"rank": 1, "name": "Feedzai", "score": 86.5},
                {"rank": 2, "name": "Sword Health", "score": 84.0},
                {"rank": 3, "name": "Defined.ai", "score": 82.7},
                {"rank": 4, "name": "Unbabel", "score": 80.7},
                {"rank": 5, "name": "Talkdesk", "score": 77.0},
            ],
            "tools": [
                {"rank": 1, "name": "ChatGPT", "score": 100.0},
                {"rank": 2, "name": "Canva Magic Studio", "score": 98.2},
                {"rank": 3, "name": "Figma AI", "score": 98.0},
                {"rank": 4, "name": "NotebookLM", "score": 97.0},
                {"rank": 5, "name": "Perplexity", "score": 97.0},
            ],
            "prompts": [
                {"rank": 1, "title": "Verificar uma alegação e as suas fontes", "score": 96.9},
                {"rank": 2, "title": "Transformar informação numa decisão executiva", "score": 96.1},
                {"rank": 3, "title": "Revisão de código orientada para risco", "score": 95.3},
                {"rank": 4, "title": "Testar uma estratégia com contraditório sério", "score": 94.5},
                {"rank": 5, "title": "Explicar um conceito complexo em português claro", "score": 93.6},
            ],
        }

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_builds_four_editorial_resource_posts(self):
        posts = build_saturday_resource_posts(self.index, target_date=date(2026, 6, 27))

        self.assertEqual([post.slot for post in posts], ["mapa", "builders", "ferramentas", "prompts"])
        self.assertIn("A IA em português precisa de mais do que notícias.", posts[0].body)
        self.assertIn("Daniela Braga", posts[1].body)
        self.assertIn("Feedzai", posts[1].body)
        self.assertIn("ChatGPT", posts[2].body)
        self.assertIn("Verificar uma alegação", posts[3].body)
        self.assertIn("#051A3B", posts[0].image_prompt)
        self.assertIn("sem laranja", posts[0].image_prompt)
        self.assertIn("Texto visual a aplicar exatamente", posts[0].image_prompt)

    def test_upsert_creates_review_posts_for_saturday_and_is_idempotent(self):
        posts_path = self.root / "final_posts.jsonl"
        first = upsert_saturday_resource_posts(
            posts_path,
            self.index,
            target_date=date(2026, 6, 27),
            created_at="2026-06-26T18:00:00+00:00",
        )
        second = upsert_saturday_resource_posts(
            posts_path,
            self.index,
            target_date=date(2026, 6, 27),
            created_at="2026-06-26T18:05:00+00:00",
        )
        stored = load_final_posts(posts_path)

        self.assertEqual(len(first), 4)
        self.assertEqual(len(second), 4)
        self.assertEqual(len(stored), 4)
        self.assertEqual({post.channel for post in stored}, {"linkedin"})
        self.assertEqual({post.status for post in stored}, {"needs_final_review"})
        self.assertEqual({post.image_status for post in stored}, {"needs_review"})
        self.assertEqual([post.scheduled_time[11:16] for post in stored], ["09:30", "12:30", "16:30", "19:00"])
        self.assertTrue(all(post.source_urls == ["https://ptia.pt/recursos/"] for post in stored))


if __name__ == "__main__":
    unittest.main()
