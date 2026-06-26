from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import json

from ptia_engine.models import FinalPost, utc_now_iso
from ptia_engine.storage import load_final_posts, write_jsonl
from ptia_engine.dedupe import stable_hash


LISBON_TZ = ZoneInfo("Europe/Lisbon")
RESOURCE_SOURCE_URL = "https://ptia.pt/recursos/"
DEFAULT_HASHTAGS = "#InteligenciaArtificial #IA #Portugal #PTIA #Recursos"
SERIES_KIND = "saturday_resources"


@dataclass(frozen=True, slots=True)
class SaturdayResourcePost:
    slot: str
    title: str
    body: str
    image_prompt: str
    visual_brief: str


def next_saturday(today: date | None = None) -> date:
    current = today or datetime.now(LISBON_TZ).date()
    days_until_saturday = (5 - current.weekday()) % 7
    return current + timedelta(days=days_until_saturday)


def load_resource_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_saturday_resource_posts(index: dict[str, Any], *, target_date: date) -> list[SaturdayResourcePost]:
    people = _top_items(index, "people", "name")
    companies = _top_items(index, "companies", "name")
    tools = _top_items(index, "tools", "name")
    prompts = _top_items(index, "prompts", "title")
    edition = str(index.get("edition", "") or _iso_week(target_date))

    return [
        _map_post(people, companies, tools, prompts, edition),
        _builders_post(people, companies, edition),
        _tools_post(tools, edition),
        _prompts_post(prompts, edition),
    ]


def upsert_saturday_resource_posts(
    posts_path: Path,
    index: dict[str, Any],
    *,
    target_date: date,
    created_at: str | None = None,
) -> list[FinalPost]:
    desired = build_saturday_resource_posts(index, target_date=target_date)
    existing = load_final_posts(posts_path)
    by_id = {post.post_id: post for post in existing}
    now = created_at or utc_now_iso()
    updated: list[FinalPost] = []

    for order, item in enumerate(desired):
        post_id = _post_id(target_date, item.slot)
        topic_id = _topic_id(target_date, item.slot)
        scheduled_time = _scheduled_time(target_date, item.slot)
        editor_notes = (
            f"[{now}] Série Recursos PTIA gerada automaticamente. "
            f"Peça {order + 1}/4. Visual brief:\n{item.visual_brief}"
        )
        post = by_id.get(post_id)
        if post is None:
            post = FinalPost(
                post_id=post_id,
                topic_id=topic_id,
                channel="linkedin",
                title=item.title,
                body=item.body,
                hashtags=DEFAULT_HASHTAGS,
                image_prompt=item.image_prompt,
                source_urls=[RESOURCE_SOURCE_URL],
                status="needs_final_review",
                scheduled_time=scheduled_time,
                image_status="needs_review",
                editor_notes=editor_notes,
                created_at=now,
            )
            existing.append(post)
        else:
            post.topic_id = topic_id
            post.channel = "linkedin"
            post.title = item.title
            post.body = item.body
            post.hashtags = DEFAULT_HASHTAGS
            post.image_prompt = item.image_prompt
            post.source_urls = [RESOURCE_SOURCE_URL]
            post.scheduled_time = scheduled_time
            post.image_status = post.image_status or "needs_review"
            if post.status not in {"approved_for_schedule", "scheduled", "published"}:
                post.status = "needs_final_review"
            post.editor_notes = editor_notes
        updated.append(post)

    write_jsonl(posts_path, existing)
    return updated


