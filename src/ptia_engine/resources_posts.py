from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ptia_engine.dedupe import stable_hash
from ptia_engine.models import FinalPost, utc_now_iso
from ptia_engine.storage import load_final_posts, write_jsonl


LISBON_TZ = ZoneInfo("Europe/Lisbon")
RESOURCE_SOURCE_URL = "https://ptia.pt/recursos/"
METHODOLOGY_SOURCE_URL = "https://ptia.pt/metodologia-indice/"
DEFAULT_HASHTAGS = "#InteligenciaArtificial #Portugal #PTIA #RadarIA"
SERIES_KIND = "saturday_resources"
SOCIAL_TOOL_CATEGORIES = (
    ("coding", "Código"),
    ("pesquisa", "Pesquisa"),
    ("automacoes", "Automações"),
)


@dataclass(frozen=True, slots=True)
class SaturdayResourcePost:
    slot: str
    title: str
    body: str
    image_prompt: str
    visual_brief: str
    source_urls: tuple[str, ...]


def next_saturday(today: date | None = None) -> date:
    current = today or datetime.now(LISBON_TZ).date()
    days_until_saturday = (5 - current.weekday()) % 7
    return current + timedelta(days=days_until_saturday)


def load_resource_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_saturday_resource_posts(
    index: dict[str, Any], *, target_date: date
) -> list[SaturdayResourcePost]:
    edition = str(index.get("edition", "") or _iso_week(target_date))
    return [_radar_post(index, edition)]


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
        editor_notes = (
            f"Série Radar PTIA gerada automaticamente para {target_date.isoformat()}. "
            f"Peça {order + 1}/{len(desired)}. Confirmar estados e fontes antes de aprovar. "
            f"Visual brief:\n{item.visual_brief}"
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
                source_urls=list(item.source_urls),
                status="needs_final_review",
                scheduled_time=_scheduled_time(target_date),
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
            post.source_urls = list(item.source_urls)
            post.scheduled_time = _scheduled_time(target_date)
            post.image_status = post.image_status or "needs_review"
            if post.status not in {"approved_for_schedule", "scheduled", "published"}:
                post.status = "needs_final_review"
            post.editor_notes = editor_notes
        updated.append(post)

    write_jsonl(posts_path, existing)
    return updated


def _radar_post(index: dict[str, Any], edition: str) -> SaturdayResourcePost:
    companies = _top_items(index, "companies", "name", limit=3)
    people = _top_items(index, "people", "name", limit=3)
    prompts = _top_items(index, "prompts", "title", limit=1)
    archived = [
        *index.get("entity_archive", {}).get("companies", []),
        *index.get("entity_archive", {}).get("people", []),
    ]
    tool_winners = _tool_winners(index)
    change = archived[0] if archived else None
    change_line = (
        f"{change['name']} sai do índice ativo: "
        f"{change.get('status_reason') or 'o estado da entidade mudou e foi verificado.'}"
        if change
        else "Nesta edição não há novas entidades retiradas do índice ativo."
    )
    company = companies[0] if companies else {"label": "Em verificação", "band": "Provisório"}
    person = people[0] if people else {"label": "Em verificação", "band": "Provisório"}
    prompt = prompts[0]["label"] if prompts else "Biblioteca PTIA"
    tool_lines = (
        "\n".join(
            f"• {label}: {tool['name']} — confiança {tool['confidence']}"
            for label, tool in tool_winners
        )
        or "• Comparações por finalidade em atualização"
    )

    body = f"""Um ranking só é útil se também souber retirar nomes.

No Radar PTIA desta semana:
• Empresa em destaque: {company["label"]} — {company["band"]}
• Pessoa em destaque: {person["label"]} — {person["band"]}
{tool_lines}
• Prompt selecionado: {prompt}

A mudança que importa:
{change_line}

É por isto que o novo índice começa pelo estado da entidade — ativa, adquirida, insolvente, liquidada ou inativa — e só depois calcula impacto.

Duas fontes independentes dão elegibilidade plena. Sem verificação recente, a entrada aparece como provisória. As ferramentas são comparadas por caso de uso. Os prompts são curadoria editorial, não uma falsa tendência semanal.

O que devemos verificar na próxima edição?

Metodologia e fontes: {METHODOLOGY_SOURCE_URL}
Radar completo: {RESOURCE_SOURCE_URL}"""

    visual = "\n".join(
        [
            "Slide 1: Radar PTIA — o que mudou e porquê",
            "Slide 2: Antes do score vem o estado — ativa, adquirida, insolvente, liquidada ou inativa",
            f"Slide 3: Empresa em destaque — {company['label']} · {company['band']}",
            f"Slide 4: Pessoa em destaque — {person['label']} · {person['band']}",
            "Slide 5: Ferramentas por finalidade — "
            + "; ".join(f"{label}: {tool['name']}" for label, tool in tool_winners),
            f"Slide 6: Retirado do índice ativo — {change_line}",
            "Slide 7: Critérios + fontes visíveis · O que devemos verificar a seguir?",
        ]
    )
    return SaturdayResourcePost(
        slot="radar",
        title="Radar PTIA — o que mudou e porquê",
        body=body,
        image_prompt=_image_prompt("Radar PTIA — o que mudou e porquê", visual, edition),
        visual_brief=visual,
        source_urls=_source_urls(archived),
    )


def _top_items(
    index: dict[str, Any], section: str, label_key: str, *, limit: int
) -> list[dict[str, Any]]:
    items = sorted(
        index.get(section, []) or [],
        key=lambda item: int(item.get("rank") or 9999),
    )
    return [
        {
            "rank": int(item.get("rank") or position),
            "label": str(
                item.get(label_key) or item.get("name") or item.get("title") or ""
            ).strip(),
            "band": str(item.get("score_band") or "Seleção editorial"),
            "confidence": str(item.get("confidence") or "provisória"),
        }
        for position, item in enumerate(items[:limit], 1)
    ]


def _tool_winners(index: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    winners = []
    for category, label in SOCIAL_TOOL_CATEGORIES:
        candidates = [
            tool
            for tool in index.get("tools", []) or []
            if category in (tool.get("category_ranks") or {})
        ]
        if not candidates:
            continue
        winner = min(candidates, key=lambda tool: tool["category_ranks"][category])
        winners.append(
            (
                label,
                {
                    "name": str(winner.get("name") or ""),
                    "confidence": str(
                        (winner.get("category_confidence") or {}).get(category) or "editorial"
                    ),
                },
            )
        )
    return winners


def _source_urls(archived: list[dict[str, Any]]) -> tuple[str, ...]:
    urls = [RESOURCE_SOURCE_URL, METHODOLOGY_SOURCE_URL]
    for item in archived:
        for source in (item.get("verification") or {}).get("sources", []):
            url = str(source.get("url") or "")
            if url.startswith("https://") and url not in urls:
                urls.append(url)
    return tuple(urls)


def _image_prompt(title: str, visual_brief: str, edition: str) -> str:
    return f"""Cria um documento/carrossel editorial premium para LinkedIn sobre: "{title}".

Objetivo: gerar conversa a partir de uma mudança verificável, com critérios e fontes visíveis.
Formato: carrossel nativo LinkedIn, 1080x1080 por slide, fundo creme PTIA, azul PTIA #051A3B, tipografia editorial, composição limpa, muito espaço branco, hierarquia forte, sem laranja.

Texto visual a aplicar exatamente:
{visual_brief}

Estilo: editorial português, sofisticado e legível em mobile. Usar o wordmark PTIA oficial quando houver marca. Não usar robôs azuis, circuitos neon, hologramas, dashboards stock, pontuações com casas decimais ou pseudo-tipografia ilegível.

Edição: {edition}. Incluir no último slide ptia.pt/recursos e a indicação "fontes na publicação". Resultado pronto para revisão antes de ir para Buffer."""


def _post_id(target_date: date, slot: str) -> str:
    value = f"{SERIES_KIND}:{target_date.isoformat()}:{slot}:linkedin"
    return f"post_{stable_hash(value, 18)}"


def _topic_id(target_date: date, slot: str) -> str:
    value = f"{SERIES_KIND}:{target_date.isoformat()}:{slot}"
    return f"topic_{stable_hash(value, 18)}"


def _scheduled_time(target_date: date) -> str:
    return datetime.combine(target_date, time(10, 0), tzinfo=LISBON_TZ).isoformat()


def _iso_week(target_date: date) -> str:
    year, week, _ = target_date.isocalendar()
    return f"{year}-W{week:02d}"
