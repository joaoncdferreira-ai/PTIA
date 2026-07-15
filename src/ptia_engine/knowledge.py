from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


RESOURCE_PATHS = (
    "/recursos/",
    "/ia-em-portugal/",
    "/ferramentas/",
    "/prompts/",
    "/glossario/",
    "/metodologia-indice/",
)

CATEGORY_LABELS = {
    "coding": "Coding",
    "estudo": "Estudo",
    "pesquisa": "Pesquisa",
    "produtividade": "Produtividade",
    "design": "Design",
    "video": "Vídeo",
    "imagem": "Imagem",
    "marketing": "Marketing",
    "automacoes": "Automações",
}

ENTITY_ALIASES = {
    "Defined.ai": ["defined ai", "definedcrowd", "defined crowd"],
    "Bright Pixel (Sonae IM)": ["bright pixel", "sonae im"],
    "ECO - Economia Online": ["eco economia online"],
}

ENTITY_STATUSES = {"active", "acquired", "insolvent", "liquidated", "inactive", "unknown"}
ENTITY_ELIGIBILITY = {"eligible", "provisional", "watchlist", "ineligible"}
NON_ACTIVE_ENTITY_STATUSES = {"acquired", "insolvent", "liquidated", "inactive"}
VERIFICATION_MAX_AGE_DAYS = 45
COMPANY_SCORE_WEIGHTS = {
    "impact": 0.30,
    "momentum": 0.25,
    "innovation": 0.20,
    "portugal_relevance": 0.15,
    "ecosystem_contribution": 0.10,
}
PERSON_SCORE_WEIGHTS = {
    "work_output": 0.35,
    "recognition": 0.25,
    "ecosystem_contribution": 0.20,
    "recency": 0.10,
    "portugal_relevance": 0.10,
}


class KnowledgeValidationError(ValueError):
    pass


@dataclass(slots=True)
class ArticleSignal:
    title: str
    body: str
    published_at: datetime
    url: str

    @property
    def text(self) -> str:
        body_without_sources = re.sub(
            r"(?im)^\s*fonte\s*:.*$|https?://\S+",
            " ",
            self.body,
        )
        return _fold(f"{self.title} {body_without_sources}")


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold(value)).strip("-")


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeValidationError(f"Não foi possível ler {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KnowledgeValidationError(f"{path} deve conter um objeto JSON.")
    return payload


def _validate_unique(records: list[dict], label: str) -> None:
    ids = [str(item.get("id") or "").strip() for item in records]
    if any(not item_id for item_id in ids):
        raise KnowledgeValidationError(f"{label}: todos os registos precisam de id.")
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise KnowledgeValidationError(f"{label}: ids duplicados: {', '.join(duplicates)}")


def validate_catalog(catalog: dict, directory: dict) -> None:
    tools = list(catalog.get("tools") or [])
    prompts = list(catalog.get("prompts") or [])
    glossary = list(catalog.get("glossary") or [])
    companies = list(directory.get("companies") or [])
    people = list(directory.get("people") or [])
    minimums = {
        "ferramentas": (tools, 25),
        "prompts": (prompts, 10),
        "glossário": (glossary, 35),
        "empresas": (companies, 10),
        "pessoas": (people, 10),
    }
    for label, (records, minimum) in minimums.items():
        if len(records) < minimum:
            raise KnowledgeValidationError(
                f"{label}: são necessários pelo menos {minimum} registos; existem {len(records)}."
            )
        _validate_unique(records, label)

    valid_categories = set(CATEGORY_LABELS)
    tool_ids = {str(tool["id"]) for tool in tools}
    for tool in tools:
        categories = set(tool.get("categories") or [])
        if not categories or not categories <= valid_categories:
            raise KnowledgeValidationError(
                f"Ferramenta {tool['id']} tem categorias inválidas: {sorted(categories)}"
            )
        if not str(tool.get("url") or "").startswith("https://"):
            raise KnowledgeValidationError(f"Ferramenta {tool['id']} precisa de URL HTTPS.")
        score = int(tool.get("baseline_score") or 0)
        if not 0 <= score <= 100:
            raise KnowledgeValidationError(f"Ferramenta {tool['id']} tem score inválido.")

    category_evidence = catalog.get("tool_category_evidence") or {}
    if set(category_evidence) != valid_categories:
        raise KnowledgeValidationError(
            "A evidência de ferramentas deve cobrir exatamente todas as categorias."
        )
    tools_by_id = {str(tool["id"]): tool for tool in tools}
    expected_components = {"capability", "popularity", "task_fit", "access"}
    for category, assessment in category_evidence.items():
        weights = assessment.get("weights") or {}
        components = assessment.get("components") or {}
        if set(weights) != expected_components or set(components) != expected_components:
            raise KnowledgeValidationError(
                f"Evidência {category} precisa dos quatro componentes definidos."
            )
        if not math.isclose(sum(float(value) for value in weights.values()), 1.0):
            raise KnowledgeValidationError(f"Os pesos de {category} devem somar 1.")
        candidate_ids: set[str] | None = None
        for component, evidence in components.items():
            ranked_ids = list(evidence.get("ranking") or [])
            if len(ranked_ids) < 5 or len(ranked_ids) != len(set(ranked_ids)):
                raise KnowledgeValidationError(
                    f"{category}/{component} precisa de pelo menos 5 ferramentas únicas."
                )
            if not str(evidence.get("url") or "").startswith("https://"):
                raise KnowledgeValidationError(f"{category}/{component} precisa de fonte HTTPS.")
            if candidate_ids is None:
                candidate_ids = set(ranked_ids)
            elif set(ranked_ids) != candidate_ids:
                raise KnowledgeValidationError(
                    f"Todos os componentes de {category} devem avaliar as mesmas ferramentas."
                )
        unknown = (candidate_ids or set()) - tool_ids
        mismatched = [
            tool_id
            for tool_id in candidate_ids or set()
            if tool_id in tools_by_id
            and category not in set(tools_by_id[tool_id].get("categories") or [])
        ]
        if unknown or mismatched:
            raise KnowledgeValidationError(
                f"Evidência {category}: desconhecidos={sorted(unknown)}; "
                f"categoria incorreta={sorted(mismatched)}."
            )

    for prompt in prompts:
        if len(str(prompt.get("template") or "")) < 80:
            raise KnowledgeValidationError(f"Prompt {prompt['id']} é demasiado curto.")
    for term in glossary:
        if len(str(term.get("definition") or "")) < 40:
            raise KnowledgeValidationError(f"Definição {term['id']} é demasiado curta.")
    english_terms = catalog.get("glossary_english") or {}
    glossary_ids = {str(term["id"]) for term in glossary}
    unknown_translations = set(english_terms) - glossary_ids
    if unknown_translations:
        raise KnowledgeValidationError(
            f"Traduções inglesas com IDs desconhecidos: {sorted(unknown_translations)}"
        )

    baselines = catalog.get("entity_baselines") or {}
    for key, records in (("companies", companies), ("people", people)):
        ordered_ids = list(baselines.get(key) or [])
        available_ids = {str(record["id"]) for record in records}
        if len(ordered_ids) != len(set(ordered_ids)):
            raise KnowledgeValidationError(f"Baseline {key}: existem IDs duplicados.")
        if set(ordered_ids) != available_ids:
            missing = sorted(available_ids - set(ordered_ids))
            unknown = sorted(set(ordered_ids) - available_ids)
            raise KnowledgeValidationError(
                f"Baseline {key} incompleta. Em falta: {missing}; desconhecidos: {unknown}."
            )

        for record in records:
            status = str(record.get("status") or "active")
            eligibility = str(record.get("eligibility") or "")
            if status not in ENTITY_STATUSES:
                raise KnowledgeValidationError(
                    f"Entidade {record['id']} tem estado inválido: {status}."
                )
            if eligibility and eligibility not in ENTITY_ELIGIBILITY:
                raise KnowledgeValidationError(
                    f"Entidade {record['id']} tem elegibilidade inválida: {eligibility}."
                )
            verification = record.get("verification") or {}
            if not isinstance(verification, dict):
                raise KnowledgeValidationError(f"Entidade {record['id']} tem verificação inválida.")
            sources = list(verification.get("sources") or [])
            if any(
                not isinstance(source, dict)
                or not str(source.get("url") or "").startswith("https://")
                for source in sources
            ):
                raise KnowledgeValidationError(
                    f"Entidade {record['id']} tem fontes de verificação inválidas."
                )
            if eligibility == "eligible" and len(_source_hosts(sources)) < 2:
                raise KnowledgeValidationError(
                    f"Entidade {record['id']} precisa de duas fontes independentes para ser elegível."
                )


def load_article_signals(site_feed_path: Path, *, now: datetime) -> list[ArticleSignal]:
    if not site_feed_path.exists():
        return []
    payload = _load_json(site_feed_path)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=84)
    signals: list[ArticleSignal] = []
    seen: set[str] = set()
    for post in payload.get("posts", []):
        published = _parse_datetime(post.get("published_at"))
        if not published or published > now.astimezone(timezone.utc) or published < cutoff:
            continue
        key = str(post.get("article_url") or post.get("id") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        signals.append(
            ArticleSignal(
                title=str(post.get("title") or ""),
                body=str(post.get("body") or ""),
                published_at=published,
                url="/" + key.strip("/"),
            )
        )
    return signals


def _aliases(record: dict) -> list[str]:
    name = str(record.get("name") or record.get("term") or "")
    values = [name, re.sub(r"[^a-zA-ZÀ-ÿ0-9]+", " ", name)]
    values.extend(str(value) for value in record.get("aliases", []))
    values.extend(ENTITY_ALIASES.get(name, []))
    return sorted({_fold(value) for value in values if value}, key=len, reverse=True)


def _matches(signal: ArticleSignal, aliases: Iterable[str]) -> bool:
    haystack = f" {signal.text} "
    return any(f" {alias} " in haystack or alias in signal.text for alias in aliases if alias)


def _evidence(record: dict, signals: list[ArticleSignal], *, limit: int = 4) -> list[dict]:
    matches = [signal for signal in signals if _matches(signal, _aliases(record))]
    matches.sort(key=lambda item: item.published_at, reverse=True)
    return [
        {
            "title": item.title,
            "url": item.url,
            "published_at": item.published_at.date().isoformat(),
        }
        for item in matches[:limit]
    ]


def _previous_ranks(previous: dict, key: str) -> dict[str, int]:
    return {
        str(item.get("id")): int(item.get("rank") or 0)
        for item in previous.get(key, [])
        if item.get("id") and item.get("rank")
    }


def _previous_category_ranks(previous: dict) -> dict[str, dict[str, int]]:
    category_ranks: dict[str, dict[str, int]] = {}
    for item in previous.get("tools", []):
        tool_id = str(item.get("id") or "")
        if not tool_id:
            continue
        for category, rank in (item.get("category_ranks") or {}).items():
            if rank:
                category_ranks.setdefault(str(category), {})[tool_id] = int(rank)
    return category_ranks


def _movement(current: int, previous: int | None) -> int | None:
    if not previous:
        return None
    return previous - current


def _ranking_change(
    current: int,
    previous: int | None,
    *,
    comparison_available: bool,
    top_limit: int = 10,
    baseline_label: str = "Nova edição",
) -> dict:
    if not comparison_available:
        return {"kind": "baseline", "delta": None, "label": baseline_label}
    if previous is None or (current <= top_limit and previous > top_limit):
        label = "Entrou no Top" if current <= top_limit else "Nova entrada"
        return {"kind": "entered", "delta": None, "label": label}
    delta = previous - current
    if delta > 0:
        return {"kind": "up", "delta": delta, "label": f"Subiu {delta}"}
    if delta < 0:
        return {"kind": "down", "delta": delta, "label": f"Desceu {abs(delta)}"}
    return {"kind": "same", "delta": 0, "label": "Manteve"}


def _source_hosts(sources: Iterable[dict]) -> set[str]:
    hosts: set[str] = set()
    for source in sources:
        match = re.match(r"https://([^/]+)", str(source.get("url") or "").casefold())
        if match:
            hosts.add(match.group(1).removeprefix("www."))
    return hosts


def _verification_is_fresh(record: dict, *, now: datetime) -> bool:
    verified_at = _parse_datetime((record.get("verification") or {}).get("verified_at"))
    if verified_at is None:
        return False
    age = now.astimezone(timezone.utc) - verified_at
    return timedelta(0) <= age <= timedelta(days=VERIFICATION_MAX_AGE_DAYS)


def _entity_eligibility(record: dict, *, now: datetime) -> str:
    status = str(record.get("status") or "active")
    explicit = str(record.get("eligibility") or "")
    if status in NON_ACTIVE_ENTITY_STATUSES:
        return "ineligible"
    if explicit in {"watchlist", "ineligible"}:
        return explicit
    sources = list((record.get("verification") or {}).get("sources") or [])
    if (
        status == "active"
        and len(_source_hosts(sources)) >= 2
        and _verification_is_fresh(record, now=now)
    ):
        return "eligible"
    return "provisional"


def _bounded_score(value: object, *, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, score))


