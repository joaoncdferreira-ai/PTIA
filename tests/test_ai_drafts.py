import unittest

from ptia_engine.ai_drafts import generate_ai_draft_payload, payload_to_drafts
from ptia_engine.models import ProcessedItem, RawArticle


class AIDraftTests(unittest.TestCase):
    def test_payload_to_drafts_creates_expected_formats(self):
        item = ProcessedItem(
            item_id="item_1",
            article_id="art_1",
            source_id="source",
            source_name="Source",
            title_original="Original title",
            source_url="https://example.com",
            section="business",
            relevance_score=8,
            hype_score=1,
            portugal_relevance_score=5,
            builder_relevance_score=3,
            business_relevance_score=8,
            should_cover=True,
            reason="Useful.",
        )
        payload = {
            "title_pt": "Titulo PTIA",
            "summary_pt": "Resumo",
            "why_it_matters_pt": "Importa",
            "portugal_angle_pt": "Portugal",
            "key_takeaways": ["Um", "Dois"],
            "linkedin_post": "LinkedIn",
            "instagram_caption": "Instagram",
            "carousel_slides": [
                {"headline": "H1", "text": "T1", "visual": "V1"},
                {"headline": "H2", "text": "T2", "visual": "V2"},
                {"headline": "H3", "text": "T3", "visual": "V3"},
                {"headline": "H4", "text": "T4", "visual": "V4"},
                {"headline": "H5", "text": "T5", "visual": "V5"},
            ],
            "site_entry": "Site",
            "newsletter_item": "Newsletter",
            "risk_notes": "Risk",
        }

        drafts = payload_to_drafts(item, payload, "gpt-test")

        self.assertEqual(len(drafts), 5)
        self.assertEqual({draft.status for draft in drafts}, {"needs_edit"})
        self.assertIn("instagram_carousel", {draft.format for draft in drafts})

    def test_template_provider_generates_payload_without_api_key(self):
        item = ProcessedItem(
            item_id="item_1",
            article_id="art_1",
            source_id="source",
            source_name="Source",
            title_original="AI agents in business",
            source_url="https://example.com",
            section="business",
            relevance_score=8,
            hype_score=1,
            portugal_relevance_score=6,
            builder_relevance_score=4,
            business_relevance_score=8,
            should_cover=True,
            reason="Useful for Portuguese companies.",
        )
        article = RawArticle(
            article_id="art_1",
            source_id="source",
            source_name="Source",
            title_original="AI agents in business",
            url="https://example.com",
            raw_excerpt="A company launched a new AI agent workflow.",
        )

        payload, cost = generate_ai_draft_payload(item, article, provider="template")

        self.assertEqual(cost, 0.0)
        self.assertIn("linkedin_post", payload)
        self.assertGreaterEqual(len(payload["carousel_slides"]), 5)
        self.assertIn(article.url, payload["site_entry"])


if __name__ == "__main__":
    unittest.main()
