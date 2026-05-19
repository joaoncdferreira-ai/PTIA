from __future__ import annotations

import json
import os
import urllib.request

from ptia_engine.budget import estimate_cost_usd, estimate_tokens
from ptia_engine.dedupe import stable_hash
from ptia_engine.models import ProcessedItem, RawArticle

CLASSIFICATION_SCHEMA = {
    "name": "ptia_article_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "section": {
                "type": "string",
                "enum": [
                    "world_ai",
                    "portugal_ai",
                    "builders",
                    "business",
                    "regulation",
                    "tools",
                    "research",
                ],
            },
            "relevance_score": {"type": "integer", "minimum": 1, "maximum": 10},
            "hype_score": {"type": "integer", "minimum": 1, "maximum": 10},
            "portugal_relevance_score": {"type": "integer", "minimum": 1, "maximum": 10},
            "builder_relevance_score": {"type": "integer", "minimum": 1, "maximum": 10},
            "business_relevance_score": {"type": "integer", "minimum": 1, "maximum": 10},
            "should_cover": {"type": "boolean"},
            "reason": {"type": "string"},
            "risk_notes": {"type": "string"},
        },
        "required": [
            "section",
            "relevance_score",
            "hype_score",
            "portugal_relevance_score",
            "builder_relevance_score",
            "business_relevance_score",
            "should_cover",
            "reason",
            "risk_notes",
        ],
    },
}


SECTION_KEYWORDS = {
    "portugal_ai": ["portugal", "portuguese", "lisbon", "porto", "ama", "cnpd"],
    "regulation": ["ai act", "regulation", "compliance", "privacy", "gdpr", "european commission"],
    "builders": ["developer", "agent", "agents", "api", "open source", "github", "framework"],
    "business": ["enterprise", "business", "company", "workplace", "productivity", "sales"],
    "research": ["research", "paper", "benchmark", "arxiv", "model evaluation"],
    "tools": ["tool", "workflow", "automation", "assistant"],
}

HYPE_KEYWORDS = ["revolutionary", "game-changing", "breakthrough", "world-first", "disrupt"]

SOURCE_DEFAULT_SECTION = {
    "openai_news": "world_ai",
    "google_ai_blog": "world_ai",
    "microsoft_ai_blog": "business",
    "nvidia_ai_blog": "builders",
    "hugging_face_blog": "builders",
    "mit_technology_review_ai": "world_ai",
    "venturebeat_ai": "world_ai",
    "the_decoder": "world_ai",
    "arxiv_cs_ai": "research",
    "arxiv_cs_lg": "research",
}

BUILDER_SOURCES = {"openai_news", "nvidia_ai_blog", "hugging_face_blog", "arxiv_cs_ai", "arxiv_cs_lg"}
BUSINESS_SOURCES = {"microsoft_ai_blog", "venturebeat_ai"}


def article_text(article: RawArticle) -> str:
    return f"{article.title_original}\n\n{article.raw_excerpt}".strip()


