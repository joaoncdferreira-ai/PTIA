from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.dashboard import HTML
from ptia_engine.knowledge_automation import (
    knowledge_review_snapshot,
    run_knowledge_automation,
    update_review_status,
)


class FakeProvider:
    available = True

    def __init__(self, proposals):
        self.proposals = proposals

    def grounded_json(self, prompt: str, *, temperature: float = 0.1):
        self.prompt = prompt
        return {"proposals": self.proposals}


class MissingProvider:
    available = False


class FailingProvider:
    available = True

    def grounded_json(self, prompt: str, *, temperature: float = 0.1):
        raise RuntimeError("temporary API failure")


class KnowledgeAutomationTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path.cwd()
        self.root = self.repo / ".test_tmp" / uuid.uuid4().hex
        (self.root / "config").mkdir(parents=True)
        (self.root / "site" / "assets").mkdir(parents=True)
        (self.root / "data").mkdir(parents=True)
        shutil.copy2(
            self.repo / "config" / "ptia_knowledge.json",
            self.root / "config" / "ptia_knowledge.json",
        )
        shutil.copy2(
            self.repo / "site" / "assets" / "quem-e-quem.json",
            self.root / "site" / "assets" / "quem-e-quem.json",
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _coding_ranking(self):
        catalog = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        return catalog["tool_category_evidence"]["coding"]["components"]["capability"]["ranking"]

    def test_high_confidence_small_change_is_applied(self):
        ranking = self._coding_ranking()
        proposed = ranking.copy()
        proposed[0], proposed[1] = proposed[1], proposed[0]
        run = run_knowledge_automation(
            self.root,
            provider=FakeProvider([
                {
                    "kind": "tool_component_order",
                    "target": "coding",
                    "confidence": 0.97,
                    "reason": "Dois benchmarks recentes colocam o segundo candidato à frente.",
                    "sources": [
                        {"label": "Benchmark A", "url": "https://example.org/a"},
                        {"label": "Benchmark B", "url": "https://example.net/b"},
                    ],
                    "payload": {
                        "component": "capability",
                        "ranking": proposed,
                        "label": "Benchmarks combinados",
                        "url": "https://example.org/a",
                    },
                }
            ]),
        )

        self.assertEqual(run["auto_applied"], 1)
        self.assertEqual(self._coding_ranking(), proposed)
        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["applied"], 1)

    def test_large_change_is_held_for_review(self):
        ranking = self._coding_ranking()
        proposed = ranking.copy()
        proposed.insert(0, proposed.pop())
        run_knowledge_automation(
            self.root,
            provider=FakeProvider([
                {
                    "kind": "tool_component_order",
                    "target": "coding",
                    "confidence": 0.99,
                    "reason": "Mudança invulgar.",
                    "sources": [
                        {"label": "A", "url": "https://example.org/a"},
                        {"label": "B", "url": "https://example.net/b"},
                    ],
                    "payload": {
                        "component": "capability",
                        "ranking": proposed,
                        "label": "Teste",
                        "url": "https://example.org/a",
                    },
                }
            ]),
        )

        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["pending"], 1)
        self.assertIn("movimento superior", snapshot["reviews"][0]["issues"][0])
        self.assertEqual(self._coding_ranking(), ranking)

    def test_missing_provider_creates_dashboard_alert(self):
        run = run_knowledge_automation(self.root, provider=MissingProvider())
        self.assertEqual(run["status"], "attention")
        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["pending"], 1)
        review = snapshot["reviews"][0]
        self.assertEqual(review["target"], "external_discovery")

        updated = update_review_status(
            self.root,
            proposal_id=review["proposal_id"],
            status="rejected",
            notes="Credencial será configurada.",
        )
        self.assertEqual(updated["status"], "rejected")

    def test_provider_failure_does_not_block_weekly_run(self):
        run = run_knowledge_automation(self.root, provider=FailingProvider())
        self.assertEqual(run["status"], "attention")
        self.assertIn("temporary API failure", run["provider_error"])
        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["pending"], 1)

    def test_dashboard_exposes_resources_management_tab(self):
        self.assertIn('data-tab="knowledge_tab"', HTML)
        self.assertIn('id="knowledge_tab"', HTML)
        self.assertIn("/api/knowledge-review", HTML)
        self.assertIn("Automação de Recursos", HTML)


if __name__ == "__main__":
    unittest.main()
