import shutil
import unittest
import uuid
from copy import deepcopy
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
            "verification_summary": {
                "eligible": 0,
                "provisional": 2,
                "excluded": 1,
            },
            "tools": [
                {
                    "rank": 1,
                    "name": "Claude",
                    "best_for": "Revisão e implementação de código complexo.",
                    "category_ranks": {"coding": 1},
                    "category_scores": {"coding": 92.4},
                    "category_publication_status": {"coding": "ranked"},
                    "category_sources": {
                        "coding": [
                            {
                                "label": "Benchmark coding",
                                "url": "https://example.com/coding",
                            }
                        ]
                    },
                },
                {
                    "rank": 2,
                    "name": "ChatGPT",
                    "best_for": "Produtividade generalista.",
                    "category_ranks": {"produtividade": 1},
                    "category_scores": {"produtividade": 89.1},
                    "category_publication_status": {"produtividade": "ranked"},
                    "category_sources": {
                        "produtividade": [
                            {
                                "label": "Benchmark produtividade",
                                "url": "https://example.org/productivity",
                            }
                        ]
                    },
                },
                {
                    "rank": 3,
                    "name": "Figma AI",
                    "best_for": "Design de produto em equipa.",
                    "category_ranks": {"design": 1},
                    "category_scores": {"design": 91.8},
                    "category_publication_status": {"design": "ranked"},
                    "category_sources": {
                        "design": [
                            {
                                "label": "Benchmark design",
                                "url": "https://example.net/design",
                            }
                        ]
                    },
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
        self.assertIn("O melhor top não é o que tem mais nomes.", post.body)
        self.assertNotIn("Feedzai", post.body)
        self.assertNotIn("Daniela Braga", post.body)
        self.assertIn("Unbabel saiu do índice ativo", post.body)
        self.assertIn("Código — #1 Claude", post.body)
        self.assertIn("0/2 perfis cumprem o gate", post.body)
        self.assertIn("Verificar uma alegação", post.body)
        self.assertIn("Slide 8", post.visual_brief)
        self.assertIn("#071A33", post.image_prompt)
        self.assertIn("sem etiquetas vagas", post.image_prompt)
        self.assertIn("1080x1350", post.image_prompt)
        self.assertIn("Texto visual a aplicar exatamente", post.image_prompt)
        self.assertIn(RESOURCE_SOURCE_URL, post.source_urls)
        self.assertIn(METHODOLOGY_SOURCE_URL, post.source_urls)
        self.assertIn("https://example.com/coding", post.source_urls)
        self.assertIn(
            "https://aman-alliance.org/Home/ContentDetail/example",
            post.source_urls,
        )

    def test_radar_promotes_only_eligible_entity_leaders(self):
        index = deepcopy(self.index)
        index["companies"][0].update(
            eligibility="eligible",
            score=84.2,
            verification={
                "sources": [
                    {"label": "Fonte empresa", "url": "https://company.example/evidence"},
                    {"label": "Fonte empresa 2", "url": "https://company-news.example/evidence"},
                ]
            },
        )
        index["people"][0].update(
            eligibility="eligible",
            score=87.6,
            verification={
                "sources": [
                    {"label": "Fonte pessoa", "url": "https://person.example/evidence"},
                    {"label": "Fonte pessoa 2", "url": "https://person-news.example/evidence"},
                ]
            },
        )
        index["verification_summary"] = {
            "eligible": 2,
            "provisional": 0,
            "excluded": 1,
        }

        post = build_saturday_resource_posts(index, target_date=date(2026, 6, 27))[0]

        self.assertIn("Empresa — #1 Feedzai (índice 84/100)", post.body)
        self.assertIn("Pessoa — #1 Daniela Braga (índice 88/100)", post.body)
        self.assertIn("Slide 4: Empresa #1 · Feedzai", post.visual_brief)
        self.assertIn("Slide 5: Pessoa #1 · Daniela Braga", post.visual_brief)
        self.assertIn("https://company.example/evidence", post.source_urls)
        self.assertIn("https://person.example/evidence", post.source_urls)

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