def classify_heuristic(
    article: RawArticle,
    model: str = "heuristic",
    learning_weights: dict | None = None,
) -> ProcessedItem:
    learning_weights = learning_weights or {}
    text = article_text(article).casefold()
    scores = {section: 1 for section in SECTION_KEYWORDS}
    for section, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[section] += 2
    section = SOURCE_DEFAULT_SECTION.get(article.source_id, "world_ai")
    if max(scores.values()) > 1:
        section = max(scores, key=scores.get)
    if article.source_id.startswith("arxiv"):
        section = "research"

    portugal_score = min(10, 1 + scores["portugal_ai"] + (3 if article.country == "PT" else 0))
    builder_score = min(
        10,
        1
        + scores["builders"]
        + (3 if article.source_id in BUILDER_SOURCES else 0)
        + (2 if article.source_id.startswith("arxiv") else 0),
    )
    business_score = min(10, 1 + scores["business"] + (2 if article.source_id in BUSINESS_SOURCES else 0))
    regulation_score = min(10, 1 + scores["regulation"])
    section_score = scores.get(section, 1)
    relevance = max(2, portugal_score, builder_score, business_score, regulation_score, section_score)
    if article.source_id in {"openai_news", "google_ai_blog", "microsoft_ai_blog"}:
        relevance += 2
    source_boost = learning_weights.get("source_boosts", {}).get(article.source_id, {}).get("boost", 0)
    section_boost = learning_weights.get("section_boosts", {}).get(section, {}).get("boost", 0)
    relevance += int(source_boost) + int(section_boost)
    relevance = max(1, min(10, relevance))
    hype = min(10, 1 + sum(2 for keyword in HYPE_KEYWORDS if keyword in text))
    should_cover = (
        relevance >= 7
        or portugal_score >= 6
        or builder_score >= 7
        or regulation_score >= 7
    )
    reason = "Sinal editorial detectado por keywords; rever manualmente antes de publicar."
    if should_cover:
        reason = "Candidato util para curadoria PTIA; precisa de validacao editorial."

    return ProcessedItem(
        item_id=f"item_{stable_hash(article.article_id)}",
        article_id=article.article_id,
        source_id=article.source_id,
        source_name=article.source_name,
        title_original=article.title_original,
        source_url=article.url,
        section=section,
        relevance_score=relevance,
        hype_score=hype,
        portugal_relevance_score=portugal_score,
        builder_relevance_score=builder_score,
        business_relevance_score=business_score,
        should_cover=should_cover,
        reason=reason,
        risk_notes="Classificacao heuristica; usar AI ou revisao humana para decisao final.",
        ai_confidence=3,
        editorial_status="needs_review" if should_cover else "rejected",
        classifier_mode="heuristic",
        model=model,
        estimated_cost_usd=0.0,
    )


def build_classification_prompt(article: RawArticle) -> str:
    return f"""Es o editor-chefe do PTIA, uma publicacao portuguesa sobre Inteligencia Artificial.

A tua funcao e avaliar se este artigo merece ser coberto para uma audiencia portuguesa interessada em IA, negocios, tecnologia, produtividade, regulacao e builders.

Nao procures hype. Da prioridade a utilidade, impacto real, clareza e relevancia para Portugal.

Artigo:
Titulo: {article.title_original}
Fonte: {article.source_name}
URL: {article.url}
Resumo/Texto: {article.raw_excerpt}
"""


def estimate_openai_classification_cost(article: RawArticle, model: str, max_output_tokens: int) -> float:
    prompt = build_classification_prompt(article)
    return estimate_cost_usd(model, estimate_tokens(prompt), max_output_tokens)


def classify_openai(
    article: RawArticle,
    model: str = "gpt-4.1-mini",
    max_output_tokens: int = 500,
) -> ProcessedItem:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    prompt = build_classification_prompt(article)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Responde apenas com JSON valido no schema pedido.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_schema", "json_schema": CLASSIFICATION_SCHEMA},
        "max_tokens": max_output_tokens,
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        response_body = json.loads(response.read().decode("utf-8"))

    message = response_body["choices"][0]["message"]["content"]
    result = json.loads(message)
    usage = response_body.get("usage", {})
    input_tokens = int(usage.get("prompt_tokens", estimate_tokens(prompt)))
    output_tokens = int(usage.get("completion_tokens", max_output_tokens))
    estimated_cost = estimate_cost_usd(model, input_tokens, output_tokens)

    return ProcessedItem(
        item_id=f"item_{stable_hash(article.article_id)}",
        article_id=article.article_id,
        source_id=article.source_id,
        source_name=article.source_name,
        title_original=article.title_original,
        source_url=article.url,
        section=result["section"],
        relevance_score=int(result["relevance_score"]),
        hype_score=int(result["hype_score"]),
        portugal_relevance_score=int(result["portugal_relevance_score"]),
        builder_relevance_score=int(result["builder_relevance_score"]),
        business_relevance_score=int(result["business_relevance_score"]),
        should_cover=bool(result["should_cover"]),
        reason=str(result["reason"]),
        risk_notes=str(result["risk_notes"]),
        ai_confidence=7,
        editorial_status="needs_review" if result["should_cover"] else "rejected",
        classifier_mode="openai",
        model=model,
        estimated_cost_usd=estimated_cost,
    )
