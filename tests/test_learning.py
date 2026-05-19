import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.classifier import classify_heuristic
from ptia_engine.learning import generate_learning_weights
from ptia_engine.models import ContentDraft, ContentPerformance, ProcessedItem, RawArticle
from ptia_engine.storage import append_jsonl


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write_post(self, index: int, source_id: str, section: str, likes: int):
        article_id = f"art_{index}"
        item_id = f"item_{index}"
        draft_id = f"draft_{index}"
        append_jsonl(
            self.root / "processed_items.jsonl",
            [
                ProcessedItem(
                    item_id=item_id,
                    article_id=article_id,
                    source_id=source_id,
                    source_name=source_id,
                    title_original=f"Title {index}",
                    source_url="https://example.com",
                    section=section,
                    relevance_score=7,
                    hype_score=1,
                    portugal_relevance_score=2,
                    builder_relevance_score=6,
                    business_relevance_score=3,
                    should_cover=True,
                    reason="Useful.",
                )
            ],
        )
        append_jsonl(
            self.root / "content_drafts.jsonl",
            [
                ContentDraft(
                    draft_id=draft_id,
                    item_id=item_id,
                    article_id=article_id,
                    channel="linkedin",
                    format="linkedin_post",
                    title=f"Title {index}",
                    body="Post",
                    status="published",
                )
            ],
        )
        append_jsonl(
            self.root / "content_performance.jsonl",
            [
                ContentPerformance(
                    performance_id=f"perf_{index}",
                    draft_id=draft_id,
                    post_id=f"post_{index}",
                    channel="linkedin",
                    published_at="2026-05-14T12:00:00+00:00",
                    topic=f"Title {index}",
                    section=section,
                    likes=likes,
                )
            ],
        )

    def test_learning_weights_wait_for_minimum_sample(self):
        self._write_post(1, "source_a", "builders", 10)

        weights = generate_learning_weights(
            self.root / "processed_items.jsonl",
            self.root / "content_drafts.jsonl",
            self.root / "content_performance.jsonl",
            min_samples=3,
        )

        self.assertEqual(weights["sample_count"], 1)
        self.assertEqual(weights["source_boosts"], {})
        self.assertIn("Amostra insuficiente", weights["recommendations"][0])

    def test_learning_boost_changes_heuristic_relevance(self):
        article = RawArticle(
            article_id="art_test",
            source_id="source_a",
            source_name="Source A",
            title_original="Small business AI workflow",
            url="https://example.com",
            raw_excerpt="A workflow update for business users.",
        )
        neutral = classify_heuristic(article)
        boosted = classify_heuristic(
            article,
            learning_weights={"source_boosts": {"source_a": {"boost": 2}}, "section_boosts": {}},
        )

        self.assertGreater(boosted.relevance_score, neutral.relevance_score)
        self.assertLessEqual(boosted.relevance_score, 10)


if __name__ == "__main__":
    unittest.main()
