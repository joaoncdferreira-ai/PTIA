import copy
import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ptia_engine.knowledge import (
    KnowledgeValidationError,
    build_knowledge_payload,
    build_knowledge_site,
    load_article_signals,
    validate_catalog,
)


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path.cwd()
        self.root = self.repo / ".test_tmp" / uuid.uuid4().hex
        (self.root / "config").mkdir(parents=True)
        (self.root / "site" / "assets").mkdir(parents=True)
        shutil.copy2(self.repo / "config" / "ptia_knowledge.json", self.root / "config")
        shutil.copy2(
            self.repo / "site" / "assets" / "quem-e-quem.json",
            self.root / "site" / "assets",
        )
        self.now = datetime(2026, 6, 7, 12, tzinfo=timezone.utc)
        feed = {
            "posts": [
                {
                    "id": "one",
                    "title": "Defined.ai e Unbabel reforçam IA em Portugal",
                    "body": "Claude Code, Codex e RAG estão no centro da adoção.\n\nFonte: https://observador.pt/openai",
                    "published_at": "2026-06-06T12:00:00+00:00",
                    "article_url": "artigos/teste",
                },
                {
                    "id": "future",
                    "title": "Artigo futuro",
                    "body": "Não deve contar.",
                    "published_at": "2026-06-08T12:00:00+00:00",
                    "article_url": "artigos/futuro",
                },
            ]
        }
        (self.root / "site" / "site-feed.json").write_text(
            json.dumps(feed, ensure_ascii=False),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_builds_all_pages_and_versioned_payload(self):
        payload = build_knowledge_site(root=self.root, now=self.now)

        self.assertEqual(payload["edition"], "2026-W23")
        self.assertEqual(payload["signal_articles"], 1)
        self.assertEqual(len(payload["prompts"]), 25)
        self.assertGreaterEqual(len(payload["glossary"]), 35)
        for path in (
            "recursos/index.html",
            "ia-em-portugal/index.html",
            "ferramentas/index.html",
            "prompts/index.html",
            "glossario/index.html",
            "metodologia-indice/index.html",
            "assets/ptia-index/latest.json",
            "assets/ptia-index/archive/2026-W23.json",
        ):
            self.assertTrue((self.root / "site" / path).exists(), path)
        glossary = (self.root / "site" / "glossario" / "index.html").read_text(encoding="utf-8")
        self.assertIn("DefinedTermSet", glossary)
        self.assertIn("Machine learning", glossary)
        self.assertIn("Artificial General Intelligence", glossary)
        self.assertIn("Retrieval-Augmented Generation", glossary)
        self.assertIn('"alternateName": "AI agent"', glossary)
        self.assertIn("Inteligência Artificial, sem nevoeiro.", glossary)
        resources = (self.root / "site" / "recursos" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Quem está a construir a IA em Portugal", resources)
        self.assertIn("A melhor por finalidade", resources)
        self.assertIn("Quem e o que lidera a IA esta semana.", resources)
        self.assertIn('class="weekly-leaders"', resources)
        self.assertIn('weekly-leader-label">Empresa</span>', resources)
        self.assertIn('weekly-leader-label">Pessoa</span>', resources)
        self.assertIn('weekly-leader-label">Ferramenta</span>', resources)
        self.assertIn('weekly-leader-label">Prompt</span>', resources)
        self.assertIn('href="/recursos/">Hub</a>', resources)
        self.assertEqual(resources.count("<li>"), 24)
        self.assertIn("<small>PTIA</small>", resources)
        self.assertIn('class="lobby-entity-list"', resources)
        self.assertNotIn(">Manteve<", resources)
        portugal = (self.root / "site" / "ia-em-portugal" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-index-tab="companies"', portugal)
        self.assertIn('data-index-panel="people"', portugal)
        self.assertIn("PTIA Score", portugal)
        self.assertNotIn(">Manteve<", portugal)
        prompts = (self.root / "site" / "prompts" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Top 10 prompts PTIA", prompts)
        self.assertIn("data-prompt-search-input", prompts)
        self.assertIn('data-prompt-category="imagem"', prompts)
        self.assertIn("data-prompt-suggestion-form", prompts)
        self.assertGreater(
            prompts.index("data-prompt-suggestion-form"),
            prompts.index('class="prompt-grid"'),
        )
        self.assertNotIn("· Manteve", prompts)

        repeated = build_knowledge_site(root=self.root, now=self.now)
        self.assertTrue(all(item["movement"] is None for item in repeated["companies"]))
        self.assertTrue(all(item["movement"] is None for item in repeated["people"]))

    def test_future_articles_do_not_affect_signals(self):
        signals = load_article_signals(self.root / "site" / "site-feed.json", now=self.now)
        self.assertEqual([signal.title for signal in signals], ["Defined.ai e Unbabel reforçam IA em Portugal"])

    def test_rankings_are_stable_and_include_evidence(self):
        catalog = json.loads((self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8"))
        directory = json.loads(
            (self.root / "site" / "assets" / "quem-e-quem.json").read_text(encoding="utf-8")
        )
        validate_catalog(catalog, directory)
        signals = load_article_signals(self.root / "site" / "site-feed.json", now=self.now)
        payload = build_knowledge_payload(
            catalog=catalog,
            directory=directory,
            signals=signals,
            now=self.now,
        )
        defined = next(item for item in payload["companies"] if item["id"] == "definedai")
        observador = next(item for item in payload["companies"] if item["id"] == "observador-pt")
        codex = next(item for item in payload["tools"] if item["id"] == "codex")
        self.assertTrue(defined["evidence"])
        self.assertFalse(observador["evidence"])
        self.assertTrue(codex["evidence"])
        self.assertEqual(sorted(item["rank"] for item in payload["prompts"]), list(range(1, 26)))
        agent = next(item for item in payload["glossary"] if item["id"] == "agente-ia")
        self.assertEqual(agent["english_term"], "AI agent")

        winners = {}
        for category in catalog["tool_category_evidence"]:
            eligible = [
                item for item in payload["tools"] if category in item["category_ranks"]
            ]
            winners[category] = min(
                eligible,
                key=lambda item: item["category_ranks"][category],
            )["id"]
        self.assertEqual(winners["coding"], "claude-opus-4-8")
        self.assertEqual(winners["estudo"], "notebooklm")
        self.assertEqual(winners["video"], "higgsfield")
        self.assertEqual(winners["design"], "figma-ai")
        self.assertEqual(winners["imagem"], "chatgpt")
        self.assertEqual(winners["produtividade"], "chatgpt")
        self.assertEqual(winners["marketing"], "canva")
        self.assertEqual(winners["automacoes"], "n8n")

    def test_weekly_movements_cover_entered_up_down_and_category_changes(self):
        catalog = json.loads((self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8"))
        directory = json.loads(
            (self.root / "site" / "assets" / "quem-e-quem.json").read_text(encoding="utf-8")
        )
        signals = load_article_signals(self.root / "site" / "site-feed.json", now=self.now)
        baseline = build_knowledge_payload(
            catalog=catalog,
            directory=directory,
            signals=signals,
            now=self.now,
        )
        previous = copy.deepcopy(baseline)
        previous["prompts"][0]["rank"] = baseline["prompts"][0]["rank"] + 2
        previous["prompts"] = [
            item for item in previous["prompts"] if item["id"] != baseline["prompts"][1]["id"]
        ]
        previous["prompts"][1]["rank"] = max(1, baseline["prompts"][2]["rank"] - 2)
        coding_winner = min(
            (tool for tool in baseline["tools"] if "coding" in tool["category_ranks"]),
            key=lambda tool: tool["category_ranks"]["coding"],
        )
        previous_coding_winner = next(
            tool for tool in previous["tools"] if tool["id"] == coding_winner["id"]
        )
        previous_coding_winner["category_ranks"]["coding"] = 3

        changed = build_knowledge_payload(
            catalog=catalog,
            directory=directory,
            signals=signals,
            previous=previous,
            now=self.now,
        )
        self.assertEqual(changed["prompts"][0]["ranking_change"]["label"], "Subiu 2")
        self.assertEqual(changed["prompts"][1]["ranking_change"]["label"], "Entrou no Top")
        self.assertEqual(changed["prompts"][2]["ranking_change"]["label"], "Desceu 2")
        changed_winner = next(
            tool for tool in changed["tools"] if tool["id"] == coding_winner["id"]
        )
        self.assertEqual(
            changed_winner["category_movements"]["coding"]["label"],
            "Subiu 2",
        )

    def test_validation_blocks_incomplete_catalog_before_writes(self):
        catalog = json.loads((self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8"))
        directory = json.loads(
            (self.root / "site" / "assets" / "quem-e-quem.json").read_text(encoding="utf-8")
        )
        catalog["prompts"] = catalog["prompts"][:2]
        with self.assertRaises(KnowledgeValidationError):
            validate_catalog(catalog, directory)


if __name__ == "__main__":
    unittest.main()
