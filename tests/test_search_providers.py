import unittest

from ptia_engine.search_providers import GeminiGroundedSearchProvider


class SearchProvidersTests(unittest.TestCase):
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
        self.assertEqual(result.title, "Titulo PT")


if __name__ == "__main__":
    unittest.main()