def _momentum_score(evidence: list[dict], *, now: datetime) -> float:
    score = 0.0
    for item in evidence:
        published_at = _parse_datetime(item.get("published_at"))
        if published_at is None:
            continue
        age_days = max(0, (now.astimezone(timezone.utc) - published_at).days)
        score += 35.0 * math.exp(-age_days / 42.0)
    return round(min(100.0, score), 1)


def _score_band(score: float) -> str:
    if score >= 75:
        return "Líder verificado"
    if score >= 60:
        return "Destaque"
    return "A acompanhar"


def _entity_breakdown(
    record: dict,
    evidence: list[dict],
    *,
    now: datetime,
) -> dict[str, float]:
    assessment = record.get("assessment") or {}
    if "role" in record:
        return {
            "work_output": _bounded_score(assessment.get("work_output"), default=50.0),
            "recognition": _bounded_score(assessment.get("recognition"), default=50.0),
            "ecosystem_contribution": _bounded_score(
                assessment.get("ecosystem_contribution"), default=50.0
            ),
            "recency": _momentum_score(evidence, now=now),
            "portugal_relevance": _bounded_score(
                assessment.get("portugal_relevance"), default=70.0
            ),
        }
    return {
        "impact": _bounded_score(assessment.get("impact"), default=50.0),
        "momentum": _momentum_score(evidence, now=now),
        "innovation": _bounded_score(assessment.get("innovation"), default=50.0),
        "portugal_relevance": _bounded_score(assessment.get("portugal_relevance"), default=70.0),
        "ecosystem_contribution": _bounded_score(
            assessment.get("ecosystem_contribution"), default=50.0
        ),
    }


def _entity_score(record: dict, breakdown: dict[str, float], eligibility: str) -> float:
    weights = PERSON_SCORE_WEIGHTS if "role" in record else COMPANY_SCORE_WEIGHTS
    score = sum(breakdown[key] * weight for key, weight in weights.items())
    if eligibility == "provisional":
        score = min(score, 69.9)
    return round(score, 1)


def _entity_confidence(record: dict, eligibility: str) -> str:
    verification = record.get("verification") or {}
    source_count = len(_source_hosts(verification.get("sources") or []))
    if eligibility == "eligible" and source_count >= 3:
        return "alta"
    if eligibility == "eligible":
        return "média"
    if eligibility == "provisional":
        return "provisória"
    return "não elegível"


def _entity_explanation(evidence: list[dict], eligibility: str) -> str:
    if eligibility == "provisional":
        return "Posição provisória: aguarda duas fontes externas e verificação recente."
    if evidence:
        return f"{len(evidence)} sinais editoriais recentes; elegibilidade confirmada externamente."
    return "Elegibilidade confirmada; sem novo sinal editorial na janela atual."


def _order_by_ids(records: list[dict], ordered_ids: list[str]) -> list[dict]:
    by_id = {str(record["id"]): record for record in records}
    return [by_id[item_id] for item_id in ordered_ids]


def rank_entities(
    records: list[dict],
    signals: list[ArticleSignal],
    *,
    previous_ranks: dict[str, int],
    now: datetime,
) -> tuple[list[dict], list[dict]]:
    ranked: list[dict] = []
    excluded: list[dict] = []
    for position, record in enumerate(records):
        evidence = (
            []
            if str(record.get("category") or "").casefold() == "media"
            else _evidence(record, signals)
        )
        eligibility = _entity_eligibility(record, now=now)
        breakdown = _entity_breakdown(record, evidence, now=now)
        score = _entity_score(record, breakdown, eligibility)
        item = {
            **record,
            "status": str(record.get("status") or "active"),
            "eligibility": eligibility,
            "baseline_position": position + 1,
            "score": score,
            "score_band": _score_band(score),
            "score_breakdown": breakdown,
            "evidence": evidence,
            "confidence": _entity_confidence(record, eligibility),
            "explanation": _entity_explanation(evidence, eligibility),
        }
        if eligibility in {"watchlist", "ineligible"}:
            item.update(
                rank=None,
                previous_rank=previous_ranks.get(item["id"]),
                movement=None,
                ranking_change={
                    "kind": "removed",
                    "delta": None,
                    "label": "Fora do índice ativo",
                },
            )
            excluded.append(item)
        else:
            ranked.append(item)

    ranked.sort(
        key=lambda item: (
            0 if item["eligibility"] == "eligible" else 1,
            -item["score"] if item["eligibility"] == "eligible" else item["baseline_position"],
            item["baseline_position"],
            item["name"],
        )
    )
    published_rank = 0
    for item in ranked:
        previous_rank = previous_ranks.get(item["id"])
        item["previous_rank"] = previous_rank
        if item["eligibility"] != "eligible":
            item["rank"] = None
            item["movement"] = None
            item["ranking_change"] = {
                "kind": "verification_pending",
                "delta": None,
                "label": "Fora do ranking at? cumprir o gate de fontes",
            }
            continue
        published_rank += 1
        item["rank"] = published_rank
        item["movement"] = _movement(published_rank, previous_rank)
        item["ranking_change"] = _ranking_change(
            published_rank,
            previous_rank,
            comparison_available=bool(previous_ranks),
        )
    excluded.sort(key=lambda item: (item["status"], item["name"]))
    return ranked, excluded


