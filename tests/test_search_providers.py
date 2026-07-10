import io
import os
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from ptia_engine.search_providers import GEMINI_SEARCH_DEFAULT_MODEL, GeminiGroundedSearchProvider


class SearchProvidersTests(unittest.TestCase):
    def test_default_search_model_uses_current_gemini_flash_alias(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = GeminiGroundedSearchProvider(api_key="test")

        self.assertEqual(provider.model, GEMINI_SEARCH_DEFAULT_MODEL)
        self.assertNotEqual(provider.model, "gemini-2.5-flash")

    def test_retries_deprecated_configured_model_with_default_alias(self):
        provider = GeminiGroundedSearchProvider(api_key="test", model="gemini-2.5-flash")
        calls = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"candidates":[{"content":{"parts":[{"text":"{}"}]}}]}'

        def fake_urlopen(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                body = b'{"error":{"message":"This model models/gemini-2.5-flash is no longer available.","status":"NOT_FOUND"}}'
                raise HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(body))
            return FakeResponse()

        with patch("ptia_engine.search_providers.urlopen_direct", fake_urlopen):
            response = provider._post_generate_content({"contents": []})

        self.assertEqual(response["candidates"][0]["content"]["parts"][0]["text"], "{}")
        self.assertIn("gemini-2.5-flash", calls[0])
        self.assertIn(GEMINI_SEARCH_DEFAULT_MODEL, calls[1])
        self.assertEqual(provider.model, GEMINI_SEARCH_DEFAULT_MODEL)

    def test_extracts_json_candidates_from_gemini_response(self):
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"candidates":[{"title":"AI news","source_url":"https://openai.com/news/example","source_name":"OpenAI","published_at":"2026-05-14","summary":"Summary","why_it_matters":"Useful","confidence":0.8}]}'
                            }
                        ]
                    },
                    "groundingMetadata": {"groundingChunks": []},
                }
            ]
        }
        provider = GeminiGroundedSearchProvider(api_key="test")
        candidates = provider._candidates_from_response(response, query="test")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_name, "OpenAI")
        self.assertEqual(candidates[0].url, "https://openai.com/news/example")

    def test_trending_scout_requests_momentum_evidence_and_article_urls(self):
        provider = GeminiGroundedSearchProvider(api_key="test")
        calls = {}

        def fake_candidates(prompt, *, query, limit):
            calls["prompt"] = prompt
            calls["query"] = query
            calls["limit"] = limit
            return []

        provider._generate_candidates = fake_candidates
        provider.scout_today_ai_news(limit=12)

        self.assertIn("trend_score", calls["prompt"])
        self.assertIn("duas", calls["prompt"])
        self.assertIn("Nunca devolvas", calls["prompt"])
        self.assertIn("data de hoje", calls["prompt"])
        self.assertIn("dia anterior", calls["prompt"])
        self.assertEqual(calls["query"], "gemini-trending-ai-news")
        self.assertEqual(calls["limit"], 12)

    def test_candidate_extracts_trend_fields(self):
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"candidates":[{"title":"AI news",'
                                    '"source_url":"https://openai.com/news/example",'
                                    '"source_name":"OpenAI","published_at":"2026-06-15",'
                                    '"summary":"Summary","why_it_matters":"Useful",'
                                    '"trend_score":87,"trend_evidence":"Multiple sources",'
                                    '"confidence":0.9}]}'
                                )
                            }
                        ]
                    },
                    "groundingMetadata": {"groundingChunks": []},
                }
            ]
        }
        provider = GeminiGroundedSearchProvider(api_key="test")

        candidate = provider._candidates_from_response(response, query="test")[0]

        self.assertEqual(candidate.trend_score, 87)
        self.assertEqual(candidate.trend_evidence, "Multiple sources")

    def test_uses_grounding_chunks_as_fallback_candidates(self):
        response = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "no json here"}]},
                    "groundingMetadata": {
                        "groundingChunks": [
                            {"web": {"uri": "https://www.reuters.com/technology/ai/story", "title": "Reuters"}}
                        ]
                    },
                }
            ]
        }
        provider = GeminiGroundedSearchProvider(api_key="test")
        candidates = provider._candidates_from_response(response, query="test")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_name, "Reuters")
        self.assertEqual(candidates[0].url, "https://www.reuters.com/technology/ai/story")

    def test_extracts_rewrite_result(self):
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"title":"Novo titulo","body":"Novo texto","hashtags":"#IA","rationale":"Mais concreto"}'
                            }
                        ]
                    }
                }
            ]
        }
        provider = GeminiGroundedSearchProvider(api_key="test")
        result = provider._generate_rewrite_from_response(response)

        self.assertEqual(result.title, "Novo titulo")
        self.assertEqual(result.body, "Novo texto")
        self.assertEqual(result.hashtags, "#IA")

    def test_polish_uses_low_temperature_rewrite(self):
        provider = GeminiGroundedSearchProvider(api_key="test")
        calls = {}

        def fake_rewrite(prompt, *, temperature=0.55):
            calls["prompt"] = prompt
            calls["temperature"] = temperature
            return provider._generate_rewrite_from_response(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": '{"title":"Titulo PT","body":"Texto em portugues europeu","hashtags":"#IA","rationale":"Mais PT-PT"}'
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        provider._generate_rewrite = fake_rewrite
        result = provider.polish_final_post(
            channel="linkedin",
            title="Titulo",
            body="Texto",
            hashtags="#IA",
            source_urls=["https://example.com"],
        )

        self.assertEqual(calls["temperature"], 0.7)
        self.assertIn("editor final PT-PT", calls["prompt"])
        self.assertIn("Não imprimas headings", calls["prompt"])
        self.assertIn("Exemplos PTIA de tom", calls["prompt"])
        self.assertIn("Passagem anti-assistente", calls["prompt"])
        self.assertIn("Senior Tech Journalist", calls["prompt"])
        self.assertIn("Absolute Humanization", calls["prompt"])
        self.assertIn("Disciplina de angulo especifico", calls["prompt"])
        self.assertIn("Se a tese pudesse servir para dez outras noticias de IA", calls["prompt"])
        self.assertIn("Regra reforcada para o canal site", calls["prompt"])
        self.assertIn("artigo editorial curado", calls["prompt"])
        self.assertEqual(result.title, "Titulo PT")

    def test_rewrite_uses_human_editorial_article_prompt(self):
        provider = GeminiGroundedSearchProvider(api_key="test")
        calls = {}

        def fake_rewrite(prompt, *, temperature=0.55):
            calls["prompt"] = prompt
            calls["temperature"] = temperature
            return provider._generate_rewrite_from_response(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": '{"title":"Titulo humano","body":"Texto editorial","hashtags":"","rationale":"Menos AI"}'
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        provider._generate_rewrite = fake_rewrite
        result = provider.rewrite_final_post(
            channel="site",
            title="Titulo",
            body="Texto",
            hashtags="",
            source_urls=["https://example.com"],
            feedback="menos AI",
        )

        self.assertEqual(calls["temperature"], 0.72)
        self.assertIn("Senior Tech Journalist", calls["prompt"])
        self.assertIn("Strict AI Cliche Filter", calls["prompt"])
        self.assertIn("Disciplina de angulo especifico", calls["prompt"])
        self.assertIn("Lead: start in media res", calls["prompt"])
        self.assertIn("artigo editorial curado", calls["prompt"])
        self.assertEqual(result.title, "Titulo humano")

    def test_visual_image_title_suggestions_keep_both_tones(self):
        provider = GeminiGroundedSearchProvider(api_key="test")

        def fake_json_response(prompt, *, temperature):
            self.assertIn("Instagram e X", prompt)
            self.assertEqual(temperature, 0.78)
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"suggestions":[{"tone":"provocatorio",'
                                        '"title":"A automacao ja escolhe por ti?"},'
                                        '{"tone":"editorial","title":"Quando a IA entra na decisao"}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

        provider._generate_json_response = fake_json_response
        suggestions = provider.suggest_visual_image_titles(
            title="AI decisions",
            body="Texto PTIA",
            source_urls=["https://example.com"],
        )

        self.assertEqual([item["tone"] for item in suggestions], ["provocatorio", "editorial"])
        self.assertEqual(suggestions[0]["title"], "A automacao ja escolhe por ti?")


if __name__ == "__main__":
    unittest.main()
