import unittest

from ptia_engine.classifier import classify_heuristic
from ptia_engine.models import RawArticle


class ClassifierTests(unittest.TestCase):
    def test_heuristic_marks_agent_business_story_as_candidate(self):
        article = RawArticle(
            article_id="art_test",
            source_id="openai_news",
            source_name="OpenAI News",
            title_original="OpenAI launches new agents for enterprise developers",
            url="https://example.com",
            raw_excerpt="The new agent API helps developers build enterprise workflows.",
            language="en",
            country="US",
        )

        item = classify_heuristic(article)

        self.assertTrue(item.should_cover)
        self.assertEqual(item.editorial_status, "needs_review")
        self.assertGreaterEqual(item.builder_relevance_score, 7)

    def test_heuristic_rejects_low_signal_story(self):
        article = RawArticle(
            article_id="art_test_low",
            source_id="misc",
            source_name="Misc",
            title_original="Company updates its website footer",
            url="https://example.com",
            raw_excerpt="A small visual update was shipped today.",
            language="en",
            country="US",
        )

        item = classify_heuristic(article)

        self.assertFalse(item.should_cover)
        self.assertEqual(item.editorial_status, "rejected")


if __name__ == "__main__":
    unittest.main()