def rank_tools(
    tools: list[dict],
    signals: list[ArticleSignal],
    *,
    category_evidence: dict[str, dict],
    previous_ranks: dict[str, int],
    previous_category_ranks: dict[str, dict[str, int]],
) -> list[dict]:
    ranked_by_id: dict[str, dict] = {}
    for tool in tools:
        evidence = _evidence(tool, signals)
        ranked_by_id[str(tool["id"])] = {
            **tool,
            "score": float(tool["baseline_score"]),
            "evidence": evidence,
            "category_ranks": {},
            "category_scores": {},
            "category_breakdowns": {},
            "category_sources": {},
            "category_movements": {},
            "category_confidence": {},
            "category_external_source_count": {},
            "category_publication_status": {},
            "score_basis": "avaliação relativa por finalidade",
        }

    for category, assessment in category_evidence.items():
        weights = assessment["weights"]
        components = assessment["components"]
        candidate_ids = list(components["capability"]["ranking"])
        category_scores: dict[str, float] = {tool_id: 0.0 for tool_id in candidate_ids}
        breakdowns: dict[str, dict[str, float]] = {tool_id: {} for tool_id in candidate_ids}
        for component, evidence_source in components.items():
            ranked_ids = list(evidence_source["ranking"])
            denominator = max(1, len(ranked_ids) - 1)
            for position, tool_id in enumerate(ranked_ids):
                component_score = round(100.0 - (position / denominator * 45.0), 1)
                breakdowns[tool_id][component] = component_score
                category_scores[tool_id] += component_score * float(weights[component])
        ordered = sorted(candidate_ids, key=lambda tool_id: (-category_scores[tool_id], tool_id))
        for position, tool_id in enumerate(ordered, 1):
            item = ranked_by_id[tool_id]
            previous_rank = previous_category_ranks.get(category, {}).get(tool_id)
            item["category_ranks"][category] = position
            item["category_scores"][category] = round(category_scores[tool_id], 1)
            item["category_breakdowns"][category] = breakdowns[tool_id]
            item["category_movements"][category] = _ranking_change(
                position,
                previous_rank,
                comparison_available=bool(previous_category_ranks.get(category)),
                baseline_label="Nova categoria",
            )
            component_sources = [
                {"component": component, "label": source["label"], "url": source["url"]}
                for component, source in components.items()
            ]
            tool_sources = [
                {
                    "component": "release",
                    "label": str(source.get("label") or "Fonte do produto"),
                    "url": str(source.get("url") or ""),
                }
                for source in item.get("sources") or []
                if str(source.get("url") or "").startswith("https://")
            ]
            category_sources = []
            seen_urls = set()
            for source in [*component_sources, *tool_sources]:
                if source["url"] in seen_urls:
                    continue
                seen_urls.add(source["url"])
                category_sources.append(source)
            item["category_sources"][category] = category_sources
            external_hosts = _source_hosts(
                source
                for source in category_sources
                if not str(source["url"]).startswith("https://ptia.pt/")
            )
            item["category_external_source_count"][category] = len(external_hosts)
            item["category_publication_status"][category] = (
                "ranked" if len(external_hosts) >= 2 else "watchlist"
            )
            item["category_confidence"][category] = (
                "alta"
                if len(external_hosts) >= 3
                else "média"
                if len(external_hosts) >= 2
                else "editorial"
            )

    ranked = list(ranked_by_id.values())
    for item in ranked:
        if item["category_scores"]:
            scores = list(item["category_scores"].values())
            item["score"] = round(sum(scores) / len(scores), 1)
    ranked.sort(key=lambda item: (-item["score"], item["name"]))
    for rank, item in enumerate(ranked, 1):
        item["rank"] = rank
        previous_rank = previous_ranks.get(item["id"])
        item["previous_rank"] = previous_rank
        item["movement"] = _movement(rank, previous_rank)
        item["ranking_change"] = _ranking_change(
            rank,
            previous_rank,
            comparison_available=bool(previous_ranks),
        )
    return ranked


def rank_prompts(
    prompts: list[dict],
    signals: list[ArticleSignal],
    *,
    previous_ranks: dict[str, int],
) -> list[dict]:
    ranked = []
    for prompt in prompts:
        keywords = [_fold(value) for value in prompt.get("keywords", [])]
        topical_articles = sum(
            1
            for signal in signals
            if any(keyword in signal.text for keyword in keywords if keyword)
        )
        ranked.append(
            {
                **prompt,
                "score": float(prompt["baseline_score"]),
                "topical_articles": topical_articles,
                "selection_kind": "curadoria editorial",
                "usage_evidence": "ainda não medido",
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["title"]))
    for rank, item in enumerate(ranked, 1):
        item["rank"] = rank
        previous_rank = previous_ranks.get(item["id"])
        item["previous_rank"] = previous_rank
        item["movement"] = _movement(rank, previous_rank)
        item["ranking_change"] = _ranking_change(
            rank,
            previous_rank,
            comparison_available=bool(previous_ranks),
        )
    return ranked


def rank_glossary(
    glossary: list[dict],
    signals: list[ArticleSignal],
    *,
    english_terms: dict[str, str],
) -> list[dict]:
    ranked = []
    for term in glossary:
        mentions = sum(1 for signal in signals if _matches(signal, _aliases(term)))
        ranked.append(
            {
                **term,
                "english_term": str(english_terms.get(str(term["id"])) or ""),
                "mentions_12w": mentions,
            }
        )
    ranked.sort(key=lambda item: (-item["mentions_12w"], _fold(item["term"])))
    return ranked