def _top_items(index: dict[str, Any], section: str, label_key: str, limit: int = 5) -> list[dict[str, Any]]:
    items = sorted(index.get(section, []) or [], key=lambda item: int(item.get("rank") or 9999))
    result = []
    for item in items[:limit]:
        result.append(
            {
                "rank": int(item.get("rank") or len(result) + 1),
                "label": str(item.get(label_key) or item.get("name") or item.get("title") or "").strip(),
                "score": float(item.get("score") or 0),
                "category": str(item.get("category") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "change": str((item.get("ranking_change") or {}).get("label") or "").strip(),
            }
        )
    return result


def _map_post(
    people: list[dict[str, Any]],
    companies: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    prompts: list[dict[str, Any]],
    edition: str,
) -> SaturdayResourcePost:
    body = f"""A IA em português precisa de mais do que notícias.

Precisa de uma camada de referência:
quem está a construir,
que empresas estão a escalar,
que ferramentas fazem sentido,
e que prompts ajudam a trabalhar melhor.

Esta semana, o PTIA organiza 20 recursos em quatro mapas:
pessoas, empresas, ferramentas e prompts.

Não é uma lista definitiva.
É uma leitura editorial, recalculada com sinais públicos, utilidade prática e relevância para quem trabalha com IA em Portugal.

Guardar este mapa é provavelmente mais útil do que guardar mais uma notícia.

Índice completo: https://ptia.pt/recursos/"""
    visual = "\n".join(
        [
            "Slide 1: O mapa PTIA dos recursos de IA em português",
            "Slide 2: Top 5 pessoas — " + "; ".join(_labels(people)),
            "Slide 3: Top 5 empresas — " + "; ".join(_labels(companies)),
            "Slide 4: Top 5 ferramentas — " + "; ".join(_labels(tools)),
            "Slide 5: Top 5 prompts — " + "; ".join(_labels(prompts)),
            "Slide 6: PTIA Recursos — Uma camada editorial para separar sinal de ruído.",
        ]
    )
    return SaturdayResourcePost(
        slot="mapa",
        title="O mapa PTIA dos recursos de IA em português",
        body=body,
        image_prompt=_image_prompt("O mapa PTIA dos recursos de IA em português", visual, edition),
        visual_brief=visual,
    )


def _builders_post(
    people: list[dict[str, Any]], companies: list[dict[str, Any]], edition: str
) -> SaturdayResourcePost:
    people_lines = _ranked_lines(people)
    company_lines = _ranked_lines(companies)
    body = f"""O ranking não é sobre fama.

É sobre sinal.

No ecossistema português de IA, há dois mapas que interessam acompanhar:
quem constrói conhecimento e quem transforma esse conhecimento em produto, receita e impacto.

Top pessoas PTIA:
{people_lines}

Top empresas PTIA:
{company_lines}

A leitura editorial é simples:
Portugal não parte do zero em IA. Parte de uma base real, mas ainda dispersa.

O trabalho agora é ligar pessoas, empresas, ferramentas e adoção.

Índice completo: https://ptia.pt/recursos/"""
    visual = "\n".join(
        [
            "Título: Quem está a construir IA em Portugal?",
            "Coluna esquerda: Pessoas — " + "; ".join(_labels(people)),
            "Coluna direita: Empresas — " + "; ".join(_labels(companies)),
            "Rodapé: PTIA Recursos · Índice editorial de IA em português",
        ]
    )
    return SaturdayResourcePost(
        slot="builders",
        title="Quem está a construir IA em Portugal?",
        body=body,
        image_prompt=_image_prompt("Quem está a construir IA em Portugal?", visual, edition),
        visual_brief=visual,
    )


def _tools_post(tools: list[dict[str, Any]], edition: str) -> SaturdayResourcePost:
    body = f"""A pergunta errada:
"Qual é a melhor ferramenta de IA?"

A pergunta útil:
"Que ferramenta faz sentido para este caso de uso?"

Top 5 ferramentas no índice PTIA desta semana:

1. {tools[0]["label"]} — trabalho generalista, escrita, análise e aprendizagem.
2. {tools[1]["label"]} — criação visual e produção rápida.
3. {tools[2]["label"]} — produto, design e colaboração.
4. {tools[3]["label"]} — estudo, síntese e trabalho ancorado em fontes.
5. {tools[4]["label"]} — pesquisa com referências visíveis.

A tese PTIA:
a maturidade em IA não vem de usar mais ferramentas.
Vem de escolher melhor, integrar melhor e medir melhor.

Índice completo: https://ptia.pt/recursos/"""
    visual = "\n".join(
        [
            "Título: O stack útil de IA",
            "01 ChatGPT — Assistente generalista",
            "02 Canva Magic Studio — Design e produção",
            "03 Figma AI — Produto e colaboração",
            "04 NotebookLM — Estudo com fontes",
            "05 Perplexity — Pesquisa verificável",
            "Rodapé: Não é hype. É adequação ao uso.",
        ]
    )
    return SaturdayResourcePost(
        slot="ferramentas",
        title="O stack útil de IA",
        body=body,
        image_prompt=_image_prompt("O stack útil de IA", visual, edition),
        visual_brief=visual,
    )


def _prompts_post(prompts: list[dict[str, Any]], edition: str) -> SaturdayResourcePost:
    body = f"""O prompt mais útil não é o mais complexo.

É o que melhora uma decisão.

Top 5 prompts PTIA desta semana:

{_ranked_lines(prompts)}

Esta é provavelmente a camada mais prática dos Recursos PTIA:
menos "faz-me um texto",
mais "ajuda-me a pensar melhor".

A utilidade real da IA começa quando o prompt obriga a fonte, critério, risco e clareza.

Índice completo: https://ptia.pt/recursos/"""
    visual = "\n".join(
        [
            "Título: 5 prompts para trabalhar melhor com IA",
            "01 Verificar uma alegação",
            "02 Transformar informação em decisão",
            "03 Rever código por risco",
            "04 Testar estratégia com contraditório",
            "05 Explicar em português claro",
            "Rodapé: PTIA Prompts · Utilidade antes de automação",
        ]
    )
    return SaturdayResourcePost(
        slot="prompts",
        title="5 prompts para trabalhar melhor com IA",
        body=body,
        image_prompt=_image_prompt("5 prompts para trabalhar melhor com IA", visual, edition),
        visual_brief=visual,
    )


def _image_prompt(title: str, visual_brief: str, edition: str) -> str:
    return f"""Cria uma imagem/carrossel editorial premium para LinkedIn sobre este tema: "{title}".

Objetivo: promover os Recursos PTIA com autoridade editorial, não como lista genérica.
Formato recomendado: documento/carrossel nativo LinkedIn, 1080x1080 por slide, fundo creme PTIA, azul PTIA #051A3B, tipografia editorial, composição limpa, muito espaço branco, hierarquia forte, sem laranja.

Texto visual a aplicar exatamente:
{visual_brief}

Estilo: editorial português, sofisticado, institucional sem parecer corporativo genérico, inspirado em jornal/revista de referência. Usar o wordmark PTIA oficial quando houver marca. Não usar robôs azuis, circuitos neon, hologramas, dashboards stock ou pseudo-tipografia ilegível.

Edição: {edition}. Resultado deve ser legível em mobile e pronto para revisão antes de ir para Buffer."""


def _labels(items: list[dict[str, Any]]) -> list[str]:
    return [f"{item['rank']:02d} {item['label']}" for item in items]


def _ranked_lines(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"{item['rank']}. {item['label']}" for item in items)


def _post_id(target_date: date, slot: str) -> str:
    return f"post_{stable_hash(f'{SERIES_KIND}:{target_date.isoformat()}:{slot}:linkedin', 18)}"


def _topic_id(target_date: date, slot: str) -> str:
    return f"topic_{stable_hash(f'{SERIES_KIND}:{target_date.isoformat()}:{slot}', 18)}"


def _scheduled_time(target_date: date, slot: str) -> str:
    times = {
        "mapa": time(9, 30),
        "builders": time(12, 30),
        "ferramentas": time(16, 30),
        "prompts": time(19, 0),
    }
    return datetime.combine(target_date, times[slot], tzinfo=LISBON_TZ).isoformat()


def _iso_week(target_date: date) -> str:
    year, week, _ = target_date.isocalendar()
    return f"{year}-W{week:02d}"
