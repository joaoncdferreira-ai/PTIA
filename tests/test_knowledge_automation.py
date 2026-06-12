from __future__ import annotations

import json
import shutil
import unittest
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ptia_engine.dashboard import HTML
from ptia_engine.knowledge_automation import (
    apply_approved_reviews,
    knowledge_review_snapshot,
    proposal_issues,
    run_knowledge_automation,
    update_review_status,
)
from ptia_engine.knowledge_remote import (
    dispatch_knowledge_workflow,
    read_remote_text,
    sync_knowledge_state,
)


class FakeProvider:
    available = True

    def __init__(self, proposals):
        self.proposals = proposals

    def grounded_json(self, prompt: str, *, temperature: float = 0.1):
        self.prompt = prompt
        grounding_sources = []
        seen = set()
        for proposal in self.proposals:
            for source in proposal.get("sources") or []:
                if source["url"] in seen:
                    continue
                grounding_sources.append(source)
                seen.add(source["url"])
        return {
            "proposals": self.proposals,
            "_grounding_sources": grounding_sources,
        }


class MissingProvider:
    available = False


class FailingProvider:
    available = True

    def grounded_json(self, prompt: str, *, temperature: float = 0.1):
        raise RuntimeError("temporary API failure")


class PartitionedProvider:
    available = True
    partitioned_research = True

    def __init__(self):
        self.research_prompts = []
        self.structured_prompts = []

    def grounded_research(self, prompt: str, *, temperature: float = 0.1):
        self.research_prompts.append(prompt)
        return {
            "text": "Não foi encontrada alteração material.",
            "sources": [],
        }

    def structured_json(self, prompt: str, *, temperature: float = 0.0):
        self.structured_prompts.append(prompt)
        return {"proposals": []}


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
                        {
                            "label": "Benchmark A",
                            "url": "https://vellum.ai/a",
                            "evidence": "O benchmark coloca este modelo em primeiro lugar.",
                        },
                        {
                            "label": "Benchmark B",
                            "url": "https://github.com/b",
                            "evidence": "O segundo benchmark confirma a mesma ordenação.",
                        },
                    ],
                    "payload": {
                        "component": "capability",
                        "ranking": proposed,
                        "label": "Benchmarks combinados",
                        "url": "https://vellum.ai/a",
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
                        {
                            "label": "A",
                            "url": "https://vellum.ai/a",
                            "evidence": "A fonte propõe uma alteração extensa no ranking.",
                        },
                        {
                            "label": "B",
                            "url": "https://github.com/b",
                            "evidence": "A segunda fonte confirma a alteração extensa.",
                        },
                    ],
                    "payload": {
                        "component": "capability",
                        "ranking": proposed,
                        "label": "Teste",
                        "url": "https://vellum.ai/a",
                    },
                }
            ]),
        )

        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["pending"], 1)
        self.assertIn("movimento superior", snapshot["reviews"][0]["issues"][0])
        self.assertEqual(self._coding_ranking(), ranking)

    def test_invalid_risky_proposal_is_held_without_blocking_run(self):
        original = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        tool = deepcopy(
            next(item for item in original["tools"] if item["id"] == "claude-opus-4-8")
        )
        tool["categories"] = ["coding"]
        tool["category_positions"] = {
            "coding": {"capability": 1, "popularity": 1, "task_fit": 1, "access": 1}
        }
        run = run_knowledge_automation(
            self.root,
            provider=FakeProvider([
                {
                    "kind": "tool_upsert",
                    "target": "coding",
                    "confidence": 0.99,
                    "reason": "Alteração que invalida a presença noutra categoria.",
                    "sources": [
                        {
                            "label": "A",
                            "url": "https://vellum.ai/a",
                            "evidence": "A fonte descreve a ferramenta apenas para coding.",
                        },
                        {
                            "label": "B",
                            "url": "https://github.com/b",
                            "evidence": "A segunda fonte repete a classificação para coding.",
                        },
                    ],
                    "payload": tool,
                }
            ]),
        )

        updated = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["auto_applied"], 0)
        self.assertEqual(updated, original)
        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["pending"], 1)

    def test_invalid_approved_proposal_is_rolled_back(self):
        original = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        tool = deepcopy(
            next(item for item in original["tools"] if item["id"] == "claude-opus-4-8")
        )
        tool["categories"] = ["coding"]
        tool["category_positions"] = {
            "coding": {"capability": 1, "popularity": 1, "task_fit": 1, "access": 1}
        }
        record = {
            "proposal_id": "knowledge_invalid_approved",
            "kind": "tool_upsert",
            "target": "coding",
            "confidence": 0.99,
            "reason": "Alteração aprovada que invalida outra categoria.",
            "sources": [
                {
                    "label": "A",
                    "url": "https://vellum.ai/a",
                    "evidence": "A fonte descreve a ferramenta apenas para coding.",
                },
                {
                    "label": "B",
                    "url": "https://github.com/b",
                    "evidence": "A segunda fonte repete a classificação para coding.",
                },
            ],
            "payload": tool,
            "status": "approved",
            "notes": "",
        }
        (self.root / "data" / "knowledge_review.jsonl").write_text(
            json.dumps(record, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        result = apply_approved_reviews(self.root)

        updated = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result, {"applied": 0, "failed": 1})
        self.assertEqual(updated, original)
        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["failed"], 1)

    def test_new_records_always_require_editorial_approval(self):
        catalog = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        prompt = deepcopy(catalog["prompts"][0])
        prompt["id"] = "novo-prompt-seguro"
        prompt["title"] = "Novo prompt seguro"
        run = run_knowledge_automation(
            self.root,
            provider=FakeProvider([
                {
                    "kind": "prompt_upsert",
                    "target": "produtividade",
                    "confidence": 0.99,
                    "reason": "Duas fontes sugerem este padrão de utilização.",
                    "sources": [
                        {
                            "label": "A",
                            "url": "https://vellum.ai/a",
                            "evidence": "A fonte demonstra o padrão num contexto profissional.",
                        },
                        {
                            "label": "B",
                            "url": "https://github.com/b",
                            "evidence": "A fonte independente apresenta o mesmo padrão.",
                        },
                    ],
                    "payload": prompt,
                }
            ]),
        )

        self.assertEqual(run["auto_applied"], 0)
        self.assertEqual(run["pending"], 1)
        self.assertNotIn(
            "novo-prompt-seguro",
            [item["id"] for item in json.loads(
                (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
            )["prompts"]],
        )

    def test_weekly_task_is_capped_to_three_proposals(self):
        catalog = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        proposals = []
        for index in range(5):
            prompt = deepcopy(catalog["prompts"][0])
            prompt["id"] = f"candidate-{index}"
            prompt["title"] = f"Candidate {index}"
            proposals.append(
                {
                    "kind": "prompt_upsert",
                    "target": "produtividade",
                    "confidence": 0.90 + index / 100,
                    "reason": f"Candidato material número {index}.",
                    "sources": [
                        {
                            "label": "Vellum",
                            "url": "https://vellum.ai/a",
                            "evidence": "A fonte demonstra um padrão de utilização concreto.",
                        },
                        {
                            "label": "GitHub",
                            "url": "https://github.com/b",
                            "evidence": "A segunda fonte documenta o mesmo padrão.",
                        },
                    ],
                    "payload": prompt,
                }
            )

        run = run_knowledge_automation(self.root, provider=FakeProvider(proposals))

        self.assertEqual(run["proposals"], 3)
        self.assertEqual(knowledge_review_snapshot(self.root)["counts"]["pending"], 3)

    def test_ungrounded_sources_cannot_be_auto_applied(self):
        ranking = self._coding_ranking()
        proposed = ranking.copy()
        proposed[0], proposed[1] = proposed[1], proposed[0]
        provider = FakeProvider([
            {
                "kind": "tool_component_order",
                "target": "coding",
                "confidence": 0.99,
                "reason": "Ranking alegadamente suportado.",
                "sources": [
                    {
                        "label": "A",
                        "url": "https://vellum.ai/a",
                        "evidence": "A fonte coloca o segundo candidato à frente.",
                    },
                    {
                        "label": "B",
                        "url": "https://github.com/b",
                        "evidence": "A segunda fonte confirma a mesma posição.",
                    },
                ],
                "payload": {
                    "component": "capability",
                    "ranking": proposed,
                    "label": "Teste",
                    "url": "https://vellum.ai/a",
                },
            }
        ])
        provider.grounded_json = lambda prompt, temperature=0.1: {
            "proposals": provider.proposals,
            "_grounding_sources": [
                {"label": "Outra", "url": "https://unrelated.example.com/result"}
            ],
        }
        run_knowledge_automation(self.root, provider=provider)

        snapshot = knowledge_review_snapshot(self.root)
        self.assertTrue(
            any(
                "não confirmadas pelo grounding" in issue
                for issue in snapshot["reviews"][0]["issues"]
            )
        )
        self.assertEqual(self._coding_ranking(), ranking)

    def test_rejected_proposal_is_not_applied_on_later_run(self):
        ranking = self._coding_ranking()
        proposed = ranking.copy()
        proposed[0], proposed[1] = proposed[1], proposed[0]
        proposal = {
            "kind": "tool_component_order",
            "target": "coding",
            "confidence": 0.99,
            "reason": "Dois benchmarks propõem esta alteração.",
            "sources": [
                {
                    "label": "A",
                    "url": "https://vellum.ai/a",
                    "evidence": "A fonte coloca o segundo candidato à frente.",
                },
                {
                    "label": "B",
                    "url": "https://github.com/b",
                    "evidence": "A segunda fonte confirma a mesma posição.",
                },
            ],
            "payload": {
                "component": "capability",
                "ranking": proposed,
                "label": "Teste",
                "url": "https://vellum.ai/a",
            },
        }
        initial = deepcopy(proposal)
        initial["confidence"] = 0.80
        run_knowledge_automation(self.root, provider=FakeProvider([initial]))
        review = knowledge_review_snapshot(self.root)["reviews"][0]
        update_review_status(
            self.root,
            proposal_id=review["proposal_id"],
            status="rejected",
            notes="Rejeitado editorialmente.",
        )

        run = run_knowledge_automation(self.root, provider=FakeProvider([proposal]))

        self.assertEqual(run["auto_applied"], 0)
        self.assertEqual(self._coding_ranking(), ranking)
        snapshot = knowledge_review_snapshot(self.root)
        self.assertEqual(snapshot["counts"]["rejected"], 1)

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

    def test_partitioned_research_receives_current_catalog_context(self):
        provider = PartitionedProvider()

        run = run_knowledge_automation(self.root, provider=provider)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["proposals"], 0)
        self.assertEqual(len(provider.research_prompts), 4)
        self.assertTrue(any("Feedzai" in prompt for prompt in provider.research_prompts))
        self.assertTrue(any("Claude Opus 4.8" in prompt for prompt in provider.research_prompts))
        self.assertTrue(
            any("Transformar informação" in prompt for prompt in provider.research_prompts)
        )
        self.assertTrue(any("Contexto atual" in prompt for prompt in provider.research_prompts))
        current_date = datetime.now(timezone.utc).date().isoformat()
        self.assertTrue(
            all(f"Data atual: {current_date}" in prompt for prompt in provider.research_prompts)
        )
        self.assertTrue(
            all(f"Data atual: {current_date}" in prompt for prompt in provider.structured_prompts)
        )

    def test_stale_future_claim_is_flagged(self):
        catalog = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        directory = json.loads(
            (self.root / "site" / "assets" / "quem-e-quem.json").read_text(
                encoding="utf-8"
            )
        )
        proposal = {
            "kind": "entity_upsert",
            "target": "companies",
            "confidence": 0.95,
            "reason": "A organização anunciou que em 2025 terá um novo programa.",
            "sources": [
                {
                    "label": "Fonte A",
                    "url": "https://example.com/a",
                    "evidence": "A agenda publicada descreve o programa previsto para 2025.",
                },
                {
                    "label": "Fonte B",
                    "url": "https://example.org/b",
                    "evidence": "A segunda fonte confirma que o evento será realizado em 2025.",
                },
            ],
            "payload": {},
        }

        issues = proposal_issues(proposal, catalog, directory)

        self.assertIn("alegação futura baseada num ano já passado", issues)

    def test_near_duplicate_glossary_term_is_flagged(self):
        catalog = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        directory = json.loads(
            (self.root / "site" / "assets" / "quem-e-quem.json").read_text(
                encoding="utf-8"
            )
        )
        proposal = {
            "kind": "glossary_upsert",
            "target": "agentes-autonomos-ia",
            "confidence": 0.95,
            "reason": "Expressão recente para sistemas que executam tarefas autonomamente.",
            "sources": [
                {
                    "label": "Fonte A",
                    "url": "https://example.com/a",
                    "evidence": "A fonte descreve agentes autónomos de inteligência artificial.",
                },
                {
                    "label": "Fonte B",
                    "url": "https://example.org/b",
                    "evidence": "A segunda fonte usa o termo para o mesmo conceito.",
                },
            ],
            "payload": {
                "id": "agentes-autonomos-ia",
                "term": "Agentes Autónomos de IA",
                "definition": (
                    "Sistemas de inteligência artificial que planeiam e executam "
                    "tarefas com autonomia."
                ),
                "example": (
                    "Um agente pesquisa, compara opções e entrega uma recomendação."
                ),
                "related": ["agente-ia"],
                "aliases": ["agentes de ia"],
            },
        }

        issues = proposal_issues(proposal, catalog, directory)

        self.assertIn("possível duplicado de termo existente", issues)

    def test_tool_redirect_url_is_flagged(self):
        catalog = json.loads(
            (self.root / "config" / "ptia_knowledge.json").read_text(encoding="utf-8")
        )
        directory = json.loads(
            (self.root / "site" / "assets" / "quem-e-quem.json").read_text(
                encoding="utf-8"
            )
        )
        proposal = {
            "kind": "tool_upsert",
            "target": "example-tool",
            "confidence": 0.95,
            "reason": "Nova ferramenta relevante para pesquisa.",
            "sources": [
                {
                    "label": "Fonte A",
                    "url": "https://example.com/a",
                    "evidence": "A fonte apresenta resultados recentes da ferramenta.",
                },
                {
                    "label": "Fonte B",
                    "url": "https://example.org/b",
                    "evidence": "A segunda fonte documenta a utilização do produto.",
                },
            ],
            "payload": {
                "id": "example-tool",
                "name": "Example Tool",
                "url": (
                    "https://vertexaisearch.cloud.google.com/"
                    "grounding-api-redirect/example"
                ),
                "categories": ["pesquisa"],
                "description": (
                    "Ferramenta de pesquisa assistida por inteligência artificial."
                ),
                "best_for": "Pesquisa documental.",
                "watch_out": "Confirmar fontes.",
                "baseline_score": 80,
                "aliases": [],
                "sources": [],
                "category_positions": {
                    "pesquisa": {
                        "capability": 1,
                        "popularity": 1,
                        "task_fit": 1,
                        "access": 1,
                    }
                },
            },
        }

        issues = proposal_issues(proposal, catalog, directory)

        self.assertIn("ferramenta sem URL direta do produto", issues)

    def test_dashboard_exposes_resources_management_tab(self):
        self.assertIn('data-tab="knowledge_tab"', HTML)
        self.assertIn('id="knowledge_tab"', HTML)
        self.assertIn("/api/knowledge-review", HTML)
        self.assertIn("/api/knowledge-sync", HTML)
        self.assertIn("Automação de Recursos", HTML)

    @patch("ptia_engine.knowledge_remote._request")
    def test_remote_state_sync_writes_canonical_files(self, request):
        content = '{"proposal_id":"remote","status":"pending"}\n'
        encoded = __import__("base64").b64encode(content.encode()).decode()
        request.side_effect = [
            (200, {"content": encoded, "sha": "review-sha"}),
            (404, {}),
        ]

        result = sync_knowledge_state(self.root)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            (self.root / "data" / "knowledge_review.jsonl").read_text(encoding="utf-8"),
            content,
        )

    @patch("ptia_engine.knowledge_remote._request")
    def test_workflow_dispatch_targets_main(self, request):
        request.return_value = (204, {})

        result = dispatch_knowledge_workflow()

        self.assertEqual(result["status"], "dispatched")
        _, kwargs = request.call_args
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["payload"], {"ref": "main"})

    @patch("ptia_engine.knowledge_remote._request")
    def test_remote_text_reader_decodes_github_content(self, request):
        content = '{"status":"completed"}\n'
        encoded = __import__("base64").b64encode(content.encode()).decode()
        request.return_value = (200, {"content": encoded, "sha": "abc"})

        text, sha = read_remote_text("data/knowledge_runs.jsonl")

        self.assertEqual(text, content)
        self.assertEqual(sha, "abc")


if __name__ == "__main__":
    unittest.main()