def build_knowledge_payload(
    *,
    catalog: dict,
    directory: dict,
    signals: list[ArticleSignal],
    previous: dict | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    previous = previous or {}
    baselines = catalog["entity_baselines"]
    companies, excluded_companies = rank_entities(
        _order_by_ids(list(directory["companies"]), list(baselines["companies"])),
        signals,
        previous_ranks=_previous_ranks(previous, "companies"),
        now=now,
    )
    people, excluded_people = rank_entities(
        _order_by_ids(list(directory["people"]), list(baselines["people"])),
        signals,
        previous_ranks=_previous_ranks(previous, "people"),
        now=now,
    )
    tools = rank_tools(
        list(catalog["tools"]),
        signals,
        category_evidence=dict(catalog["tool_category_evidence"]),
        previous_ranks=_previous_ranks(previous, "tools"),
        previous_category_ranks=_previous_category_ranks(previous),
    )
    prompts = rank_prompts(
        list(catalog["prompts"]),
        signals,
        previous_ranks=_previous_ranks(previous, "prompts"),
    )
    return {
        "schema_version": 2,
        "edition": f"{now.isocalendar().year}-W{now.isocalendar().week:02d}",
        "updated_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "signal_window_days": 84,
        "signal_articles": len(signals),
        "methodology_url": "https://ptia.pt/metodologia-indice/",
        "disclaimer": (
            "Índice editorial PTIA, não uma medição absoluta de influência. "
            "O estado da entidade é verificado antes da avaliação; registos sem duas fontes "
            "independentes e recentes ficam na watchlist, sem posição publicada, e entidades "
            "inativas passam para o arquivo."
        ),
        "companies": companies,
        "people": people,
        "entity_archive": {
            "companies": excluded_companies,
            "people": excluded_people,
        },
        "verification_summary": {
            "eligible": sum(item["eligibility"] == "eligible" for item in [*companies, *people]),
            "provisional": sum(
                item["eligibility"] == "provisional" for item in [*companies, *people]
            ),
            "excluded": len(excluded_companies) + len(excluded_people),
        },
        "tools": tools,
        "prompts": prompts,
        "glossary": rank_glossary(
            list(catalog["glossary"]),
            signals,
            english_terms=dict(catalog.get("glossary_english") or {}),
        ),
    }


def _json_script(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _movement_label(value: int | None) -> str:
    if value is None:
        return "Nova edição"
    if value > 0:
        return f"Subiu {value}"
    if value < 0:
        return f"Desceu {abs(value)}"
    return "Sem alteração"


def _change_badge(change: dict | None) -> str:
    change = change or {"kind": "baseline", "label": "Nova edição"}
    if change["kind"] == "same":
        return ""
    return (
        f'<span class="movement-badge movement-{html.escape(str(change["kind"]))}">'
        f"{html.escape(str(change['label']))}</span>"
    )


def _change_suffix(change: dict | None) -> str:
    if not change or change.get("kind") == "same":
        return ""
    return f" · {html.escape(str(change['label']))}"


def _page_shell(title: str, description: str, canonical: str, body: str, schema: dict) -> str:
    return f"""<!doctype html>
<html lang="pt-PT" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · PTIA.pt</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="canonical" href="{html.escape(canonical)}">
  <meta property="og:title" content="{html.escape(title)} · PTIA.pt">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:url" content="{html.escape(canonical)}">
  <meta property="og:type" content="website">
  <link rel="icon" type="image/svg+xml" href="/favicon.svg?v=20260608-ptia">
  <link rel="icon" type="image/png" href="/favicon.png?v=20260608-ptia">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20260608-ptia">
  <link rel="stylesheet" href="/styles.css?v=20260608-2">
  <link rel="stylesheet" href="/assets/knowledge.css?v=20260713-1">
  <link rel="stylesheet" href="/assets/resources.css?v=20260713-3">
  <script>
    try {{ document.documentElement.dataset.theme = localStorage.getItem("ptia-theme") === "dark" ? "dark" : "light"; }} catch (_) {{}}
  </script>
  <script type="application/ld+json">{_json_script(schema)}</script>
</head>
<body>
  <a class="skip-link" href="#conteudo">Saltar para o conteúdo</a>
  <header class="knowledge-header">
    <div class="wrap knowledge-nav">
      <a class="brand-logo-link" href="/" aria-label="PTIA.pt"><img class="brand-logo" src="/assets/ptia-wordmark-navy-transparent.png" alt="PTIA"></a>
      <nav aria-label="Recursos PTIA">
        <a href="/recursos/">Hub</a>
        <a href="/ia-em-portugal/">Índice Portugal</a>
        <a href="/ferramentas/">Ferramentas</a>
        <a href="/prompts/">Prompts</a>
        <a href="/glossario/">Glossário</a>
      </nav>
      <a class="knowledge-back" href="/">Hoje</a>
    </div>
  </header>
{body}
  <footer class="knowledge-footer">
    <div class="wrap"><p>PTIA.pt · Inteligência Artificial, lida a partir de Portugal.</p><a href="/metodologia-indice/">Metodologia e correções</a></div>
  </footer>
  <script src="/assets/knowledge.js?v=20260608-2" defer></script>
  <script src="/assets/resources.js?v=20260713-2" defer></script>
  <script src="/analytics.js?v=20260713-2"></script>
</body>
</html>
"""


def _hero(kicker: str, title: str, lead: str, payload: dict) -> str:
    return f"""
  <main id="conteudo">
    <section class="knowledge-hero">
      <div class="wrap knowledge-hero-grid">
        <div>
          <p class="knowledge-kicker">{html.escape(kicker)}</p>
          <h1>{html.escape(title)}</h1>
          <p class="knowledge-lead">{html.escape(lead)}</p>
        </div>
        <dl class="edition-panel">
          <div><dt>Edição</dt><dd>{html.escape(payload["edition"])}</dd></div>
          <div><dt>Janela</dt><dd>{payload["signal_window_days"]} dias</dd></div>
          <div><dt>Artigos analisados</dt><dd>{payload["signal_articles"]}</dd></div>
          <div><dt>Atualizado</dt><dd>{payload["updated_at"][:10]}</dd></div>
        </dl>
      </div>
    </section>
"""


def _rank_list(items: list[dict], *, kind: str) -> str:
    cards = []
    for item in items[:10]:
        subtitle = item.get("tagline") if kind == "company" else item.get("role")
        description = item.get("description") if kind == "company" else item.get("bio")
        evidence = item.get("evidence") or []
        verification_sources = (item.get("verification") or {}).get("sources") or []
        verified_sources = min(2, len(_source_hosts(verification_sources)))
        eligible = item.get("eligibility") == "eligible" and item.get("rank")
        change_badge = _change_badge(item.get("ranking_change")) if eligible else ""
        source_items = [
            (source.get("label") or "Fonte", source.get("url"))
            for source in verification_sources[:2]
            if source.get("url")
        ]
        if evidence and not source_items:
            source_items.append(("Evidência PTIA recente", evidence[0]["url"]))
        evidence_markup = " · ".join(
            f'<a href="{html.escape(url)}" rel="noopener">{html.escape(str(label))}</a>'
            for label, url in source_items
        )
        evidence_markup = evidence_markup or "<span>Sem fontes independentes validadas</span>"
        position = f"{int(item['rank']):02d}" if eligible else "—"
        state_label = "No ranking" if eligible else "Watchlist · sem posição"
        signal = (
            html.escape(str(item.get("score_band") or "Posição publicada"))
            if eligible
            else f"{verified_sources}/2 fontes"
        )
        signal_note = (
            "Gate cumprido · posição comparável"
            if eligible
            else "Entra no ranking quando cumprir o gate"
        )
        cards.append(
            f"""
        <article class="rank-row rank-{"eligible" if eligible else "watchlist"}">
          <div class="rank-number">{position}</div>
          <div class="rank-copy">
            <p class="rank-meta">{html.escape(str(item.get("category") or ""))} <span class="status-pill status-{"eligible" if eligible else "watchlist"}">{state_label}</span></p>
            <h3>{html.escape(item["name"])}</h3>
            <p class="rank-subtitle">{html.escape(str(subtitle or ""))}</p>
            <p>{html.escape(str(description or ""))}</p>
            <p class="rank-explanation">{html.escape(str(item.get("explanation") or ""))}</p>
          </div>
          <div class="rank-signal">
            <strong>{signal}</strong>
            <span>{signal_note}</span>{change_badge}
            <span class="source-links">{evidence_markup}</span>
          </div>
        </article>
"""
        )
    return "".join(cards)


def render_portugal_page(payload: dict) -> str:
    eligible_companies = [
        item for item in payload["companies"] if item.get("eligibility") == "eligible"
    ]
    eligible_people = [item for item in payload["people"] if item.get("eligibility") == "eligible"]
    body = _hero(
        "Índice PTIA · Portugal",
        "Quem está a construir a IA em Portugal.",
        "Posições só para perfis com duas fontes independentes e recentes. Os restantes permanecem numa watchlist sem número até cumprirem esse gate.",
        payload,
    )
    company_title = (
        "Top de impacto empresarial"
        if eligible_companies
        else "Watchlist empresarial · ainda sem posições"
    )
    people_title = (
        "Top de impacto público" if eligible_people else "Watchlist de pessoas · ainda sem posições"
    )
    body += f"""
    <section class="knowledge-section">
      <div class="wrap">
        <div class="index-gate-note">
          <strong>{len(eligible_companies) + len(eligible_people)} perfis no ranking</strong>
          <span>O número publicado exige estado ativo + 2 fontes independentes + verificação nos últimos {VERIFICATION_MAX_AGE_DAYS} dias.</span>
          <a href="/metodologia-indice/">Ver o gate →</a>
        </div>
        <div class="segmented-control" role="tablist" aria-label="Tipo de índice">
          <button class="active" type="button" role="tab" aria-selected="true" data-index-tab="companies">Empresas</button>
          <button type="button" role="tab" aria-selected="false" data-index-tab="people">Pessoas</button>
        </div>
        <div data-index-panel="companies">
          <header class="knowledge-section-head"><div><p>Empresas</p><h2>{company_title}</h2></div><p>Impacto 30% · momentum 25% · inovação 20% · relevância Portugal 15% · ecossistema 10%.</p></header>
          <div class="rank-list">{_rank_list(payload["companies"], kind="company")}</div>
        </div>
        <div data-index-panel="people" hidden>
          <header class="knowledge-section-head"><div><p>Pessoas</p><h2>{people_title}</h2></div><p>Trabalho publicado 35% · reconhecimento 25% · ecossistema 20% · atualidade 10% · Portugal 10%.</p></header>
          <div class="rank-list">{_rank_list(payload["people"], kind="person")}</div>
        </div>
      </div>
    </section>
    <section class="knowledge-note"><div class="wrap"><strong>Sem fontes, não há pódio.</strong><p>{html.escape(payload["disclaimer"])}</p><a href="/quem-e-quem">Consultar o diretório completo</a></div></section>
  </main>
"""
    item_lists = []
    if eligible_companies:
        item_lists.append(
            {
                "@type": "ItemList",
                "name": "Índice PTIA de empresas com impacto na IA em Portugal",
                "dateModified": payload["updated_at"],
                "itemListElement": [
                    {"@type": "ListItem", "position": item["rank"], "name": item["name"]}
                    for item in eligible_companies[:10]
                ],
            }
        )
    if eligible_people:
        item_lists.append(
            {
                "@type": "ItemList",
                "name": "Índice PTIA de pessoas com impacto público na IA em Portugal",
                "dateModified": payload["updated_at"],
                "itemListElement": [
                    {"@type": "ListItem", "position": item["rank"], "name": item["name"]}
                    for item in eligible_people[:10]
                ],
            }
        )
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Índice PTIA de IA em Portugal",
        "dateModified": payload["updated_at"],
        "mainEntity": item_lists,
    }
    return _page_shell(
        "Índice PTIA de IA em Portugal",
        "Empresas e pessoas com impacto público na inteligência artificial em Portugal, com um gate objetivo de fontes antes de qualquer posição.",
        "https://ptia.pt/ia-em-portugal/",
        body,
        schema,
    )


def render_tools_page(payload: dict) -> str:
    category_buttons = "".join(
        (
            f'<button type="button" data-tool-category="{key}" '
            f'class="{"active" if index == 0 else ""}">{label}</button>'
        )
        for index, (key, label) in enumerate(CATEGORY_LABELS.items())
    )
    panels = []
    published_lists = []
    for panel_index, (category, label) in enumerate(CATEGORY_LABELS.items()):
        ranked_tools = sorted(
            (tool for tool in payload["tools"] if category in tool.get("category_ranks", {})),
            key=lambda tool: tool["category_ranks"][category],
        )
        published = ranked_tools[0].get("category_publication_status", {}).get(category) == "ranked"
        category_tools = (
            ranked_tools
            if published
            else sorted(ranked_tools, key=lambda tool: _fold(tool["name"]))
        )
        rows = []
        for tool in category_tools:
            sources = tool["category_sources"][category]
            external_sources = len(
                _source_hosts(
                    source
                    for source in sources
                    if not str(source.get("url") or "").startswith("https://ptia.pt/")
                )
            )
            source_markup = " · ".join(
                f'<a href="{html.escape(source["url"])}" rel="noopener">{html.escape(source["label"])}</a>'
                for source in sources
            )
            breakdown = tool["category_breakdowns"][category]
            category_change = tool["category_movements"][category] if published else None
            score = int(round(float(tool["category_scores"][category])))
            position = f"{int(tool['category_ranks'][category]):02d}" if published else "—"
            signal_value = str(score) if published else f"{external_sources}/2"
            signal_label = (
                "Índice relativo em 100" if published else "Fontes externas · sem posição publicada"
            )
            movement = _change_badge(category_change) if published else ""
            rows.append(
                f"""
            <article class="tool-row">
              <div class="rank-number">{position}</div>
              <div>
                <p class="rank-meta">{html.escape(label)}</p>
                <h2>{html.escape(tool["name"])}</h2>
                <p>{html.escape(tool["description"])}</p>
                <dl class="tool-details"><div><dt>Melhor para</dt><dd>{html.escape(tool["best_for"])}</dd></div><div><dt>Atenção</dt><dd>{html.escape(tool["watch_out"])}</dd></div></dl>
                <div class="score-breakdown" aria-label="Componentes da avaliação"><span>Capacidade <strong>{int(round(float(breakdown["capability"])))}</strong></span><span>Adoção <strong>{int(round(float(breakdown["popularity"])))}</strong></span><span>Adequação <strong>{int(round(float(breakdown["task_fit"])))}</strong></span><span>Acesso <strong>{int(round(float(breakdown["access"])))}</strong></span></div>
              </div>
              <div class="rank-signal"><strong>{signal_value}</strong><span>{signal_label}</span><span>{external_sources} fonte{"s" if external_sources != 1 else ""} externa{"s" if external_sources != 1 else ""} · 4 critérios</span>{movement}<span class="source-links">{source_markup}</span><a href="{html.escape(tool["url"])}" rel="noopener">Site oficial</a></div>
            </article>
"""
            )
        evidence_count = int(
            ranked_tools[0].get("category_external_source_count", {}).get(category) or 0
        )
        if published:
            winner = ranked_tools[0]
            winner_score = int(round(float(winner["category_scores"][category])))
            feature_label = f"#01 para {label}"
            feature_name = winner["name"]
            feature_note = (
                f"{winner['best_for']} · índice {winner_score}/100 · "
                f"{evidence_count} fontes externas"
            )
            summary_text = (
                f"{len(ranked_tools)} ferramentas ordenadas especificamente para {label.lower()}"
            )
            published_lists.append(
                {
                    "@type": "ItemList",
                    "name": f"Top de ferramentas de IA para {label}",
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": tool["category_ranks"][category],
                            "name": tool["name"],
                            "url": tool["url"],
                        }
                        for tool in ranked_tools
                    ],
                }
            )
        else:
            feature_label = f"Shortlist para {label}"
            feature_name = "Posições ainda fechadas"
            feature_note = (
                f"{evidence_count}/2 fontes externas necessárias para publicar o ranking."
            )
            summary_text = (
                f"{len(category_tools)} ferramentas listadas alfabeticamente; "
                "a ordem interna não é publicada."
            )
        panels.append(
            f"""
        <div id="top-{category}" data-tool-panel="{category}"{" hidden" if panel_index else ""}>
          <div class="category-winner"><span>{html.escape(feature_label)}</span><strong>{html.escape(feature_name)}</strong><p>{html.escape(feature_note)}</p></div>
          <p class="filter-summary">{html.escape(summary_text)}</p>
          <div class="tool-list">{"".join(rows)}</div>
        </div>
"""
        )
    body = _hero(
        "Ferramentas · PTIA",
        "A ferramenta certa depende do trabalho.",
        "Comparações por finalidade com quatro critérios e fontes abertas. Quando faltam duas referências externas, mostramos uma shortlist sem posições.",
        payload,
    )
    body += f"""
    <section class="knowledge-section">
      <div class="wrap">
        <div class="criteria-strip">
          <span><strong>01</strong> capacidade</span>
          <span><strong>02</strong> adoção observável</span>
          <span><strong>03</strong> adequação ao trabalho</span>
          <span><strong>04</strong> acesso e valor</span>
        </div>
        <div class="knowledge-filters" role="tablist" aria-label="Escolher finalidade">{category_buttons}</div>
{"".join(panels)}
      </div>
    </section>
  </main>
"""
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Ferramentas de IA comparadas pela PTIA",
        "dateModified": payload["updated_at"],
        "mainEntity": published_lists,
    }
    return _page_shell(
        "Ferramentas de IA por caso de uso",
        "Ferramentas de IA por finalidade, com rankings publicados apenas quando existem critérios comuns e duas fontes externas.",
        "https://ptia.pt/ferramentas/",
        body,
        schema,
    )


