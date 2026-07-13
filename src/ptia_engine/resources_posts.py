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
    ("produtividade", "Produtividade"),
    ("design", "Design"),
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
    prompts = _top_items(index, "prompts", "title", limit=1)
    archived = [
        *index.get("entity_archive", {}).get("companies", []),
        *index.get("entity_archive", {}).get("people", []),
    ]
    summary = index.get("verification_summary") or {}
    eligible = int(summary.get("eligible") or 0)
    provisional = int(summary.get("provisional") or 0)
    profile_total = eligible + provisional
    tool_winners = _tool_winners(index)
    entity_leaders = _entity_leaders(index)
    leaders_by_kind = {kind: item for kind, item in entity_leaders}
    change = archived[0] if archived else None
    change_line = (
        f"{change['name']} saiu do índice ativo: "
        f"{change.get('status_reason') or 'o estado da entidade mudou e foi verificado.'}"
        if change
        else "Nesta edição não há novas alterações de estado."
    )
    gate_line = (
        f"{eligible}/{profile_total} perfis cumprem o gate de duas fontes recentes. "
        f"Os restantes {provisional} ficam na watchlist, sem posição."
        if profile_total
        else "A watchlist Portugal está em atualização; não há posições sem fontes."
    )
    prompt = prompts[0]["label"] if prompts else "Biblioteca PTIA"
    tool_lines = (
        "\n".join(
            f"• {label} — #1 {tool['name']} (índice {tool['score']}/100). "
            f"Melhor para: {tool['best_for']}"
            for label, tool in tool_winners
        )
        or "• Comparações por finalidade em atualização"
    )
    leader_lines = (
        "\n".join(
            f"• {label} — #1 {item['name']} (índice {item['score']}/100)."
            for label, item in entity_leaders
        )
        if entity_leaders
        else gate_line
    )

    body = f"""O melhor top não é o que tem mais nomes. É o que consegue explicar cada posição.

Três escolhas de IA por trabalho nesta edição:
{tool_lines}

Top Portugal nesta edição:
{leader_lines}

A correção que também conta:
{change_line}

E o Top Portugal?
{gate_line}

Cada top de ferramentas usa os mesmos quatro critérios: capacidade, adoção observável, adequação à tarefa e acesso. O índice é relativo à categoria — não é uma nota universal.

Prompt editorial da semana:
{prompt}

Qual destes comparativos queres ver aberto na próxima edição?

Top completo: {RESOURCE_SOURCE_URL}
Método, pesos e fontes: {METHODOLOGY_SOURCE_URL}"""

    featured_tool = tool_winners[0] if tool_winners else None
    tool_slide = (
        f"Slide 3: {featured_tool[0]} · #1 {featured_tool[1]['name']} · "
        f"índice {featured_tool[1]['score']}/100 · {featured_tool[1]['best_for']}"
        if featured_tool
        else "Slide 3: Ferramentas · ranking em atualização"
    )
    company = leaders_by_kind.get("Empresa")
    person = leaders_by_kind.get("Pessoa")
    company_slide = (
        f"Slide 4: Empresa #1 · {company['name']} · índice {company['score']}/100"
        if company
        else "Slide 4: Empresas · posição só depois de duas fontes recentes"
    )
    person_slide = (
        f"Slide 5: Pessoa #1 · {person['name']} · índice {person['score']}/100"
        if person
        else "Slide 5: Pessoas · posição só depois de duas fontes recentes"
    )
    visual = "\n".join(
        [
            "Slide 1: Quem lidera a IA esta semana — e porque merece a posição",
            "Slide 2: Duas regras — critérios comparáveis · fontes abertas",
            tool_slide,
            company_slide,
            person_slide,
            f"Slide 6: A correção que conta — {change_line}",
            f"Slide 7: O gate do ranking — {gate_line}",
            "Slide 8: Qual comparativo devemos abrir a seguir? · ptia.pt/recursos",
        ]
    )
    return SaturdayResourcePost(
        slot="radar",
        title="Radar PTIA — quem lidera a IA esta semana",
        body=body,
        image_prompt=_image_prompt("Radar PTIA — quem lidera a IA esta semana", visual, edition),
        visual_brief=visual,
        source_urls=_source_urls(archived, tool_winners, entity_leaders),
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
        }
        for position, item in enumerate(items[:limit], 1)
    ]


