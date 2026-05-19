from __future__ import annotations

from typing import Any

from ptia_engine.budget import estimate_tokens
from ptia_engine.dedupe import stable_hash
from ptia_engine.drafts import DEFAULT_HASHTAGS
from ptia_engine.llm_providers import (
    default_model_for_provider,
    estimate_provider_cost_usd,
    generate_json,
)
from ptia_engine.models import ContentDraft, ProcessedItem, RawArticle

AI_DRAFT_SCHEMA = {
    "name": "ptia_editorial_drafts",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title_pt": {"type": "string"},
            "summary_pt": {"type": "string"},
            "why_it_matters_pt": {"type": "string"},
            "portugal_angle_pt": {"type": "string"},
            "key_takeaways": {"type": "array", "items": {"type": "string"}},
            "linkedin_post": {"type": "string"},
            "instagram_caption": {"type": "string"},
            "carousel_slides": {
                "type": "array",
                "minItems": 5,
                "maxItems": 7,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "headline": {"type": "string"},
                        "text": {"type": "string"},
                        "visual": {"type": "string"},
                    },
                    "required": ["headline", "text", "visual"],
                },
            },
            "site_entry": {"type": "string"},
            "newsletter_item": {"type": "string"},
            "risk_notes": {"type": "string"},
        },
        "required": [
            "title_pt",
            "summary_pt",
            "why_it_matters_pt",
            "portugal_angle_pt",
            "key_takeaways",
            "linkedin_post",
            "instagram_caption",
            "carousel_slides",
            "site_entry",
            "newsletter_item",
            "risk_notes",
        ],
    },
}


def build_ai_draft_prompt(item: ProcessedItem, article: RawArticle) -> str:
    return f"""Es o editor do PTIA, uma publicacao portuguesa sobre Inteligencia Artificial.

Transforma esta noticia/artigo numa peca curta de curadoria em portugues europeu.

Regras:
- Nao copies texto da fonte.
- Nao traduzas o artigo inteiro.
- Nao inventes factos.
- Se a informacao for incerta, assinala.
- Sem hype.
- Distingue facto de interpretacao.
- Inclui sempre a fonte original.
- Escreve para profissionais, empresas e builders em Portugal.

Estrutura editorial interna:
1. Facto principal.
2. Leitura editorial PTIA.
3. Relevancia para Portugal.
4. Proxima accao ou pergunta util.
5. Fonte original.

Nao imprimas rotulos como "O que aconteceu", "Porque importa" ou "A leitura PTIA".

Item classificado:
Secao: {item.section}
Relevancia: {item.relevance_score}/10
Portugal: {item.portugal_relevance_score}/10
Builders: {item.builder_relevance_score}/10
Empresas: {item.business_relevance_score}/10
Notas de risco: {item.risk_notes}

Artigo:
Titulo: {article.title_original}
Fonte: {article.source_name}
URL: {article.url}
Publicado: {article.published_at}
Excerto: {article.raw_excerpt}
"""


def estimate_ai_draft_cost(
    item: ProcessedItem,
    article: RawArticle,
    model: str,
    max_output_tokens: int,
    provider: str = "openai",
) -> float:
    prompt = build_ai_draft_prompt(item, article)
    return estimate_provider_cost_usd(provider, model, estimate_tokens(prompt), max_output_tokens)