def render_prompts_page(payload: dict) -> str:
    prompt_categories = sorted({prompt["category"] for prompt in payload["prompts"]})
    category_buttons = "".join(
        f'<button type="button" data-prompt-category="{html.escape(category)}">{html.escape(category.title())}</button>'
        for category in prompt_categories
    )
    top_rows = "".join(
        f'<a class="prompt-top-row" href="#prompt-{html.escape(prompt["id"])}"><span>{prompt["rank"]:02d}</span><strong>{html.escape(prompt["title"])}</strong><small>{html.escape(prompt["category"])}</small>{_change_badge(prompt.get("ranking_change"))}</a>'
        for prompt in payload["prompts"][:10]
    )
    cards = []
    for prompt in payload["prompts"]:
        cards.append(
            f"""
        <article class="prompt-card" id="prompt-{html.escape(prompt["id"])}" data-prompt-item data-prompt-category-value="{html.escape(prompt["category"])}" data-prompt-search="{html.escape(_fold(prompt["title"] + " " + prompt["purpose"] + " " + prompt["template"]))}">
          <header><span>{prompt["rank"]:02d}</span><div><p>{html.escape(prompt["category"])}</p><h2>{html.escape(prompt["title"])}</h2></div></header>
          <p>{html.escape(prompt["purpose"])}</p>
          <pre><code>{html.escape(prompt["template"])}</code></pre>
          <footer><span>Curadoria editorial · utilização ainda não medida</span><button type="button" data-copy-prompt>Copiar prompt</button></footer>
        </article>
"""
        )
    prompt_library = [
        {
            "id": prompt["id"],
            "title": prompt["title"],
            "category": prompt["category"],
            "purpose": prompt["purpose"],
            "template": prompt["template"],
            "search": _fold(
                " ".join(
                    [
                        prompt["title"],
                        prompt["category"],
                        prompt["purpose"],
                        " ".join(prompt.get("keywords") or []),
                    ]
                )
            ),
        }
        for prompt in payload["prompts"]
    ]
    body = _hero(
        "Prompts · PTIA",
        "Prompts úteis, testáveis e sem truques.",
        "Uma seleção editorial e uma biblioteca pesquisável de estruturas reutilizáveis, escritas e revistas pela PTIA.",
        payload,
    )
    body += f"""
    <section class="knowledge-section"><div class="wrap">
      <header class="knowledge-section-head"><div><p>Seleção editorial</p><h2>10 prompts escolhidos pela PTIA</h2></div><p>Ordenação editorial baseada na clareza, reutilização e utilidade do template. Não representa popularidade nem utilização real.</p></header>
      <div class="prompt-top-list">{top_rows}</div>
    </div></section>
    <section class="knowledge-section knowledge-section-alt"><div class="wrap">
      <header class="knowledge-section-head"><div><p>Biblioteca</p><h2>{len(payload["prompts"])} prompts para pesquisar</h2></div><p>O catálogo pode crescer sem tornar o Top 10 ilegível.</p></header>
      <label class="knowledge-search"><span>Pesquisar prompts</span><input type="search" data-prompt-search-input placeholder="Ex.: pesquisa, código, reunião"></label>
      <div class="knowledge-filters" aria-label="Filtrar prompts"><button class="active" type="button" data-prompt-category="all">Todos</button>{category_buttons}</div>
      <p class="filter-summary" data-prompt-summary>{len(payload["prompts"])} prompts</p>
      <div class="prompt-grid">{"".join(cards)}</div>
    </div></section>
    <section class="prompt-suggester-band"><div class="wrap">
      <div class="prompt-suggester" data-prompt-suggester>
        <div><p class="knowledge-kicker">Caso de uso livre</p><h2>Não encontras o que precisas?</h2><p>Descreve a tarefa. Primeiro procuramos um prompt PTIA testado; se não existir, propomos uma estrutura claramente identificada como não testada.</p></div>
        <form data-prompt-suggestion-form>
          <label for="prompt-use-case">O que queres fazer?</label>
          <textarea id="prompt-use-case" data-prompt-use-case rows="4" placeholder="Ex.: comparar duas propostas comerciais e identificar riscos escondidos"></textarea>
          <button type="submit">Encontrar ou sugerir prompt</button>
        </form>
        <article class="prompt-suggestion-result" data-prompt-suggestion-result hidden aria-live="polite">
          <p data-prompt-suggestion-status></p>
          <h3 data-prompt-suggestion-title></h3>
          <pre><code data-prompt-suggestion-code></code></pre>
          <button type="button" data-copy-suggestion>Copiar prompt</button>
        </article>
      </div>
      <script type="application/json" id="prompt-library-data">{_json_script(prompt_library)}</script>
    </div></section>
    <section class="knowledge-note"><div class="wrap"><strong>Mais descoberta, sem copiar comunidades.</strong><p>A PTIA acompanha fontes externas como o SnackPrompt para identificar padrões de procura, mas publica templates originais e contextualizados.</p><a href="https://snackprompt.com/" rel="noopener">Explorar SnackPrompt</a></div></section>
  </main>
"""
    schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Seleção editorial de prompts PTIA",
        "dateModified": payload["updated_at"],
        "itemListElement": [
            {"@type": "ListItem", "position": item["rank"], "name": item["title"]}
            for item in payload["prompts"]
        ],
    }
    return _page_shell(
        "Prompts selecionados pela PTIA",
        "Prompts úteis e reutilizáveis para pesquisa, estudo, coding, produtividade e decisão.",
        "https://ptia.pt/prompts/",
        body,
        schema,
    )


def render_glossary_page(payload: dict) -> str:
    alphabetical = sorted(payload["glossary"], key=lambda item: _fold(item["term"]))
    entries = []
    for term in alphabetical:
        related = " · ".join(term.get("related") or [])
        english_term = str(term.get("english_term") or "")
        english_markup = (
            f'<small lang="en">{html.escape(english_term)}</small>' if english_term else ""
        )
        entries.append(
            f"""
        <article class="glossary-entry" id="{html.escape(term["id"])}" data-knowledge-item data-search="{html.escape(_fold(term["term"] + " " + english_term + " " + term["definition"]))}">
          <header><div><h2>{html.escape(term["term"])}</h2>{english_markup}</div><span>{term["mentions_12w"]} menções PTIA · 12 semanas</span></header>
          <p>{html.escape(term["definition"])}</p>
          <p class="glossary-example"><strong>Exemplo:</strong> {html.escape(term["example"])}</p>
          <footer>Relacionados: {html.escape(related)}</footer>
        </article>
"""
        )
    body = _hero(
        "Glossário · PTIA",
        "Inteligência Artificial, sem nevoeiro.",
        "Definições em português claro, exemplos concretos e relações entre os principais conceitos técnicos e regulatórios.",
        payload,
    )
    body += f"""
    <section class="knowledge-section">
      <div class="wrap">
        <label class="knowledge-search"><span>Pesquisar termo</span><input type="search" data-knowledge-search placeholder="Ex.: RAG, agente, AI Act"></label>
        <p class="filter-summary" data-search-summary>{len(entries)} termos</p>
        <div class="glossary-grid">{"".join(entries)}</div>
      </div>
    </section>
  </main>
"""
    schema = {
        "@context": "https://schema.org",
        "@type": "DefinedTermSet",
        "name": "Glossário de Inteligência Artificial PTIA",
        "url": "https://ptia.pt/glossario/",
        "dateModified": payload["updated_at"],
        "hasDefinedTerm": [
            {
                "@type": "DefinedTerm",
                "name": item["term"],
                **({"alternateName": item["english_term"]} if item.get("english_term") else {}),
                "description": item["definition"],
                "url": f"https://ptia.pt/glossario/#{item['id']}",
            }
            for item in alphabetical
        ],
    }
    return _page_shell(
        "Glossário de Inteligência Artificial",
        "Glossário português de IA com definições claras, exemplos e termos relacionados.",
        "https://ptia.pt/glossario/",
        body,
        schema,
    )