def _tool_winners(index: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
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
        if (winner.get("category_publication_status") or {}).get(category) != "ranked":
            continue
        sources = list((winner.get("category_sources") or {}).get(category) or [])
        winners.append(
            (
                label,
                {
                    "name": str(winner.get("name") or ""),
                    "score": int(
                        round(float((winner.get("category_scores") or {}).get(category) or 0))
                    ),
                    "best_for": str(winner.get("best_for") or ""),
                    "source_urls": [
                        str(source.get("url") or "")
                        for source in sources
                        if str(source.get("url") or "").startswith("https://")
                    ],
                },
            )
        )
    return winners


def _entity_leaders(index: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    leaders = []
    for key, label in (("companies", "Empresa"), ("people", "Pessoa")):
        candidates = [
            item
            for item in index.get(key, []) or []
            if item.get("eligibility") == "eligible" and item.get("rank")
        ]
        if not candidates:
            continue
        winner = min(candidates, key=lambda item: int(item["rank"]))
        sources = list((winner.get("verification") or {}).get("sources") or [])
        leaders.append(
            (
                label,
                {
                    "name": str(winner.get("name") or ""),
                    "score": int(round(float(winner.get("score") or 0))),
                    "source_urls": [
                        str(source.get("url") or "")
                        for source in sources
                        if str(source.get("url") or "").startswith("https://")
                    ],
                },
            )
        )
    return leaders


def _source_urls(
    archived: list[dict[str, Any]],
    tool_winners: list[tuple[str, dict[str, Any]]],
    entity_leaders: list[tuple[str, dict[str, Any]]] | None = None,
) -> tuple[str, ...]:
    urls = [RESOURCE_SOURCE_URL, METHODOLOGY_SOURCE_URL]
    for _, tool in tool_winners:
        for url in tool.get("source_urls") or []:
            if url not in urls:
                urls.append(url)
    for _, leader in entity_leaders or []:
        for url in leader.get("source_urls") or []:
            if url not in urls:
                urls.append(url)
    for item in archived:
        for source in (item.get("verification") or {}).get("sources", []):
            url = str(source.get("url") or "")
            if url.startswith("https://") and url not in urls:
                urls.append(url)
    return tuple(urls)


def _image_prompt(title: str, visual_brief: str, edition: str) -> str:
    return f"""Cria um documento editorial premium para LinkedIn sobre: "{title}".

Objetivo: parar o scroll com uma ideia clara e levar o leitor a deslizar para perceber a razão de cada posição.
Formato: documento PDF nativo LinkedIn, 1080x1350 por página (4:5), oito páginas, composição desenhada primeiro para leitura em telemóvel.

Texto visual a aplicar exatamente:
{visual_brief}

Sistema visual:
- capa azul PTIA #071A33, tipografia editorial grande e uma única promessa;
- páginas interiores marfim #F5F1E8, azul PTIA e dourado #D0AD67 apenas para posição e dados-chave;
- uma mensagem por página, números grandes, hierarquia evidente e bastante espaço negativo;
- grelha consistente, wordmark PTIA discreto e rodapé com edição;
- sem mosaico de cartões, sem etiquetas vagas, sem fotografias stock, robôs, circuitos, neon, 3D ou dashboards genéricos;
- não inventar logos, scores, citações, fontes ou texto;
- todas as páginas devem ser legíveis a 360 px de largura.

Edição: {edition}. No último slide incluir ptia.pt/recursos e "método e fontes no link". Resultado pronto para revisão antes de publicação."""


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
