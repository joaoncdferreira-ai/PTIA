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
            raise KnowledgeValidationError(
                f"Os pesos de {category} devem somar 1."
            )
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


def _order_by_ids(records: list[dict], ordered_ids: list[str]) -> list[dict]:
    by_id = {str(record["id"]): record for record in records}
    return [by_id[item_id] for item_id in ordered_ids]


def rank_entities(
    records: list[dict],
    signals: list[ArticleSignal],
    *,
    previous_ranks: dict[str, int],
) -> list[dict]:
    ranked = []
    count = max(1, len(records) - 1)
    for position, record in enumerate(records):
        evidence = (
            []
            if str(record.get("category") or "").casefold() == "media"
            else _evidence(record, signals)
        )
        baseline = 100 - (position / count * 40)
        signal_score = min(100.0, len(evidence) * 25.0)
        score = round(baseline * 0.82 + signal_score * 0.18, 1)
        ranked.append(
            {
                **record,
                "baseline_position": position + 1,
                "score": score,
                "evidence": evidence,
                "confidence": "alta" if len(evidence) >= 3 else "média" if evidence else "editorial",
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["baseline_position"], item["name"]))
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
            item["category_sources"][category] = [
                {"component": component, "label": source["label"], "url": source["url"]}
                for component, source in components.items()
            ]

    ranked = list(ranked_by_id.values())
    for item in ranked:
        if item["category_scores"]:
            item["score"] = max(item["category_scores"].values())
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
    corpus = " ".join(signal.text for signal in signals)
    ranked = []
    for prompt in prompts:
        keywords = [_fold(value) for value in prompt.get("keywords", [])]
        topical_hits = sum(corpus.count(keyword) for keyword in keywords if keyword)
        topical_score = min(100.0, math.log1p(topical_hits) * 23)
        score = round(float(prompt["baseline_score"]) * 0.78 + topical_score * 0.22, 1)
        ranked.append({**prompt, "score": score, "topical_hits": topical_hits})
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
    companies = rank_entities(
        _order_by_ids(list(directory["companies"]), list(baselines["companies"])),
        signals,
        previous_ranks=_previous_ranks(previous, "companies"),
    )
    people = rank_entities(
        _order_by_ids(list(directory["people"]), list(baselines["people"])),
        signals,
        previous_ranks=_previous_ranks(previous, "people"),
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
        "schema_version": 1,
        "edition": f"{now.isocalendar().year}-W{now.isocalendar().week:02d}",
        "updated_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "signal_window_days": 84,
        "signal_articles": len(signals),
        "methodology_url": "https://ptia.pt/metodologia-indice/",
        "disclaimer": (
            "Índice editorial PTIA, não uma medição absoluta de influência. "
            "Combina uma base editorial versionada com sinais dos artigos PTIA dos últimos 84 dias."
        ),
        "companies": companies,
        "people": people,
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
        f'{html.escape(str(change["label"]))}</span>'
    )


def _change_suffix(change: dict | None) -> str:
    if not change or change.get("kind") == "same":
        return ""
    return f' · {html.escape(str(change["label"]))}'


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
  <link rel="stylesheet" href="/assets/knowledge.css?v=20260608-3">
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
  <script src="/analytics.js?v=20260606-1"></script>
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
        change_badge = _change_badge(item.get("ranking_change"))
        evidence_markup = (
            f'<a href="{html.escape(evidence[0]["url"])}">Evidência PTIA recente</a>'
            if evidence
            else "<span>Base editorial</span>"
        )
        cards.append(
            f"""
        <article class="rank-row">
          <div class="rank-number">{item["rank"]:02d}</div>
          <div class="rank-copy">
            <p class="rank-meta">{html.escape(str(item.get("category") or ""))}</p>
            <h3>{html.escape(item["name"])}</h3>
            <p class="rank-subtitle">{html.escape(str(subtitle or ""))}</p>
            <p>{html.escape(str(description or ""))}</p>
          </div>
          <div class="rank-signal">
            <strong>{item["score"]}</strong>
            <span>PTIA Score</span>{change_badge}
            {evidence_markup}
          </div>
        </article>
"""
        )
    return "".join(cards)