def _open_source_radar_markup() -> str:
    return """
    <section class="knowledge-section knowledge-section-alt open-source-radar" id="radar-open-source">
      <div class="wrap">
        <article class="lobby-panel lobby-panel-wide">
          <header><div><span>Radar separado</span><h2>Open source para explorar</h2></div><a href="#radar-open-source-nota">Critérios ↓</a></header>
          <p class="panel-intro" id="radar-open-source-nota">Dez projetos com sinal público de comunidade e atividade recente. Não altera o índice PTIA nem equivale a uma recomendação, avaliação de qualidade ou validação de segurança.</p>
          <p class="radar-status" id="github-repos-updated" aria-live="polite">A carregar dados públicos do GitHub…</p>
          <ol class="lobby-ranked open-source-list" id="github-repos-list" aria-live="polite">
            <li class="radar-loading"><span>—</span><strong>A carregar o radar open source</strong><small>Atualização semanal</small></li>
          </ol>
        </article>
      </div>
    </section>
    <script>
      (() => {
        const list = document.getElementById("github-repos-list");
        const updated = document.getElementById("github-repos-updated");
        if (!list || !updated) return;
        const escapeHtml = (value) => String(value || "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
        const compactNumber = (value) => new Intl.NumberFormat("pt-PT", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
        const formatDate = (value) => {
          const date = new Date(value);
          return Number.isNaN(date.getTime()) ? "data indisponível" : new Intl.DateTimeFormat("pt-PT", { day: "numeric", month: "short", year: "numeric" }).format(date);
        };
        const githubUrl = (value) => {
          try {
            const url = new URL(String(value));
            return url.protocol === "https:" && url.hostname === "github.com" ? url.href : "";
          } catch (_) {
            return "";
          }
        };
        const repositoryRow = (repo, index) => {
          const url = githubUrl(repo.url);
          if (!url) return "";
          const rank = String(Number(repo.rank) || index + 1).padStart(2, "0");
          return '<li class="open-source-row"><span class="open-source-rank">' + rank + '</span><div class="open-source-copy"><a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' + escapeHtml(repo.name || "Repositório GitHub") + '</a><p>' + escapeHtml(repo.description || "Descrição indisponível.") + '</p></div><div class="open-source-meta"><span>' + escapeHtml(repo.language || "multi") + '</span><span>' + compactNumber(repo.stars) + ' stars</span><span>Atualizado ' + formatDate(repo.updated_at) + '</span></div></li>';
        };
        const unavailable = () => '<li class="radar-loading"><span>—</span><strong>Radar temporariamente indisponível</strong><small>Voltará a tentar na próxima atualização semanal.</small></li>';
        const loadRadar = async () => {
          try {
            const response = await fetch("/assets/github-ai-repos.json", { cache: "no-store" });
            if (!response.ok) throw new Error("GitHub radar indisponível");
            const payload = await response.json();
            const rows = (Array.isArray(payload.repos) ? payload.repos : []).map(repositoryRow).filter(Boolean);
            if (!rows.length) throw new Error("Sem repositórios válidos");
            list.innerHTML = rows.join("");
            updated.textContent = "Atualizado " + formatDate(payload.updated_at) + " · GitHub Search API · atividade nos últimos 45 dias";
          } catch (_) {
            updated.textContent = "Dados do GitHub indisponíveis nesta edição.";
            list.innerHTML = unavailable();
          }
        };
        loadRadar();
      })();
    </script>
"""


