import unittest

from ptia_engine.drafts import make_template_drafts
from ptia_engine.models import ProcessedItem, RawArticle


class DraftTests(unittest.TestCase):
    def test_template_drafts_cover_expected_channels(self):
        article = RawArticle(
            article_id="art_test",
            source_id="openai_news",
            source_name="OpenAI News",
            title_original="OpenAI launches an agent workflow",
            url="https://example.com",
            raw_excerpt="A new workflow helps developers automate tasks with AI agents.",
        )
        item = ProcessedItem(
            item_id="item_test",
            article_id="art_test",
            source_id="openai_news",
            source_name="OpenAI News",
            title_original=article.title_original,
            source_url=article.url,
            section="builders",
            relevance_score=8,
            hype_score=1,
            portugal_relevance_score=2,
            builder_relevance_score=8,
            business_relevance_score=3,
            should_cover=True,
            reason="Useful for builders.",
        )

        drafts = make_template_drafts(item, article)

        formats = {draft.format for draft in drafts}
        self.assertEqual(len(drafts), 5)
        self.assertIn("linkedin_post", formats)
        self.assertIn("instagram_caption", formats)
        self.assertIn("instagram_carousel", formats)
        self.assertIn("site_short_article", formats)
        self.assertIn("newsletter_item", formats)
        self.assertTrue(all(article.url in (draft.body + draft.caption) or draft.carousel_outline for draft in drafts))


if __name__ == "__main__":
    unittest.main()
