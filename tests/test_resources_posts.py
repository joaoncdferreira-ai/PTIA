import shutil
import unittest
import uuid
from datetime import date
from pathlib import Path

from ptia_engine.resources_posts import (
    METHODOLOGY_SOURCE_URL,
    RESOURCE_SOURCE_URL,
    build_saturday_resource_posts,
    upsert_saturday_resource_posts,
)
from ptia_engine.storage import load_final_posts


class SaturdayResourcesPostsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.index = {
            "edition": "2026-W26",
            "people": [
                {
                    "rank": 1,
                    "name": "Daniela Braga",
                    "score_band": "Destaque",
                    "confidence": "provisória",
                }
            ],
            "companies": [
                {
                    "rank": 1,
                    "name": "Feedzai",
                    "score_band": "Destaque",
                    "confidence": "provisória",
                }
            ],
            "tools": [
                {
                    "rank": 1,
                    "name": "Claude",
                    "category_ranks": {"coding": 1},
                    "category_confidence": {"coding": "alta"},
                },
                {
                    "rank": 2,
                    "name": "Perplexity",
                    "category_ranks": {"pesquisa": 1},
                    "category_confidence": {"pesquisa": "média"},
                },
                {
                    "rank": 3,
                    "name": "n8n",
                    "category_ranks": {"automacoes": 1},
                    "category_confidence": {"automacoes": "editorial"},
                },
            ],
            "prompts": [
                {
                    "rank": 1,
                    "title": "Verificar uma alegação e as suas fontes",
                }
            ],
            "entity_archive": {
                "companies": [
                    {
                        "name": "Unbabel",
                        "status": "liquidated",
                        "status_reason": (
                            "A tecnologia foi adquirida e a sociedade entrou em liquidação."
                        ),
                        "verification": {
                            "sources": [
                                {
                                    "label": "TransPerfect",
                                    "url": "https://www.transperfect.com/about/press/example",
                                },
                                {
                                    "label": "Lusa",
                                    "url": "https://aman-alliance.org/Home/ContentDetail/example",
                                },
                            ]
                        },
                    }
                ],
                "people": [],
            },
        }

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_builds_one_evidence_led_radar_post(self):
        posts = build_saturday_resource_posts(self.index, target_date=date(2026, 6, 27))

        self.assertEqual([post.slot for post in posts], ["radar"])
        post = posts[0]
        self.assertIn("Um ranking só é útil se também souber retirar nomes.", post.body)
        self.assertIn("Feedzai", post.body)
        self.assertIn("Daniela Braga", post.body)
        self.assertIn("Unbabel sai do índice ativo", post.body)
        self.assertIn("Código: Claude", post.body)
        self.assertIn("Verificar uma alegação", post.body)
        self.assertIn("Slide 7", post.visual_brief)
        self.assertIn("#051A3B", post.image_prompt)
        self.assertIn("sem laranja", post.image_prompt)
        self.assertIn("Texto visual a aplicar exatamente", post.image_prompt)
        self.assertIn(RESOURCE_SOURCE_URL, post.source_urls)
        self.assertIn(METHODOLOGY_SOURCE_URL, post.source_urls)
        self.assertIn(
            "https://aman-alliance.org/Home/ContentDetail/example",
            post.source_urls,
        )

    def test_upsert_creates_one_review_post_and_is_idempotent(self):
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

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].channel, "linkedin")
        self.assertEqual(stored[0].status, "needs_final_review")
        self.assertEqual(stored[0].image_status, "needs_review")
        self.assertEqual(stored[0].scheduled_time[11:16], "10:00")
        self.assertEqual(stored[0].source_urls, list(first[0].source_urls))
        self.assertGreater(len(stored[0].source_urls), 2)


if __name__ == "__main__":
    unittest.main()
