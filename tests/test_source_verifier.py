import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError
from unittest.mock import patch

from ptia_engine.search_providers import SearchCandidate
from ptia_engine.source_verifier import (
    GLOBAL_NEWS_MEDIA_DOMAINS,
    PORTUGUESE_NEWS_MEDIA_DOMAINS,
    VerificationResult,
    credible_source_name,
    discovery_source_name,
    domain_for_url,
    extract_credible_links,
    is_blocked_source_url,
    resolve_discovery_link,
    resolve_submitted_link,
    verify_search_candidate,
    verify_url,
)


class SourceVerifierTests(unittest.TestCase):
    def test_detects_credible_source_domain(self):
        self.assertEqual(
            credible_source_name("https://www.anthropic.com/news/claude-for-small-business"),
            "Anthropic",
        )
        self.assertEqual(
            credible_source_name("https://www.gartner.com/en/newsroom/press-releases/example"),
            "Gartner",
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

    def test_verified_page_uses_grounded_title_when_metadata_returns_url(self):
        candidate = SearchCandidate(
            title="OpenAI lança um novo produto empresarial",
            url="https://openai.com/news/example",
            source_name="OpenAI",
            published_at=datetime.now(timezone.utc).date().isoformat(),
            summary="A empresa lançou um produto com novas capacidades para equipas.",
        )
        verified = VerificationResult(
            status="verified",
            source_name="OpenAI",
            title=candidate.url,
            published_at=candidate.published_at,
            summary="",
            notes="Data verificada pelo URL.",
            verified_url=candidate.url,
        )

        with patch("ptia_engine.source_verifier.verify_url", return_value=verified):
            result = verify_search_candidate(candidate)

        self.assertEqual(result.title, candidate.title)
        self.assertEqual(result.summary, candidate.summary)

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
        self.assertEqual(
            credible_source_name("https://www.apdc.pt/noticias/atualidade-nacional/exemplo"),
            "APDC",
        )

    def test_detects_researched_news_media_domains(self):
        self.assertGreaterEqual(len(GLOBAL_NEWS_MEDIA_DOMAINS), 995)
        self.assertGreaterEqual(len(PORTUGUESE_NEWS_MEDIA_DOMAINS), 20)
        self.assertEqual(
            credible_source_name(
                "https://www.wsj.com/cio-journal/this-cannes-film-cost-500-000-to-make"
            ),
            "WSJ",
        )
        self.assertEqual(
            credible_source_name("https://www.rtp.pt/noticias/economia/noticia"),
            "RTP Noticias",
        )
        self.assertEqual(
            credible_source_name("https://sicnoticias.pt/economia/2026-05-22/noticia"),
            "SIC Noticias",
        )
        self.assertEqual(
            credible_source_name("https://www.nytimes.com/2026/05/19/technology/meta-layoffs-ai.html"),
            "New York Times",
        )
        self.assertEqual(
            credible_source_name("https://edition.cnn.com/2026/05/20/tech/ai-executive-order"),
            "CNN",
        )

    def test_reuters_date_in_slug_passes_when_metadata_blocks(self):
        today = datetime.now(timezone.utc).date().isoformat()
        url = f"https://www.reuters.com/world/europe/story-title-{today}/?utm_source=chatgpt.com"

        with patch("ptia_engine.source_verifier.fetch_page_metadata", side_effect=RuntimeError("HTTP 401")):
            result = verify_url(url)

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.source_name, "Reuters")
        self.assertEqual(result.published_at, today)
        self.assertNotIn("utm_source", result.verified_url)

    def test_news_date_path_passes_when_metadata_blocks(self):
        today = datetime.now(timezone.utc).date()
        urls = [
            (
                f"https://www.nytimes.com/{today:%Y/%m/%d}/technology/meta-layoffs-ai.html",
                "New York Times",
            ),
            (
                f"https://edition.cnn.com/{today:%Y/%m/%d}/tech/ai-executive-order",
                "CNN",
            ),
        ]

        with patch("ptia_engine.source_verifier.fetch_page_metadata", side_effect=RuntimeError("HTTP 401")):
            for url, source_name in urls:
                with self.subTest(url=url):
                    result = verify_url(url)

                    self.assertEqual(result.status, "verified")
                    self.assertEqual(result.source_name, source_name)
                    self.assertEqual(result.published_at, today.isoformat())

    def test_gartner_press_release_slug_date_passes_when_metadata_blocks(self):
        today = datetime.now(timezone.utc).date()
        url = (
            f"https://www.gartner.com/en/newsroom/press-releases/{today:%Y-%m-%d}-"
            "gartner-says-applying-uniform-governance-across-ai-agents-will-lead-to-enterprise-ai-agent-failure"
        )

        with patch("ptia_engine.source_verifier.fetch_page_metadata", side_effect=RuntimeError("HTTP 403")):
            result = verify_url(url)

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.source_name, "Gartner")
        self.assertEqual(result.published_at, today.isoformat())

    def test_rejects_missing_article_even_when_url_contains_today(self):
        today = datetime.now(timezone.utc).date()
        url = f"https://www.forbes.com/sites/example/{today:%Y/%m/%d}/invented-story/"

        with patch(
            "ptia_engine.source_verifier.fetch_page_metadata",
            side_effect=HTTPError(url, 404, "Not Found", {}, None),
        ):
            result = verify_url(url)

        self.assertEqual(result.status, "rejected")
        self.assertIn("HTTP 404", result.notes)

    def test_apdc_visible_date_is_used_for_recency_rejection(self):
        html = """
        <html>
          <head><title>Portugal e Espanha formalizam candidatura conjunta</title></head>
          <body>
            <span class="date">2026-03-11</span>
            <p>Portugal e Espanha formalizam candidatura conjunta a gigafabrica de IA.</p>
          </body>
        </html>
        """

        with patch("ptia_engine.source_verifier.fetch_page_html", return_value=html):
            result = verify_url(
                "https://www.apdc.pt/noticias/atualidade-nacional/portugal-e-espanha-formalizam-candidatura-conjunta-a-gigafabrica-de-ia?utm_source=chatgpt.com"
            )

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.source_name, "APDC")
        self.assertEqual(result.published_at, "2026-03-11")

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