def render_resources_page(payload: dict) -> str:
    summary = payload.get("verification_summary") or {}
    archived_entities = [
        *payload.get("entity_archive", {}).get("companies", []),
        *payload.get("entity_archive", {}).get("people", []),
    ]
    categories: list[tuple[str, str, list[dict]]] = []
    for category, label in CATEGORY_LABELS.items():
        tools = sorted(
            (tool for tool in payload["tools"] if category in tool.get("category_ranks", {})),
            key=lambda tool: tool["category_ranks"][category],
        )
        if tools:
            categories.append((category, label, tools))
    published_category_count = sum(
        tools[0].get("category_publication_status", {}).get(category) == "ranked"
        for category, _, tools in categories
    )

    def source_count(sources: Iterable[dict]) -> int:
        return len(
            _source_hosts(
                source
                for source in sources
                if not str(source.get("url") or "").startswith("https://ptia.pt/")
            )
        )

    def tool_card(tool: dict, category: str, label: str, *, published: bool) -> str:
        rank = int(tool["category_ranks"][category])
        score = int(round(float(tool["category_scores"][category])))
        breakdown = tool["category_breakdowns"][category]
        sources = tool["category_sources"][category]
        external_sources = source_count(sources)
        position_label = f"#{rank:02d}" if published else "Sem posição"
        card_class = f"resources-rank-{rank}" if published else "resources-rank-watchlist"
        score_value = score if published else external_sources
        score_caption = "índice relativo<br>em 100" if published else "fontes externas<br>em 2"
        source_links = " · ".join(
            f'<a href="{html.escape(str(source["url"]))}" rel="noopener" data-resource-action="source_opened">{html.escape(str(source["label"]))}</a>'
            for source in sources
        )
        bars = "".join(
            f'<span><i>{html.escape(name)}</i><b><em style="--value:{int(round(float(breakdown[key])))}%"></em></b><strong>{int(round(float(breakdown[key])))}</strong></span>'
            for key, name in (
                ("capability", "Capacidade"),
                ("popularity", "Adoção"),
                ("task_fit", "Adequação"),
                ("access", "Acesso"),
            )
        )
        movement = _change_badge(tool["category_movements"][category]) if published else ""
        return f"""
          <article class="resources-rank-card {card_class}" data-resource-item="{html.escape(tool["id"])}">
            <div class="resources-rank-topline">
              <span class="resources-rank-number">{position_label}</span>{movement}
            </div>
            <p class="resources-rank-category">{html.escape(label)}</p>
            <h3>{html.escape(tool["name"])}</h3>
            <p class="resources-rank-fit">{html.escape(tool["best_for"])}</p>
            <div class="resources-rank-score">
              <strong>{score_value}</strong>
              <span>{score_caption}</span>
            </div>
            <details data-resource-explanation data-resource-label="{html.escape(tool["name"])}">
              <summary>Porque está aqui <span>+</span></summary>
              <div class="resources-rank-evidence">
                <p><b>Melhor para</b>{html.escape(tool["best_for"])}</p>
                <p><b>Atenção</b>{html.escape(tool["watch_out"])}</p>
                <div class="resources-score-bars" aria-label="Quatro componentes da avaliação">{bars}</div>
                <p class="resources-source-count">{external_sources} fonte{"s" if external_sources != 1 else ""} externa{"s" if external_sources != 1 else ""} · 4 critérios</p>
                <p class="resources-source-links">{source_links}</p>
              </div>
            </details>
          </article>
"""

    category_buttons = "".join(
        f'<button type="button" role="tab" aria-selected="{"true" if index == 0 else "false"}" class="{"active" if index == 0 else ""}" data-resource-category="{html.escape(category)}">{html.escape(label)}</button>'
        for index, (category, label, _) in enumerate(categories)
    )
    category_panels = []
    for index, (category, label, tools) in enumerate(categories):
        published = tools[0].get("category_publication_status", {}).get(category) == "ranked"
        displayed_tools = (
            tools[:3] if published else sorted(tools[:3], key=lambda tool: _fold(tool["name"]))
        )
        cards = "".join(
            tool_card(tool, category, label, published=published) for tool in displayed_tools
        )
        if published:
            panel_title = f"Top 3 para {label.lower()}"
            panel_note = "Posições calculadas com capacidade, adoção, adequação à tarefa e acesso."
            share_button = (
                f'<button type="button" class="resources-share-button" '
                f'data-resource-share data-share-title="Top 3 de IA para '
                f'{html.escape(label)} · PTIA" data-share-content="tools-'
                f'{html.escape(category)}">Partilhar este top</button>'
            )
        else:
            evidence_count = int(
                tools[0].get("category_external_source_count", {}).get(category) or 0
            )
            panel_title = f"Shortlist para {label.lower()}"
            panel_note = (
                f"Sem posições publicadas: {evidence_count}/2 fontes externas "
                "necessárias para abrir o ranking."
            )
            share_button = ""
        category_panels.append(
            f"""
        <div class="resources-ranking-panel" role="tabpanel" data-resource-category-panel="{html.escape(category)}"{" hidden" if index else ""}>
          <div class="resources-ranking-toolbar">
            <p><strong>{html.escape(panel_title)}</strong><span>{html.escape(panel_note)}</span></p>
            <div>{share_button}<a href="/ferramentas/#top-{html.escape(category)}" data-resource-action="full_comparison_opened">Abrir análise completa →</a></div>
          </div>
          <div class="resources-podium">{"".join(cards)}</div>
        </div>
"""
        )

    eligible_companies = [
        item for item in payload["companies"] if item.get("eligibility") == "eligible"
    ][:3]
    eligible_people = [item for item in payload["people"] if item.get("eligibility") == "eligible"][
        :3
    ]

    def entity_initials(name: str) -> str:
        words = [part for part in re.split(r"\s+", name.strip()) if part]
        return "".join(part[0] for part in words[:2]).upper() or "PT"

    def entity_source_links(item: dict, *, limit: int = 3) -> str:
        sources = list((item.get("verification") or {}).get("sources") or [])
        return " · ".join(
            f'<a href="{html.escape(str(source["url"]))}" rel="noopener" '
            f'data-resource-action="portugal_source_opened">'
            f"{html.escape(str(source.get('label') or 'Fonte'))}</a>"
            for source in sources[:limit]
            if str(source.get("url") or "").startswith("https://")
        )

    def entity_criterion_bars(item: dict, *, kind: str) -> str:
        criteria = (
            (
                ("impact", "Impacto"),
                ("momentum", "Momentum PTIA"),
                ("innovation", "Inovação"),
                ("portugal_relevance", "Relevância PT"),
                ("ecosystem_contribution", "Ecossistema"),
            )
            if kind == "company"
            else (
                ("work_output", "Trabalho"),
                ("recognition", "Reconhecimento"),
                ("ecosystem_contribution", "Ecossistema"),
                ("recency", "Atualidade PTIA"),
                ("portugal_relevance", "Ligação PT"),
            )
        )
        breakdown = item.get("score_breakdown") or {}
        return "".join(
            f'<span><i>{html.escape(label)}</i><b><em style="--value:'
            f'{int(round(float(breakdown.get(key) or 0)))}%"></em></b></span>'
            for key, label in criteria
        )

    def leader_board(kind: str, label: str, items: list[dict]) -> str:
        ranked = bool(items)
        if not items:
            source = payload["companies"] if kind == "company" else payload["people"]
            items = source[:3]
        featured = items[0]
        sources = list((featured.get("verification") or {}).get("sources") or [])
        source_total = len(_source_hosts(sources))
        score = int(round(float(featured.get("score") or 0)))
        subtitle = featured.get("tagline") if kind == "company" else featured.get("role")
        verified_at = str((featured.get("verification") or {}).get("verified_at") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified_at):
            year, month, day = verified_at.split("-")
            verified_at = f"{day}/{month}/{year}"
        featured_position = "01" if ranked else "—"
        featured_score = str(score) if ranked else "—"
        featured_sources = entity_source_links(featured)
        featured_reason = str(
            featured.get("assessment_reason")
            or featured.get("explanation")
            or "O perfil permanece em validação editorial."
        )
        rows = []
        for fallback_rank, item in enumerate(items[1:3], 2):
            row_sources = entity_source_links(item, limit=2)
            row_subtitle = item.get("tagline") if kind == "company" else item.get("role")
            row_score = int(round(float(item.get("score") or 0)))
            rank_value = int(item.get("rank") or fallback_rank) if ranked else fallback_rank
            rows.append(
                f"""
              <details class="resources-leader-row">
                <summary>
                  <span class="resources-leader-row-rank">{rank_value:02d}</span>
                  <span class="resources-leader-row-copy"><strong>{html.escape(item["name"])}</strong><small>{html.escape(str(row_subtitle or ""))}</small></span>
                  <span class="resources-leader-row-score"><strong>{row_score if ranked else "—"}</strong><small>{"/100" if ranked else "em validação"}</small></span>
                  <span class="resources-leader-row-open" aria-hidden="true">+</span>
                </summary>
                <div><p>{html.escape(str(item.get("assessment_reason") or item.get("explanation") or ""))}</p><p>{row_sources or "Fontes em validação"}</p></div>
              </details>
"""
            )
        return f"""
          <section class="resources-leader-board" aria-label="Top de {html.escape(label.lower())}">
            <header><div><p>Índice {"empresarial" if kind == "company" else "de influência"}</p><h3>{html.escape(label)}</h3></div><span>{"Top 3 verificado" if ranked else "Radar em validação"}</span></header>
            <article class="resources-leader-featured">
              <div class="resources-leader-featured-top"><span>#{featured_position}</span><small>{html.escape(str(featured.get("score_band") if ranked else "Fontes em validação"))}</small></div>
              <div class="resources-leader-identity"><span aria-hidden="true">{html.escape(entity_initials(str(featured["name"])))}</span><div><p>{"Empresa" if kind == "company" else "Pessoa"} que lidera</p><h3>{html.escape(featured["name"])}</h3><small>{html.escape(str(subtitle or ""))}</small></div></div>
              <div class="resources-leader-stats">
                <span><strong>{featured_score}</strong><small>índice /100</small></span>
                <span><strong>{source_total}</strong><small>fontes externas</small></span>
                <span><strong>5</strong><small>critérios ponderados</small></span>
              </div>
              <details class="resources-leader-evidence">
                <summary>Ver critérios e fontes <span aria-hidden="true">+</span></summary>
                <div><p>{html.escape(featured_reason)}</p><div class="resources-leader-bars">{entity_criterion_bars(featured, kind=kind)}</div><p class="resources-leader-sources">{featured_sources or "Fontes em validação"}</p><small>Estado verificado em {html.escape(verified_at or "revisão")}</small></div>
              </details>
            </article>
            <div class="resources-leader-list">{"".join(rows)}</div>
          </section>
"""

    has_published_portugal_ranking = bool(eligible_companies or eligible_people)
    company_board = leader_board("company", "Empresas", eligible_companies)
    people_board = leader_board("person", "Pessoas", eligible_people)
    if has_published_portugal_ranking:
        portugal_title = "Quem está a transformar IA em impacto real."
        portugal_intro = (
            "Os artigos da PTIA medem momentum; fontes públicas independentes validam "
            "estado e impacto. Só depois entram os critérios ponderados e a posição."
        )
    else:
        portugal_title = "Os nomes estão escolhidos. As posições ainda não."
        portugal_intro = (
            "O índice abre quando cada perfil ativo tiver duas fontes independentes e "
            "recentes. Até lá mostramos o radar, sem transformar hipótese em ranking."
        )

    archive = archived_entities[0] if archived_entities else None
    if archive:
        archive_sources = " · ".join(
            f'<a href="{html.escape(str(source["url"]))}" rel="noopener" data-resource-action="correction_source_opened">{html.escape(str(source.get("label") or "Fonte"))}</a>'
            for source in (archive.get("verification") or {}).get("sources", [])[:3]
            if source.get("url")
        )
        archive_markup = f"""
          <p class="resources-card-kicker">Correção verificável</p>
          <h3>{html.escape(archive["name"])} saiu do índice ativo.</h3>
          <p>{html.escape(str(archive.get("status_reason") or "O estado da entidade mudou e foi verificado."))}</p>
          <div class="resources-correction-sources">{archive_sources or "Fontes em revisão"}</div>
          <a href="/recursos/#arquivo-entidades" data-resource-action="archive_opened">Ver arquivo e decisão →</a>
"""
    else:
        archive_markup = """
          <p class="resources-card-kicker">Memória editorial</p>
          <h3>Sem alterações de estado nesta edição.</h3>
          <p>Quando uma entidade é adquirida, encerrada ou fica inativa, a mudança fica registada com fontes.</p>
          <a href="/metodologia-indice/" data-resource-action="methodology_opened">Ver regra editorial →</a>
"""

    prompt_cards = "".join(
        f"""
          <a class="resources-prompt-card" href="/prompts/#prompt-{html.escape(prompt["id"])}" data-resource-action="prompt_opened">
            <span>{prompt["rank"]:02d}</span>
            <div><small>{html.escape(prompt["category"])}</small><strong>{html.escape(prompt["title"])}</strong></div>
            <b>Usar →</b>
          </a>
"""
        for prompt in payload["prompts"][:3]
    )
    glossary_links = "".join(
        f'<a href="/glossario/#{html.escape(item["id"])}" data-resource-action="glossary_opened">{html.escape(item["term"])}</a>'
        for item in payload["glossary"][:8]
    )

    first_category, first_label, first_tools = categories[0]
    first_tool = first_tools[0]
    first_score = int(round(float(first_tool["category_scores"][first_category])))
    body = f"""
  <main id="conteudo" class="resources-v2" data-resources-engine="verified-weekly-v3">
    <section class="resources-v2-hero">
      <div class="wrap resources-v2-hero-grid">
        <div class="resources-v2-hero-copy">
          <p class="resources-v2-eyebrow"><span>Radar PTIA</span> Edição {html.escape(payload["edition"])} · atualização semanal</p>
          <h1>Os sinais de IA que valem o teu tempo.</h1>
          <p>Rankings por tarefa, líderes portugueses com fontes abertas e mudanças de estado que não desaparecem do histórico.</p>
          <div class="resources-v2-actions">
            <a href="#top-portugal" class="resources-primary-action" data-resource-action="ranking_started">Ver quem lidera</a>
            <button type="button" data-resource-share data-share-title="Radar PTIA · {html.escape(payload["edition"])}" data-share-content="weekly-edition">Partilhar edição</button>
          </div>
        </div>
        <aside class="resources-week-card" aria-label="Escolha da semana">
          <div class="resources-week-card-head"><span>Escolha da semana</span><b>{html.escape(first_label)}</b></div>
          <p class="resources-week-rank">#01</p>
          <h2>{html.escape(first_tool["name"])}</h2>
          <p>{html.escape(first_tool["best_for"])}</p>
          <div class="resources-week-score"><strong>{first_score}</strong><span>índice relativo<br>em 100</span></div>
          <a href="#top-ferramentas" data-resource-action="featured_ranking_opened">Ver porque lidera →</a>
        </aside>
      </div>
      <div class="wrap resources-v2-proof">
        <span><strong>{published_category_count}</strong> tops publicados</span>
        <span><strong>{len(categories) - published_category_count}</strong> shortlists em validação</span>
        <span><strong>{summary.get("eligible", 0)}</strong> perfis Portugal no ranking</span>
        <span><strong>{summary.get("excluded", 0)}</strong> alteração de estado auditável</span>
      </div>
    </section>

    <nav class="resources-jump-nav" aria-label="Navegação nesta página">
      <div class="wrap">
        <a href="#top-portugal">Portugal</a>
        <a href="#top-ferramentas">Ferramentas</a>
        <a href="#escolhas-editoriais">Prompts</a>
        <a href="#radar-open-source">Open source</a>
        <a href="/metodologia-indice/" data-resource-action="methodology_opened">Metodologia ↗</a>
      </div>
    </nav>

    <section class="resources-portugal-section" id="top-portugal">
      <div class="wrap">
        <header class="resources-v2-section-head">
          <div><p>Índice Portugal · {html.escape(payload["edition"])}</p><h2>{html.escape(portugal_title)}</h2></div>
          <p>{html.escape(portugal_intro)}</p>
        </header>
        <div class="resources-leader-grid">{company_board}{people_board}</div>
        <div class="resources-portugal-footer">
          <p><strong>Como é calculado:</strong> impacto/trabalho, momentum/atualidade, inovação/reconhecimento, relevância para Portugal e contribuição para o ecossistema. Menções nos artigos PTIA contam apenas para momentum — nunca validam sozinhas um perfil.</p>
          <a href="/ia-em-portugal/" data-resource-action="portugal_ranking_opened">Abrir ranking, pesos e fontes →</a>
        </div>
      </div>
    </section>

    <section class="resources-ranking-section" id="top-ferramentas">
      <div class="wrap">
        <header class="resources-v2-section-head">
          <div><p>Rankings comparáveis</p><h2>Escolhe o trabalho.<br>Nós mostramos o top.</h2></div>
          <p>Não existe “a melhor IA” em abstrato. Cada lista usa o mesmo quadro de quatro critérios e muda quando a evidência muda.</p>
        </header>
        <div class="resources-category-tabs" role="tablist" aria-label="Escolher finalidade">{category_buttons}</div>
{"".join(category_panels)}
        <div class="resources-method-strip">
          <p><span>01</span><strong>Capacidade</strong><small>Benchmarks e funções</small></p>
          <p><span>02</span><strong>Adoção</strong><small>Uso observável</small></p>
          <p><span>03</span><strong>Adequação</strong><small>Fit com a tarefa</small></p>
          <p><span>04</span><strong>Acesso</strong><small>Disponibilidade e valor</small></p>
          <a href="/metodologia-indice/" data-resource-action="methodology_opened">Ver pesos e fontes →</a>
        </div>
      </div>
    </section>

    <section class="resources-editorial-section" id="escolhas-editoriais">
      <div class="wrap resources-editorial-grid">
        <article class="resources-editorial-card">
          <header><div><p class="resources-card-kicker">Seleção editorial</p><h2>3 prompts para fazer melhor trabalho.</h2></div><a href="/prompts/" data-resource-action="prompt_library_opened">Ver biblioteca →</a></header>
          <p class="resources-editorial-note">Ordenados por clareza, reutilização e utilidade — não por uma popularidade que ainda não medimos.</p>
          <div class="resources-prompt-list">{prompt_cards}</div>
        </article>
        <article class="resources-correction-card" id="arquivo-entidades">{archive_markup}</article>
      </div>
    </section>

    <section class="resources-glossary-strip">
      <div class="wrap">
        <div><p>Sem nevoeiro</p><h2>IA em palavras normais.</h2></div>
        <div class="resources-glossary-links">{glossary_links}</div>
        <a href="/glossario/" data-resource-action="glossary_library_opened">Ver {len(payload["glossary"])} termos →</a>
      </div>
    </section>

    {_open_source_radar_markup().strip()}

    <section class="resources-v2-closing">
      <div class="wrap">
        <p>Uma posição sem explicação é só opinião.</p>
        <div><strong>Cada edição fica arquivada.</strong><span>Se um nome muda de estado, a página muda com ele — e mostra porquê.</span></div>
        <a href="/metodologia-indice/" data-resource-action="methodology_opened">Ler metodologia e correções →</a>
      </div>
    </section>
  </main>
"""
    item_lists = []
    for category, label, tools in categories:
        if tools[0].get("category_publication_status", {}).get(category) != "ranked":
            continue
        item_lists.append(
            {
                "@type": "ItemList",
                "name": f"Top de ferramentas de IA para {label}",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": tool["category_ranks"][category],
                        "name": tool["name"],
                        "url": tool["url"],
                    }
                    for tool in tools
                ],
            }
        )
    for key, label in (
        ("companies", "Empresas de IA com impacto em Portugal"),
        ("people", "Pessoas com impacto público na IA em Portugal"),
    ):
        eligible_items = [item for item in payload[key] if item.get("eligibility") == "eligible"]
        if not eligible_items:
            continue
        item_lists.append(
            {
                "@type": "ItemList",
                "name": label,
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": item["rank"],
                        "name": item["name"],
                        "url": "https://ptia.pt/ia-em-portugal/",
                    }
                    for item in eligible_items[:10]
                ],
            }
        )
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Rankings e recursos de Inteligência Artificial · PTIA",
        "url": "https://ptia.pt/recursos/",
        "dateModified": payload["updated_at"],
        "mainEntity": item_lists,
    }
    return _page_shell(
        "Rankings e recursos de Inteligência Artificial",
        "Rankings de ferramentas por tarefa, watchlist portuguesa com fontes, prompts úteis e radar open source, atualizados semanalmente.",
        "https://ptia.pt/recursos/",
        body,
        schema,
    )