def generate_template_draft_payload(item: ProcessedItem, article: RawArticle) -> dict[str, Any]:
    source_line = f"Fonte original: {article.url}"
    portugal_angle = (
        "Vale acompanhar em Portugal se isto afectar produtividade, adopcao empresarial, regulacao ou equipas tecnicas."
    )
    if item.portugal_relevance_score >= 6:
        portugal_angle = "Ha um angulo claro para Portugal: empresas, decisores e builders devem avaliar impacto e aplicacao local."
    takeaways = [
        "Confirmar a fonte original antes de publicar.",
        "Explicar impacto pratico, nao apenas a novidade.",
        "Separar facto de interpretacao editorial PTIA.",
    ]
    return {
        "title_pt": item.title_original,
        "summary_pt": f"{article.raw_excerpt or item.reason} {source_line}".strip(),
        "why_it_matters_pt": "Importa se ajudar empresas, profissionais ou builders a decidir melhor sobre IA.",
        "portugal_angle_pt": portugal_angle,
        "key_takeaways": takeaways,
        "linkedin_post": "\n\n".join(
            [
                item.title_original,
                article.raw_excerpt or item.reason,
                "Pode trazer sinais uteis para quem acompanha IA em Portugal.",
                portugal_angle,
                source_line,
                "Que aplicacao pratica ves para isto no contexto portugues?",
            ]
        ),
        "instagram_caption": "\n".join(
            [
                item.title_original,
                "",
                article.raw_excerpt or item.reason,
                "",
                "- Rever a fonte original.",
                "- Procurar impacto pratico.",
                "- Avaliar relevancia local antes de publicar.",
                "",
                "Guarda para rever com calma.",
                source_line,
            ]
        ),
        "carousel_slides": [
            {"headline": "O sinal", "text": item.title_original[:120], "visual": "Titulo forte sobre fundo PTIA."},
            {"headline": "O que aconteceu", "text": (article.raw_excerpt or item.reason)[:140], "visual": "Bloco de noticia curto."},
            {"headline": "Porque importa", "text": "Separar novidade de impacto pratico para profissionais.", "visual": "Escala impacto vs ruido."},
            {"headline": "Quem deve olhar", "text": "Empresas, builders e decisores que usam IA no trabalho.", "visual": "Tres grupos em colunas."},
            {"headline": "Angulo Portugal", "text": portugal_angle[:140], "visual": "Mapa simples de Portugal com marcador."},
            {"headline": "Takeaway", "text": "Ler a fonte, validar claims e procurar uso real.", "visual": "Checklist editorial."},
        ],
        "site_entry": "\n\n".join(
            [
                f"## {item.title_original}",
                f"{article.raw_excerpt or item.reason}",
                "O PTIA destaca este tema pela sua possivel utilidade pratica.",
                portugal_angle,
                source_line,
            ]
        ),
        "newsletter_item": f"{item.title_original} - {item.reason} {source_line}",
        "risk_notes": "Draft template local. Requer edicao humana antes de publicar.",
    }


def generate_ai_draft_payload(
    item: ProcessedItem,
    article: RawArticle,
    provider: str = "openai",
    model: str | None = None,
    max_output_tokens: int = 1800,
) -> tuple[dict, float]:
    provider = provider.strip().casefold()
    if provider == "template":
        return generate_template_draft_payload(item, article), 0.0
    model = model or default_model_for_provider(provider)
    prompt = build_ai_draft_prompt(item, article)
    result = generate_json(
        provider=provider,
        prompt=prompt,
        schema=AI_DRAFT_SCHEMA,
        model=model,
        max_output_tokens=max_output_tokens,
        temperature=0.3,
        system_message="Responde apenas em JSON valido no schema pedido. Usa portugues europeu.",
    )
    return result.payload, result.estimated_cost_usd


def payload_to_drafts(item: ProcessedItem, payload: dict, model: str) -> list[ContentDraft]:
    base_id = stable_hash(f"{item.item_id}:ai:{model}")
    hashtags = DEFAULT_HASHTAGS.get(item.section, DEFAULT_HASHTAGS["world_ai"])
    slides = []
    for index, slide in enumerate(payload["carousel_slides"], start=1):
        slides.append(
            f"Slide {index}: {slide['headline']}\nTexto: {slide['text']}\nVisual: {slide['visual']}"
        )
    carousel_outline = "\n\n".join(slides)
    title = payload["title_pt"].strip() or item.title_original

    return [
        ContentDraft(
            draft_id=f"draft_{base_id}_ai_linkedin",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="linkedin",
            format="linkedin_post",
            title=title,
            body=payload["linkedin_post"],
            hashtags=hashtags,
            status="needs_edit",
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_ai_instagram_caption",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="instagram",
            format="instagram_caption",
            title=title,
            caption=payload["instagram_caption"],
            hashtags=hashtags,
            status="needs_edit",
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_ai_instagram_carousel",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="instagram",
            format="instagram_carousel",
            title=title,
            carousel_outline=carousel_outline,
            hashtags=hashtags,
            status="needs_edit",
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_ai_site",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="site",
            format="site_short_article",
            title=title,
            body=payload["site_entry"],
            status="needs_edit",
        ),
        ContentDraft(
            draft_id=f"draft_{base_id}_ai_newsletter",
            item_id=item.item_id,
            article_id=item.article_id,
            channel="newsletter",
            format="newsletter_item",
            title=title,
            body=payload["newsletter_item"],
            status="needs_edit",
        ),
    ]