def render_portugal_page(payload: dict) -> str:
    body = _hero(
        "Índice PTIA · Portugal",
        "Quem está a construir a IA em Portugal.",
        "Uma leitura editorial, transparente e atualizada semanalmente sobre pessoas e empresas com impacto público no ecossistema português.",
        payload,
    )
    body += f"""
    <section class="knowledge-section">
      <div class="wrap">
        <div class="segmented-control" role="tablist" aria-label="Tipo de índice">
          <button class="active" type="button" role="tab" aria-selected="true" data-index-tab="companies">Empresas</button>
          <button type="button" role="tab" aria-selected="false" data-index-tab="people">Pessoas</button>
        </div>
        <div data-index-panel="companies">
          <header class="knowledge-section-head"><div><p>Empresas</p><h2>Top 10 impacto empresarial</h2></div><p>Base editorial + menções verificáveis na cobertura PTIA das últimas 12 semanas.</p></header>
          <div class="rank-list">{_rank_list(payload["companies"], kind="company")}</div>
        </div>
        <div data-index-panel="people" hidden>
          <header class="knowledge-section-head"><div><p>Pessoas</p><h2>Top 10 impacto público</h2></div><p>O índice mede sinal editorial observável; não mede valor pessoal nem profissional absoluto.</p></header>
          <div class="rank-list">{_rank_list(payload["people"], kind="person")}</div>
        </div>
      </div>
    </section>
    <section class="knowledge-note"><div class="wrap"><strong>Não é um concurso de popularidade.</strong><p>{html.escape(payload["disclaimer"])}</p><a href="/quem-e-quem">Consultar o diretório completo</a></div></section>
  </main>
"""
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "name": "Top 10 empresas com impacto na IA em Portugal",
                "dateModified": payload["updated_at"],
                "itemListElement": [
                    {"@type": "ListItem", "position": item["rank"], "name": item["name"]}
                    for item in payload["companies"][:10]
                ],
            },
            {
                "@type": "ItemList",
                "name": "Top 10 pessoas com impacto público na IA em Portugal",
                "dateModified": payload["updated_at"],
                "itemListElement": [
                    {"@type": "ListItem", "position": item["rank"], "name": item["name"]}
                    for item in payload["people"][:10]
                ],
            },
        ],
    }
    return _page_shell(
        "Índice PTIA de IA em Portugal",
        "Top 10 empresas e pessoas com impacto público na inteligência artificial em Portugal, com metodologia e atualização semanal.",
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
    for panel_index, (category, label) in enumerate(CATEGORY_LABELS.items()):
        category_tools = sorted(
            (
                tool
                for tool in payload["tools"]
                if category in tool.get("category_ranks", {})
            ),
            key=lambda tool: tool["category_ranks"][category],
        )
        rows = []
        for tool in category_tools:
            sources = tool["category_sources"][category]
            source_markup = " · ".join(
                f'<a href="{html.escape(source["url"])}" rel="noopener">{html.escape(source["label"])}</a>'
                for source in sources[:2]
            )
            breakdown = tool["category_breakdowns"][category]
            category_change = tool["category_movements"][category]
            rows.append(
                f"""
            <article class="tool-row">
              <div class="rank-number">{tool["category_ranks"][category]:02d}</div>
              <div>
                <p class="rank-meta">{html.escape(label)}</p>
                <h2>{html.escape(tool["name"])}</h2>
                <p>{html.escape(tool["description"])}</p>
                <dl class="tool-details"><div><dt>Melhor para</dt><dd>{html.escape(tool["best_for"])}</dd></div><div><dt>Atenção</dt><dd>{html.escape(tool["watch_out"])}</dd></div></dl>
                <div class="score-breakdown" aria-label="Componentes da pontuação"><span>Capacidade <strong>{breakdown["capability"]}</strong></span><span>Popularidade <strong>{breakdown["popularity"]}</strong></span><span>Adequação <strong>{breakdown["task_fit"]}</strong></span><span>Acesso <strong>{breakdown["access"]}</strong></span></div>
              </div>
              <div class="rank-signal"><strong>{tool["category_scores"][category]}</strong><span>Índice nesta categoria</span>{_change_badge(category_change)}<span class="source-links">{source_markup}</span><a href="{html.escape(tool["url"])}" rel="noopener">Site oficial</a></div>
            </article>
"""
            )
        winner = category_tools[0]
        panels.append(
            f"""
        <div data-tool-panel="{category}"{" hidden" if panel_index else ""}>
          <div class="category-winner"><span>Escolha PTIA para {html.escape(label)}</span><strong>{html.escape(winner["name"])}</strong><p>{html.escape(winner["best_for"])}</p></div>
          <p class="filter-summary">{len(category_tools)} ferramentas ordenadas especificamente para {html.escape(label.lower())}</p>
          <div class="tool-list">{"".join(rows)}</div>
        </div>
"""
        )
    body = _hero(
        "Ferramentas · PTIA",
        "A ferramenta certa depende do trabalho.",
        "Rankings independentes por finalidade, apoiados em benchmarks, adequação à tarefa, adoção observável e valor prático.",
        payload,
    )
    body += f"""
    <section class="knowledge-section">
      <div class="wrap">
        <div class="criteria-strip">
          <span><strong>01</strong> benchmarks e capacidade</span>
          <span><strong>02</strong> utilização e popularidade</span>
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
        "@type": "ItemList",
        "name": "Ferramentas de IA recomendadas pela PTIA",
        "dateModified": payload["updated_at"],
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": item["rank"],
                "name": item["name"],
                "url": item["url"],
            }
            for item in payload["tools"]
        ],
    }
    return _page_shell(
        "Ferramentas de IA por caso de uso",
        "Ferramentas de IA para coding, estudo, pesquisa, produtividade, design, vídeo e imagem, avaliadas pela PTIA.",
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
          <footer><span>Relevância semanal {prompt["score"]}{_change_suffix(prompt.get("ranking_change"))}</span><button type="button" data-copy-prompt>Copiar prompt</button></footer>
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
        "Um Top 10 editorial e uma biblioteca pesquisável de estruturas reutilizáveis, escritas e revistas pela PTIA.",
        payload,
    )
    body += f"""
    <section class="knowledge-section"><div class="wrap">
      <header class="knowledge-section-head"><div><p>Seleção semanal</p><h2>Top 10 prompts PTIA</h2></div><p>Ordenação baseada em qualidade do template, reutilização e relevância dos temas da cobertura recente.</p></header>
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
        "name": "Top 10 prompts PTIA",
        "dateModified": payload["updated_at"],
        "itemListElement": [
            {"@type": "ListItem", "position": item["rank"], "name": item["title"]}
            for item in payload["prompts"]
        ],
    }
    return _page_shell(
        "Top 10 prompts PTIA",
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
                **(
                    {"alternateName": item["english_term"]}
                    if item.get("english_term")
                    else {}
                ),
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


def render_resources_page(payload: dict) -> str:
    leading_company = payload["companies"][0]
    leading_person = payload["people"][0]
    leading_tool = payload["tools"][0]
    leading_prompt = payload["prompts"][0]
    category_winners = []
    for category, label in CATEGORY_LABELS.items():
        category_tools = [
            tool for tool in payload["tools"] if category in tool.get("category_ranks", {})
        ]
        winner = min(category_tools, key=lambda tool: tool["category_ranks"][category])
        category_winners.append((category, label, winner))
    def leader(
        *,
        label: str,
        name: str,
        score: float,
        href: str,
        action: str,
        change: dict | None,
    ) -> str:
        score_label = f"{score:.1f}".replace(".", ",")
        change_badge = _change_badge(change)
        return f"""
          <a class="weekly-leader" href="{href}">
            <span class="weekly-leader-label">{html.escape(label)}</span>
            <strong>{html.escape(name)}</strong>
            <span class="weekly-leader-score"><b>{score_label}</b> PTIA Score</span>
            <span class="weekly-leader-action">{html.escape(action)} →</span>{change_badge}
          </a>
"""

    leaders = "".join(
        (
            leader(
                label="Empresa #1",
                name=leading_company["name"],
                score=leading_company["score"],
                href="/ia-em-portugal/",
                action="Ver empresas",
                change=leading_company.get("ranking_change"),
            ),
            leader(
                label="Pessoa #1",
                name=leading_person["name"],
                score=leading_person["score"],
                href="/ia-em-portugal/",
                action="Ver pessoas",
                change=leading_person.get("ranking_change"),
            ),
            leader(
                label="Ferramenta #1",
                name=leading_tool["name"],
                score=leading_tool["score"],
                href="/ferramentas/",
                action="Comparar",
                change=leading_tool.get("ranking_change"),
            ),
            leader(
                label="Prompt #1",
                name=leading_prompt["title"],
                score=leading_prompt["score"],
                href="/prompts/",
                action="Abrir prompt",
                change=leading_prompt.get("ranking_change"),
            ),
        )
    )
    body = f"""
  <main id="conteudo">
    <section class="resources-hero">
      <div class="wrap">
        <div class="resources-hero-meta" aria-label="Dados da edição">
          <span>Edição <strong>{html.escape(payload["edition"])}</strong></span>
          <span><strong>{payload["signal_articles"]}</strong> artigos analisados</span>
          <span>Janela <strong>{payload["signal_window_days"]} dias</strong></span>
          <span>Atualizado <strong>{payload["updated_at"][:10]}</strong></span>
        </div>
        <div class="resources-hero-intro">
          <div>
            <p class="knowledge-kicker">Índice semanal · PTIA</p>
            <h1>Quem e o que lidera a IA esta semana.</h1>
          </div>
          <p>Os sinais mais fortes entre pessoas, empresas, ferramentas e prompts, avaliados com critérios públicos e atualização semanal.</p>
        </div>
        <div class="weekly-leaders" aria-label="Líderes da semana">{leaders}
        </div>
      </div>
    </section>
"""
    company_rows = "".join(
        f'<li><b>{str(item["score"]).replace(".", ",")}<small>PTIA</small></b><span>{item["rank"]:02d}</span><strong>{html.escape(item["name"])}</strong>{_change_badge(item.get("ranking_change"))}</li>'
        for item in payload["companies"][:3]
    )
    people_rows = "".join(
        f'<li><b>{str(item["score"]).replace(".", ",")}<small>PTIA</small></b><span>{item["rank"]:02d}</span><strong>{html.escape(item["name"])}</strong>{_change_badge(item.get("ranking_change"))}</li>'
        for item in payload["people"][:3]
    )
    winners = []
    for category, label, winner in category_winners:
        score_label = f'{winner["category_scores"][category]:.1f}'.replace(".", ",")
        winners.append(
            f'<li><b>{score_label}<small>PTIA</small></b><span>{html.escape(label)}</span><strong>{html.escape(winner["name"])}</strong>{_change_badge(winner["category_movements"][category])}</li>'
        )
    prompt_rows = "".join(
        f'<li><span>{item["rank"]:02d}</span><strong>{html.escape(item["title"])}</strong>{_change_badge(item.get("ranking_change"))}</li>'
        for item in payload["prompts"][: len(CATEGORY_LABELS)]
    )
    glossary_rows = "".join(
        f'<a href="/glossario/#{html.escape(item["id"])}">{html.escape(item["term"])}</a>'
        for item in payload["glossary"][:6]
    )
    body += f"""
    <section class="knowledge-section"><div class="wrap lobby-grid">
      <article class="lobby-panel lobby-panel-wide">
        <header><div><span>Índice Portugal</span><h2>Quem está a construir a IA em Portugal</h2></div><a href="/ia-em-portugal/">Ver índice completo →</a></header>
        <div class="lobby-split"><div><h3>Empresas</h3><ol class="lobby-entity-list">{company_rows}</ol></div><div><h3>Pessoas</h3><ol class="lobby-entity-list">{people_rows}</ol></div></div>
      </article>
      <article class="lobby-panel">
        <header><div><span>Ferramentas</span><h2>A melhor por finalidade</h2></div><a href="/ferramentas/">Comparar →</a></header>
        <ul class="winner-list">{"".join(winners)}</ul>
      </article>
      <article class="lobby-panel">
        <header><div><span>Prompts</span><h2>Top desta semana</h2></div><a href="/prompts/">Abrir biblioteca →</a></header>
        <ol class="lobby-ranked">{prompt_rows}</ol>
      </article>
      <article class="lobby-panel lobby-panel-wide glossary-preview">
        <header><div><span>Glossário</span><h2>IA explicada sem nevoeiro</h2></div><a href="/glossario/">Ver {len(payload["glossary"])} termos →</a></header>
        <div>{glossary_rows}</div>
      </article>
    </div></section>
    <section class="knowledge-note"><div class="wrap"><strong>Publicação com memória.</strong><p>Cada edição fica arquivada em dados estruturados. Alterações futuras podem ser explicadas, comparadas e corrigidas.</p><a href="/metodologia-indice/">Ler metodologia</a></div></section>
  </main>
"""
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Recursos PTIA",
        "url": "https://ptia.pt/recursos/",
        "dateModified": payload["updated_at"],
    }
    return _page_shell(
        "Recursos de Inteligência Artificial",
        "Índice português de IA, ferramentas, prompts e glossário da PTIA.",
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
        <article><p>01</p><h2>Pessoas e empresas</h2><p>82% da pontuação vem da base editorial versionada do diretório PTIA. 18% vem de menções únicas em artigos PTIA publicados nos últimos 84 dias. A janela reduz oscilações provocadas por uma única notícia.</p></article>
        <article><p>02</p><h2>Ferramentas</h2><p>Cada finalidade tem um ranking independente e pesos próprios. A pontuação agrega capacidade medida por benchmarks ou testes comparáveis, popularidade observável, adequação ao workflow e acesso/valor. Onde não existe benchmark independente, a página identifica a avaliação como editorial em vez de a apresentar como ciência.</p></article>
        <article><p>03</p><h2>Prompts</h2><p>78% corresponde a qualidade e reutilização do template; 22% à relevância dos seus temas na cobertura recente. “Trending PTIA” não significa tendência nacional.</p></article>
        <article><p>04</p><h2>Glossário</h2><p>As definições são versionadas. A automação altera a ordem de destaque com base nas menções, mas não reescreve silenciosamente conceitos técnicos.</p></article>
        <article><p>05</p><h2>Movimentos semanais</h2><p>Cada edição é comparada com o arquivo da semana anterior. As posições publicam os estados Entrou no Top, Subiu, Desceu ou Manteve. Repetir a geração na mesma semana mantém a mesma base de comparação.</p></article>
        <article><p>06</p><h2>Segurança editorial</h2><p>A execução valida quantidades mínimas, IDs, categorias, URLs e conteúdo. Uma edição inválida não substitui a última versão pública.</p></article>
        <article><p>07</p><h2>Correções</h2><p>Pedidos de correção devem indicar o registo, a afirmação contestada e uma fonte verificável. Contacto: info@ptia.pt.</p></article>
      </div>
      <div class="method-sources">
        <h2>Fontes externas de referência</h2>
        <p>Benchmarks ajudam a medir capacidade; páginas oficiais confirmam funcionalidades; sinais de adoção ajudam a medir utilidade no mercado. Nenhuma fonte isolada determina a posição.</p>
        <a href="https://www.vellum.ai/llm-leaderboard" rel="noopener">Vellum LLM Leaderboard</a>
        <a href="https://www.swebench.com/" rel="noopener">SWE-bench</a>
        <a href="https://snackprompt.com/" rel="noopener">SnackPrompt</a>
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
        "Critérios, pesos, limites e processo de correções do Índice PTIA.",
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
            (
                path
                for path in archive_dir.glob("*.json")
                if path.stem != current_edition
            ),
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