def render_methodology_page(payload: dict) -> str:
    body = _hero(
        "Metodologia · PTIA",
        "Como o índice é calculado.",
        "As regras são públicas para que o resultado possa ser contestado, corrigido e melhorado.",
        payload,
    )
    body += """
    <section class="knowledge-section">
      <div class="wrap method-columns">
        <article><p>01</p><h2>Estado antes da pontuação</h2><p>O primeiro gate verifica se a entidade está ativa. Aquisição, insolvência, liquidação ou inatividade retiram-na imediatamente do índice ativo e colocam-na num arquivo auditável. Elegibilidade plena exige verificação recente e duas fontes independentes; os restantes registos são assinalados como provisórios.</p></article>
        <article><p>02</p><h2>Empresas</h2><p>A avaliação pondera impacto demonstrável (30%), momentum dos últimos 84 dias (25%), inovação (20%), relevância para Portugal (15%) e contribuição para o ecossistema (10%). Um registo provisório não pode aparecer como “líder verificado”.</p></article>
        <article><p>03</p><h2>Pessoas</h2><p>A avaliação pondera trabalho publicado ou executado (35%), reconhecimento independente (25%), contribuição para o ecossistema (20%), atualidade (10%) e ligação a Portugal (10%). Não mede valor pessoal nem popularidade em redes sociais.</p></article>
        <article><p>04</p><h2>Ferramentas</h2><p>Cada finalidade tem uma comparação própria: capacidade, adoção observável, adequação à tarefa e acesso/valor. A página mostra confiança e fontes. A posição global é apenas uma média de categorias, não um vencedor universal.</p></article>
        <article><p>05</p><h2>Prompts</h2><p>Os prompts são uma seleção editorial ordenada por clareza, reutilização e utilidade do template. Menções em artigos servem apenas de contexto. Enquanto não houver dados de utilização reais, não são apresentados como “trending” nem como ranking de popularidade.</p></article>
        <article><p>06</p><h2>Movimentos e versões</h2><p>Cada edição é comparada com a semana anterior e fica arquivada em dados estruturados. Repetir a geração na mesma semana mantém a base de comparação. Mudanças de estado têm prioridade sobre movimentos graduais de posição.</p></article>
        <article><p>07</p><h2>Correções</h2><p>Pedidos de correção devem indicar o registo, a afirmação contestada e uma fonte verificável. Uma edição inválida não substitui a última versão pública. Contacto: info@ptia.pt.</p></article>
      </div>
      <div class="method-sources">
        <h2>Fontes e limites</h2>
        <p>Fontes oficiais confirmam estado e funcionalidades; imprensa reputada e benchmarks independentes sustentam impacto e capacidade. Nenhuma fonte isolada determina a posição. A faixa e a confiança são publicadas para evitar falsa precisão.</p>
        <a href="https://www.vellum.ai/llm-leaderboard" rel="noopener">Vellum LLM Leaderboard</a>
        <a href="https://www.swebench.com/" rel="noopener">SWE-bench</a>
        <a href="/recursos/#arquivo-entidades">Arquivo de entidades</a>
      </div>
    </section>
  </main>
"""
    schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Metodologia do Índice PTIA",
        "url": "https://ptia.pt/metodologia-indice/",
        "dateModified": payload["updated_at"],
    }
    return _page_shell(
        "Metodologia do Índice PTIA",
        "Critérios, pesos, gates de elegibilidade, limites e processo de correções do Índice PTIA.",
        "https://ptia.pt/metodologia-indice/",
        body,
        schema,
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def build_knowledge_site(
    *,
    root: Path,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    catalog_path = root / "config" / "ptia_knowledge.json"
    directory_path = root / "site" / "assets" / "quem-e-quem.json"
    site_feed_path = root / "site" / "site-feed.json"
    latest_path = root / "site" / "assets" / "ptia-index" / "latest.json"
    catalog = _load_json(catalog_path)
    directory = _load_json(directory_path)
    validate_catalog(catalog, directory)
    signals = load_article_signals(site_feed_path, now=now)
    current_edition = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    previous = _load_json(latest_path) if latest_path.exists() else {}
    if previous.get("edition") == current_edition:
        archive_dir = root / "site" / "assets" / "ptia-index" / "archive"
        older_editions = sorted(
            (path for path in archive_dir.glob("*.json") if path.stem != current_edition),
            reverse=True,
        )
        previous = _load_json(older_editions[0]) if older_editions else {}
    payload = build_knowledge_payload(
        catalog=catalog,
        directory=directory,
        signals=signals,
        previous=previous,
        now=now,
    )

    site_dir = root / "site"
    pages = {
        "recursos/index.html": render_resources_page(payload),
        "ia-em-portugal/index.html": render_portugal_page(payload),
        "ferramentas/index.html": render_tools_page(payload),
        "prompts/index.html": render_prompts_page(payload),
        "glossario/index.html": render_glossary_page(payload),
        "metodologia-indice/index.html": render_methodology_page(payload),
    }
    _write_json(site_dir / "assets" / "ptia-index" / "latest.json", payload)
    _write_json(
        site_dir / "assets" / "ptia-index" / "archive" / f"{payload['edition']}.json",
        payload,
    )
    for relative, content in pages.items():
        _write_text(site_dir / relative, content)
    return payload
