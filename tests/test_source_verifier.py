import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from ptia_engine.search_providers import SearchCandidate
from ptia_engine.source_verifier import (
    VerificationResult,
    credible_source_name,
    discovery_source_name,
    domain_for_url,
    extract_credible_links,
    is_blocked_source_url,
    resolve_discovery_link,
    resolve_submitted_link,
    verify_search_candidate,
)


class SourceVerifierTests(unittest.TestCase):
    def test_detects_credible_source_domain(self):
        self.assertEqual(
            credible_source_name("https://www.anthropic.com/news/claude-for-small-business"),
            "Anthropic",
        )

    def test_normalises_www_domain(self):
        self.assertEqual(domain_for_url("https://www.reuters.com/technology/ai/"), "reuters.com")

    def test_rundown_is_discovery_only_not_final_source(self):
        url = "https://www.rundown.ai/articles/example-ai-story"
        self.assertEqual(credible_source_name(url), "")
        self.assertEqual(discovery_source_name(url), "The Rundown AI")

    def test_rejects_google_grounding_redirect_as_final_source(self):
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/example"
        self.assertTrue(is_blocked_source_url(url))
        self.assertEqual(credible_source_name(url), "")

        result = verify_search_candidate(
            SearchCandidate(
                title="Grounding redirect",
                url=url,
                source_name="Google Cloud",
                published_at=datetime.now(timezone.utc).date().isoformat(),
                summary="Not a final source.",
            )
        )

        self.assertEqual(result.status, "rejected")
        self.assertIn("fonte original", result.notes)

    def test_extracts_credible_links_from_discovery_page(self):
        html = """
        <a href="https://www.rundown.ai/articles/internal">Internal</a>
        <a href="https://openai.com/news/example">OpenAI</a>
        <a href="https://social.example/post">Social</a>
        <a href="/relative">Relative</a>
        """
        self.assertEqual(
            extract_credible_links(html, "https://www.rundown.ai/articles/source"),
            ["https://openai.com/news/example"],
        )

    def test_resolves_rundown_link_to_original_source(self):
        today = datetime.now(timezone.utc).date().isoformat()
        original = VerificationResult(
            status="verified",
            source_name="OpenAI",
            title="OpenAI source",
            published_at=today,
            summary="Original source summary",
            notes="Verified",
            verified_url="https://openai.com/news/example",
        )
        html = '<a href="https://openai.com/news/example">Original source</a>'

        with (
            patch("ptia_engine.source_verifier.fetch_page_html", return_value=html),
            patch("ptia_engine.source_verifier.verify_url", return_value=original),
        ):
            result = resolve_discovery_link("https://www.rundown.ai/articles/example-ai-story")

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.source_name, "OpenAI")
        self.assertIn("The Rundown AI", result.notes)

    def test_detects_portuguese_credible_sources(self):
        self.assertEqual(
            credible_source_name("https://eco.sapo.pt/2026/05/14/noticia-ai/"),
            "ECO",
        )
        self.assertEqual(
            credible_source_name("https://www.portugal.gov.pt/pt/gc24/comunicacao/noticia"),
            "Governo de Portugal",
        )
        self.assertEqual(
            credible_source_name("https://jornaleconomico.sapo.pt/noticias/ia/"),
            "Jornal Económico",
        )

    def test_resolves_untrusted_link_with_grounded_candidate(self):
        today = datetime.now(timezone.utc).date().isoformat()

        class FakeProvider:
            available = True

            def search_for_link(self, **_kwargs):
                return [
                    SearchCandidate(
                        title="Reuters AI story",
                        url="https://www.reuters.com/technology/artificial-intelligence/story",
                        source_name="Reuters",
                        published_at=today,
                        summary="AI story summary",
                    )
                ]

        with patch(
            "ptia_engine.source_verifier.fetch_page_metadata",
            return_value=("Reuters AI story", "AI story summary", today),
        ):
            result = resolve_submitted_link(
                "https://social.example/post/123",
                provider=FakeProvider(),
            )

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.source_name, "Reuters")
        self.assertEqual(
            result.verified_url,
            "https://www.reuters.com/technology/artificial-intelligence/story",
        )


if __name__ == "__main__":
    unittest.main()
