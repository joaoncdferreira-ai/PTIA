from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ptia_engine.knowledge import validate_catalog
from ptia_engine.search_providers import GeminiGroundedSearchProvider


AUTO_CONFIDENCE = 0.92
AUTO_APPLY_KINDS = {"tool_component_order", "entity_baseline_order"}
REVIEW_STATUSES = {"pending", "approved", "rejected", "applied", "failed"}
TRUSTED_SOURCE_SUFFIXES = (
    "a16z.com",
    "arxiv.org",
    "artificialanalysis.ai",
    "bloomberg.com",
    "europa.eu",
    "ft.com",
    "github.com",
    "gov.pt",
    "huggingface.co",
    "lmarena.ai",
    "reuters.com",
    "similarweb.com",
    "swebench.com",
    "vellum.ai",
)
DISCOVERY_TASKS = (
    (
        "entities",
        "Analisa apenas pessoas e empresas com impacto verificável em IA em Portugal. "
        "Usa apenas entity_baseline_order ou entity_upsert.",
    ),
    (
        "tools",
        "Analisa apenas ferramentas e os rankings por finalidade. "
        "Usa apenas tool_component_order ou tool_upsert.",
    ),
    (
        "prompts",
        "Analisa apenas prompts úteis, concretos e reutilizáveis. "
        "Usa apenas prompt_upsert.",
    ),
    (
        "glossary",
        "Analisa apenas termos técnicos em falta ou materialmente desatualizados. "
        "Usa apenas glossary_upsert.",
    ),
)
TASK_KINDS = {
    "entities": {"entity_baseline_order", "entity_upsert"},
    "tools": {"tool_component_order", "tool_upsert"},
    "prompts": {"prompt_upsert"},
    "glossary": {"glossary_upsert"},
}
RESEARCH_PROMPT = """
És investigador do índice PTIA. Pesquisa a web atual sobre o foco indicado.
Devolve um relatório factual curto, com no máximo 12 constatações materiais.
Cada constatação deve ser sustentada pelas fontes citadas pelo Google Search.
Não inventes rankings, métricas, datas, pessoas, empresas ou produtos.
Se não houver alteração material e recente, diz explicitamente que não há.
""".strip()

