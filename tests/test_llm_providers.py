import os
import unittest
from unittest.mock import patch

from ptia_engine.llm_providers import (
    default_model_for_provider,
    estimate_provider_cost_usd,
    normalize_provider,
    parse_json_text,
)


class LLMProviderTests(unittest.TestCase):
    def test_normalize_provider_accepts_local_alias(self):
        self.assertEqual(normalize_provider("local"), "ollama")
        self.assertEqual(normalize_provider("template"), "template")

    def test_parse_json_text_strips_markdown_fences(self):
        self.assertEqual(parse_json_text("```json\n{\"ok\": true}\n```"), {"ok": True})

    def test_non_openai_providers_have_zero_estimated_api_cost(self):
        self.assertEqual(estimate_provider_cost_usd("gemini", "gemini-test", 1000, 1000), 0.0)
        self.assertEqual(estimate_provider_cost_usd("ollama", "llama-test", 1000, 1000), 0.0)

    def test_default_model_can_be_overridden_by_env(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-custom"}):
            self.assertEqual(default_model_for_provider("gemini"), "gemini-custom")


if __name__ == "__main__":
    unittest.main()