DISCOVERY_PROMPT = """
És o investigador semanal do índice PTIA. Pesquisa a web atual e propõe apenas
alterações suportadas por evidência pública recente.

Analisa:
1. pessoas e empresas com impacto verificável em IA em Portugal;
2. ferramentas por coding, estudo, pesquisa, produtividade, design, vídeo, imagem,
   marketing e automações;
3. prompts úteis e reutilizáveis;
4. termos técnicos que devam entrar no glossário.

Responde apenas em JSON válido:
{"proposals":[{
  "kind":"tool_component_order|tool_upsert|entity_baseline_order|entity_upsert|prompt_upsert|glossary_upsert",
  "target":"categoria ou companies/people",
  "confidence":0.0,
  "reason":"explicação factual curta",
  "sources":[{"label":"fonte","url":"https://...","evidence":"facto concreto suportado"}],
  "payload":{}
}]}

Payloads:
- tool_component_order:
  {"component":"capability|popularity|task_fit|access","ranking":["tool-id"],
   "label":"nome da medição","url":"https://..."}
- entity_baseline_order: {"ranking":["entity-id"]}
- entity_upsert:
  target companies:
  {"id":"slug","name":"...","tagline":"...","description":"...","linkedin":"https://...",
   "category":"...","tags":["..."],"aliases":["..."]}
  target people:
  {"id":"slug","name":"...","role":"...","bio":"...","linkedin":"https://...",
   "tags":["..."],"aliases":["..."]}
- tool_upsert:
  {"id":"slug","name":"...","url":"https://...","categories":["coding"],
   "description":"...","best_for":"...","watch_out":"...","baseline_score":0,
   "aliases":["..."],"sources":[{"label":"...","url":"https://..."}],
   "category_positions":{"coding":{"capability":3,"popularity":4,"task_fit":2,"access":5}}}
- prompt_upsert:
  {"id":"slug","title":"...","category":"...","purpose":"...",
   "template":"mínimo 80 caracteres","keywords":["..."],"baseline_score":0}
- glossary_upsert:
  {"id":"slug","term":"...","english_term":"...","definition":"mínimo 40 caracteres",
   "example":"...","related":["..."],"aliases":["..."]}

Regras:
- Para rankings usa exclusivamente os IDs fornecidos no contexto.
- Rankings contêm exatamente os mesmos IDs atuais, apenas reordenados.
- Cada proposta precisa de pelo menos duas fontes independentes HTTPS.
- Em cada fonte inclui um campo "evidence" com a afirmação concreta sustentada.
- Não propor alterações sem evidência nova e material.
- Confiança acima de 0.92 apenas quando as fontes concordam claramente.
""".strip()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _proposal_id(proposal: dict[str, Any]) -> str:
    sources = sorted(
        {
            str(source.get("url") or "").strip()
            for source in proposal.get("sources") or []
            if isinstance(source, dict)
        }
    )
    canonical = json.dumps(
        {
            "kind": proposal.get("kind"),
            "target": proposal.get("target"),
            "payload": proposal.get("payload"),
            "reason": proposal.get("reason"),
            "sources": sources,
            "occurrence": (
                datetime.now(timezone.utc).strftime("%G-W%V")
                if proposal.get("kind") == "system_alert"
                else ""
            ),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return "knowledge_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
    proposal = {
        "kind": str(raw.get("kind") or "").strip(),
        "target": str(raw.get("target") or "").strip(),
        "confidence": round(float(raw.get("confidence") or 0.0), 3),
        "reason": str(raw.get("reason") or "").strip(),
        "sources": [
            {
                "label": str(source.get("label") or "").strip(),
                "url": str(source.get("url") or "").strip(),
                "evidence": str(source.get("evidence") or "").strip(),
            }
            for source in raw.get("sources") or []
            if isinstance(source, dict)
        ],
        "payload": dict(raw.get("payload") or {}),
    }
    proposal.update(
        proposal_id=_proposal_id(proposal),
        created_at=_now(),
        updated_at=_now(),
        status="pending",
        notes="",
    )
    return proposal


def _source_identities(proposal: dict[str, Any]) -> set[str]:
    identities = set()
    for source in proposal.get("sources") or []:
        parsed = urlparse(str(source.get("url") or ""))
        if parsed.scheme == "https" and parsed.hostname:
            host = parsed.hostname.casefold().removeprefix("www.")
            label = str(source.get("label") or "").strip().casefold().removeprefix("www.")
            if host == "vertexaisearch.cloud.google.com" and "." in label and " " not in label:
                identities.add(label)
            else:
                identities.add(host)
    return identities


def _grounding_hosts(grounding_sources: list[dict[str, Any]]) -> set[str]:
    return _source_identities({"sources": grounding_sources})


def _sources_are_grounded(
    proposal: dict[str, Any],
    grounding_sources: list[dict[str, Any]],
) -> bool:
    declared = _source_identities(proposal)
    grounded = _grounding_hosts(grounding_sources)
    return len(declared) >= 2 and declared <= grounded


def _has_trusted_source(proposal: dict[str, Any]) -> bool:
    return any(
        identity == suffix or identity.endswith("." + suffix)
        for identity in _source_identities(proposal)
        for suffix in TRUSTED_SOURCE_SUFFIXES
    )


def _ranking_valid(current: list[str], proposed: list[str]) -> bool:
    return bool(current) and len(proposed) == len(set(proposed)) and set(proposed) == set(current)


def _max_movement(current: list[str], proposed: list[str]) -> int:
    old = {item_id: index for index, item_id in enumerate(current)}
    return max((abs(old[item_id] - index) for index, item_id in enumerate(proposed)), default=0)


def proposal_issues(
    proposal: dict[str, Any],
    catalog: dict,
    directory: dict,
    *,
    grounding_sources: list[dict[str, Any]] | None = None,
) -> list[str]:
    issues: list[str] = []
    kind = proposal.get("kind")
    payload = proposal.get("payload") or {}
    if len(_source_identities(proposal)) < 2:
        issues.append("menos de duas fontes HTTPS independentes")
    if grounding_sources is not None and not _sources_are_grounded(proposal, grounding_sources):
        issues.append("fontes declaradas não confirmadas pelo grounding")
    if any(
        len(str(source.get("evidence") or "").strip()) < 20
        for source in proposal.get("sources") or []
    ):
        issues.append("fontes sem evidência concreta")
    if proposal.get("kind") in AUTO_APPLY_KINDS and not _has_trusted_source(proposal):
        issues.append("sem fonte independente de referência para auto-publicação")
    if not proposal.get("reason"):
        issues.append("sem justificação")

    if kind == "tool_component_order":
        category = str(proposal.get("target") or "")
        component = str(payload.get("component") or "")
        evidence = (catalog.get("tool_category_evidence") or {}).get(category) or {}
        current = ((evidence.get("components") or {}).get(component) or {}).get("ranking") or []
        proposed = [str(value) for value in payload.get("ranking") or []]
        if component not in {"capability", "popularity", "task_fit", "access"}:
            issues.append("componente inválido")
        if not _ranking_valid(list(current), proposed):
            issues.append("ranking não preserva os candidatos atuais")
        elif _max_movement(list(current), proposed) > 3:
            issues.append("movimento superior a três posições")
    elif kind == "entity_baseline_order":
        target = str(proposal.get("target") or "")
        current = list((catalog.get("entity_baselines") or {}).get(target) or [])
        proposed = [str(value) for value in payload.get("ranking") or []]
        available = {str(item["id"]) for item in directory.get(target) or []}
        if target not in {"companies", "people"}:
            issues.append("tipo de entidade inválido")
        if set(current) != available or not _ranking_valid(current, proposed):
            issues.append("ranking de entidades inválido")
        elif _max_movement(current, proposed) > 2:
            issues.append("movimento superior a duas posições")
    elif kind == "entity_upsert":
        target = str(proposal.get("target") or "")
        common = {"id", "name", "linkedin", "tags", "aliases"}
        required = common | (
            {"tagline", "description", "category"}
            if target == "companies"
            else {"role", "bio"}
        )
        if target not in {"companies", "people"}:
            issues.append("tipo de entidade inválido")
        if not required <= set(payload):
            issues.append("entidade incompleta")
        if payload.get("linkedin") and not str(payload.get("linkedin")).startswith("https://"):
            issues.append("LinkedIn inválido")
    elif kind == "tool_upsert":
        required = {
            "id", "name", "url", "categories", "description", "best_for",
            "watch_out", "baseline_score", "aliases", "sources", "category_positions",
        }
        if not required <= set(payload):
            issues.append("ferramenta incompleta")
        if not str(payload.get("url") or "").startswith("https://"):
            issues.append("URL de ferramenta inválido")
        valid_categories = set(catalog.get("tool_category_evidence") or {})
        categories = set(payload.get("categories") or [])
        if not categories or not categories <= valid_categories:
            issues.append("categorias de ferramenta inválidas")
        score = payload.get("baseline_score")
        if score is None or not 0 <= int(score) <= 100:
            issues.append("score de ferramenta inválido")
        positions = payload.get("category_positions") or {}
        if set(positions) != categories:
            issues.append("posições por categoria incompletas")
        for category in categories:
            components = positions.get(category) or {}
            if set(components) != {"capability", "popularity", "task_fit", "access"}:
                issues.append(f"posições incompletas em {category}")
                continue
            maximum = max(
                len(data["ranking"])
                for data in catalog["tool_category_evidence"][category]["components"].values()
            ) + 1
            if any(not 1 <= int(position) <= maximum for position in components.values()):
                issues.append(f"posição inválida em {category}")
    elif kind == "prompt_upsert":
        required = {"id", "title", "category", "purpose", "template", "keywords", "baseline_score"}
        if not required <= set(payload):
            issues.append("prompt incompleto")
        if len(str(payload.get("template") or "")) < 80:
            issues.append("template demasiado curto")
        score = payload.get("baseline_score")
        if score is None or not 0 <= int(score) <= 100:
            issues.append("score inválido")
    elif kind == "glossary_upsert":
        required = {"id", "term", "definition", "example", "related", "aliases"}
        if not required <= set(payload):
            issues.append("termo incompleto")
        if len(str(payload.get("definition") or "")) < 40:
            issues.append("definição demasiado curta")
    else:
        issues.append("tipo de proposta desconhecido")
    return issues


def _upsert(records: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    for index, record in enumerate(records):
        if str(record.get("id")) == str(payload["id"]):
            records[index] = {**record, **payload}
            return
    records.append(payload)


def apply_proposal(proposal: dict[str, Any], catalog: dict, directory: dict) -> None:
    payload = copy.deepcopy(proposal["payload"])
    kind = proposal["kind"]
    if kind == "tool_component_order":
        component = catalog["tool_category_evidence"][proposal["target"]]["components"][
            payload["component"]
        ]
        component["ranking"] = list(payload["ranking"])
        component["label"] = str(payload.get("label") or component["label"])
        component["url"] = str(payload.get("url") or component["url"])
    elif kind == "entity_baseline_order":
        catalog["entity_baselines"][proposal["target"]] = list(payload["ranking"])
    elif kind == "entity_upsert":
        target = proposal["target"]
        _upsert(directory[target], payload)
        baseline = catalog["entity_baselines"][target]
        if str(payload["id"]) not in baseline:
            baseline.append(str(payload["id"]))
    elif kind == "tool_upsert":
        positions = payload.pop("category_positions")
        _upsert(catalog["tools"], payload)
        tool_id = str(payload["id"])
        for category, component_positions in positions.items():
            components = catalog["tool_category_evidence"][category]["components"]
            for component, position in component_positions.items():
                ranking = [value for value in components[component]["ranking"] if value != tool_id]
                ranking.insert(max(0, int(position) - 1), tool_id)
                components[component]["ranking"] = ranking
    elif kind == "prompt_upsert":
        _upsert(catalog["prompts"], payload)
    elif kind == "glossary_upsert":
        english_term = str(payload.pop("english_term", "") or "")
        _upsert(catalog["glossary"], payload)
        if english_term:
            catalog.setdefault("glossary_english", {})[str(payload["id"])] = english_term
    else:
        raise ValueError(f"Tipo de proposta não suportado: {kind}")


def apply_approved_reviews(root: Path) -> dict[str, int]:
    review_path = root / "data" / "knowledge_review.jsonl"
    records = _load_jsonl(review_path)
    if not records:
        return {"applied": 0, "failed": 0}
    catalog_path = root / "config" / "ptia_knowledge.json"
    directory_path = root / "site" / "assets" / "quem-e-quem.json"
    catalog = _read_json(catalog_path)
    directory = _read_json(directory_path)
    applied = failed = 0
    for record in records:
        if record.get("status") != "approved":
            continue
        try:
            blocking = [
                issue
                for issue in proposal_issues(record, catalog, directory)
                if "movimento" not in issue
            ]
            if blocking:
                raise ValueError("; ".join(blocking))
            candidate_catalog = copy.deepcopy(catalog)
            candidate_directory = copy.deepcopy(directory)
            apply_proposal(record, candidate_catalog, candidate_directory)
            validate_catalog(candidate_catalog, candidate_directory)
            catalog = candidate_catalog
            directory = candidate_directory
            record.update(status="applied", notes="Aplicada após aprovação editorial.")
            applied += 1
        except Exception as exc:
            record.update(status="failed", notes=str(exc))
            failed += 1
        record["updated_at"] = _now()
    _write_json(catalog_path, catalog)
    _write_json(directory_path, directory)
    _write_jsonl(review_path, records)
    return {"applied": applied, "failed": failed}


def run_knowledge_automation(
    root: Path,
    *,
    provider: GeminiGroundedSearchProvider | None = None,
) -> dict[str, Any]:
    provider = provider or GeminiGroundedSearchProvider(timeout_seconds=90)
    review_path = root / "data" / "knowledge_review.jsonl"
    run_path = root / "data" / "knowledge_runs.jsonl"
    catalog_path = root / "config" / "ptia_knowledge.json"
    directory_path = root / "site" / "assets" / "quem-e-quem.json"
    catalog = _read_json(catalog_path)
    directory = _read_json(directory_path)
    existing = {
        record.get("proposal_id"): record for record in _load_jsonl(review_path)
    }

    provider_error = ""
    if provider.available:
        context = {
            "tool_categories": {
                category: {
                    component: data["ranking"]
                    for component, data in evidence["components"].items()
                }
                for category, evidence in catalog["tool_category_evidence"].items()
            },
            "companies": catalog["entity_baselines"]["companies"],
            "people": catalog["entity_baselines"]["people"],
            "prompt_ids": [item["id"] for item in catalog["prompts"]],
            "glossary_ids": [item["id"] for item in catalog["glossary"]],
        }
        tasks = (
            DISCOVERY_TASKS
            if getattr(provider, "partitioned_research", False)
            else (("all", ""),)
        )
        raw_proposals = []
        task_errors: list[str] = []
        for task_name, task_instruction in tasks:
            response = None
            errors: list[str] = []
            for _ in range(2):
                try:
                    if getattr(provider, "partitioned_research", False):
                        research = provider.grounded_research(
                            RESEARCH_PROMPT
                            + "\n\nFoco:\n"
                            + task_instruction,
                            temperature=0.1,
                        )
                        sources = [
                            source
                            for source in research.get("sources") or []
                            if isinstance(source, dict)
                        ]
                        permitted_sources = json.dumps(sources, ensure_ascii=False)
                        response = provider.structured_json(
                            DISCOVERY_PROMPT
                            + "\n\nFoco obrigatório desta chamada:\n"
                            + task_instruction
                            + "\n\nUsa apenas a evidência e os URLs exatos abaixo. "
                            "Se a evidência não suportar uma proposta, não a cries."
                            + "\n\nFontes permitidas:\n"
                            + permitted_sources
                            + "\n\nEvidência grounded:\n"
                            + str(research.get("text") or "")
                            + "\n\nContexto atual:\n"
                            + json.dumps(context, ensure_ascii=False),
                            temperature=0.0,
                        )
                        response["_grounding_sources"] = sources
                    else:
                        response = provider.grounded_json(
                            DISCOVERY_PROMPT
                            + "\n\nContexto atual:\n"
                            + json.dumps(context, ensure_ascii=False),
                            temperature=0.1,
                        )
                    break
                except Exception as exc:
                    errors.append(str(exc)[:500])
            if response is None:
                detail = " | ".join(errors)
                task_errors.append(f"{task_name}: {detail}")
                raw_proposals.append({
                    "kind": "system_alert",
                    "target": f"external_discovery:{task_name}",
                    "confidence": 0,
                    "reason": (
                        f"Pesquisa de {task_name} falhou sem bloquear as restantes: {detail}"
                    ),
                    "sources": [],
                    "payload": {},
                })
                continue
            task_grounding = [
                source
                for source in response.get("_grounding_sources") or []
                if isinstance(source, dict)
            ]
            for raw in response.get("proposals") or []:
                if not isinstance(raw, dict):
                    continue
                raw = dict(raw)
                raw["_grounding_sources"] = task_grounding
                raw["_task_name"] = task_name
                raw_proposals.append(raw)
        provider_error = " || ".join(task_errors)[:1000]
        grounding_sources = []
    else:
        grounding_sources = []
        raw_proposals = [{
            "kind": "system_alert",
            "target": "external_discovery",
            "confidence": 0,
            "reason": "GEMINI_API_KEY não está disponível no executor semanal.",
            "sources": [],
            "payload": {},
        }]

    staged_catalog = copy.deepcopy(catalog)
    staged_directory = copy.deepcopy(directory)
    auto_applied = pending = 0
    for raw in raw_proposals:
        if not isinstance(raw, dict):
            continue
        proposal_grounding = [
            source
            for source in raw.get("_grounding_sources", grounding_sources) or []
            if isinstance(source, dict)
        ]
        task_name = str(raw.get("_task_name") or "")
        try:
            proposal = _normalise(raw)
        except (TypeError, ValueError) as exc:
            proposal = _normalise({
                "kind": "system_alert",
                "target": "invalid_external_proposal",
                "confidence": 0,
                "reason": f"Proposta externa inválida: {str(exc)[:300]}",
                "sources": [],
                "payload": {},
            })
        previous = existing.get(proposal["proposal_id"])
        if previous and previous.get("status") in {"approved", "rejected", "applied"}:
            proposal["status"] = previous["status"]
            proposal["notes"] = previous.get("notes", "")
            proposal["created_at"] = previous.get("created_at", proposal["created_at"])
            proposal["issues"] = previous.get("issues", [])
            existing[proposal["proposal_id"]] = proposal
            continue
        issues = (
            [proposal["reason"]]
            if proposal["kind"] == "system_alert"
            else proposal_issues(
                proposal,
                staged_catalog,
                staged_directory,
                grounding_sources=proposal_grounding,
            )
        )
        if task_name in TASK_KINDS and proposal["kind"] not in TASK_KINDS[task_name]:
            issues.append(f"tipo incompatível com a pesquisa de {task_name}")
        proposal["issues"] = issues
        if (
            proposal["kind"] in AUTO_APPLY_KINDS
            and proposal["confidence"] >= AUTO_CONFIDENCE
            and not issues
        ):
            try:
                candidate_catalog = copy.deepcopy(staged_catalog)
                candidate_directory = copy.deepcopy(staged_directory)
                apply_proposal(proposal, candidate_catalog, candidate_directory)
                validate_catalog(candidate_catalog, candidate_directory)
                staged_catalog = candidate_catalog
                staged_directory = candidate_directory
                proposal.update(
                    status="applied",
                    notes="Aplicada automaticamente por confiança elevada.",
                )
                auto_applied += 1
            except Exception as exc:
                proposal["issues"] = [str(exc)]
                pending += 1
        else:
            pending += 1
        existing[proposal["proposal_id"]] = proposal

    validate_catalog(staged_catalog, staged_directory)
    _write_json(catalog_path, staged_catalog)
    _write_json(directory_path, staged_directory)
    records = sorted(
        existing.values(),
        key=lambda item: item.get("created_at", ""),
        reverse=True,
    )
    _write_jsonl(review_path, records)
    run = {
        "run_id": "knowledge_run_" + hashlib.sha256(_now().encode()).hexdigest()[:12],
        "created_at": _now(),
        "status": "completed" if provider.available and not provider_error else "attention",
        "provider_available": provider.available,
        "provider_error": provider_error,
        "proposals": len(raw_proposals),
        "auto_applied": auto_applied,
        "pending": pending,
    }
    runs = _load_jsonl(run_path)
    _write_jsonl(run_path, [*runs[-51:], run])
    return run


def knowledge_review_snapshot(root: Path) -> dict[str, Any]:
    reviews = _load_jsonl(root / "data" / "knowledge_review.jsonl")
    runs = _load_jsonl(root / "data" / "knowledge_runs.jsonl")
    counts = {status: 0 for status in REVIEW_STATUSES}
    for review in reviews:
        status = str(review.get("status") or "pending")
        counts[status] = counts.get(status, 0) + 1
    return {
        "counts": counts,
        "reviews": reviews[:100],
        "runs": runs[-12:][::-1],
        "last_run": runs[-1] if runs else None,
    }


def update_review_status(
    root: Path,
    *,
    proposal_id: str,
    status: str,
    notes: str = "",
) -> dict[str, Any]:
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError("Estado de revisão inválido.")
    path = root / "data" / "knowledge_review.jsonl"
    records = _load_jsonl(path)
    for record in records:
        if record.get("proposal_id") == proposal_id:
            record.update(status=status, notes=notes, updated_at=_now())
            _write_jsonl(path, records)
            return record
    raise ValueError("Proposta de Recursos não encontrada.")


def update_review_status_remote(
    root: Path,
    *,
    proposal_id: str,
    status: str,
    notes: str = "",
) -> dict[str, Any]:
    from ptia_engine.knowledge_remote import publish_review_state, read_remote_text

    if status not in {"approved", "rejected", "pending"}:
        raise ValueError("Estado de revisão inválido.")
    remote_text, _ = read_remote_text("data/knowledge_review.jsonl")
    records = [
        json.loads(line)
        for line in remote_text.splitlines()
        if line.strip()
    ]
    if not records:
        records = _load_jsonl(root / "data" / "knowledge_review.jsonl")
    for record in records:
        if record.get("proposal_id") != proposal_id:
            continue
        record.update(status=status, notes=notes, updated_at=_now())
        text = "".join(
            json.dumps(item, ensure_ascii=False) + "\n"
            for item in records
        )
        publish_review_state(root, text)
        return record
    raise ValueError("Proposta de Recursos não encontrada no estado remoto.")
