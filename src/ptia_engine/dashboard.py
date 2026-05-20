from __future__ import annotations

import base64
import ast
import json
import os
import re
import shutil
import subprocess
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
import urllib.request
from urllib.parse import quote, urlparse

from PIL import Image, ImageFilter, ImageOps

from ptia_engine.assets import create_final_post_image
from ptia_engine.buffer_api import BufferClient
from ptia_engine.dedupe import stable_hash
from ptia_engine.editorial import add_performance_record, update_draft_status, update_item_status
from ptia_engine.http_client import urlopen_direct
from ptia_engine.editorial_board import (
    add_editorial_topic,
    add_final_post,
    add_radar_signal,
    update_final_post_copy,
    update_final_post_status,
    update_signal_status,
    update_topic_status,
)
from ptia_engine.models import ContentPerformance, Source, utc_now_iso
from ptia_engine.newsletter import generate_sample_issue, generate_weekly_issue, update_newsletter_status
from ptia_engine.rss import fetch_source
from ptia_engine.search_providers import GeminiGroundedSearchProvider
from ptia_engine.source_verifier import resolve_submitted_link, verify_search_candidate, verify_url
from ptia_engine.storage import (
    load_content_drafts,
    load_content_assets,
    load_content_performance,
    load_editorial_topics,
    load_final_posts,
    load_newsletter_issues,
    load_processed_items,
    load_radar_signals,
    load_raw_articles,
    load_trend_signals,
    write_jsonl,
)


def _to_dict(record):
    return record.to_record() if hasattr(record, "to_record") else asdict(record)


def _engagement_score(perf: ContentPerformance) -> int:
    return (
        perf.likes
        + perf.clicks
        + perf.comments * 2
        + perf.shares * 3
        + perf.saves * 3
        + perf.followers_gained * 4
    )


def _boost_candidates(final_posts, performance):
    posts_by_id = {post.post_id: post for post in final_posts}
    rows = []
    for perf in performance:
        post = posts_by_id.get(perf.draft_id) or posts_by_id.get(perf.post_id)
        score = _engagement_score(perf)
        meaningful_actions = perf.comments + perf.shares + perf.saves + perf.clicks
        engagement_rate = round((score / perf.impressions) * 100, 2) if perf.impressions else 0
        boost_ready = (
            perf.impressions >= 50
            and score >= 8
            and meaningful_actions >= 2
            and perf.channel in {"linkedin", "instagram"}
        )
        if boost_ready:
            action = "Boost 3-5 EUR"
            reason = "Já tem sinal orgânico suficiente para testar audiência paga pequena."
        elif score >= 5 or meaningful_actions >= 2:
            action = "Reaproveitar"
            reason = "Bom sinal editorial. Transformar em carousel, newsletter ou follow-up."
        else:
            action = "Não promover"
            reason = "Ainda não há prova suficiente. Evitar gastar orçamento."
        rows.append(
            {
                "post_id": post.post_id if post else perf.draft_id,
                "title": post.title if post else perf.topic,
                "channel": perf.channel,
                "published_at": perf.published_at,
                "score": score,
                "engagement_rate": engagement_rate,
                "impressions": perf.impressions,
                "likes": perf.likes,
                "comments": perf.comments,
                "shares": perf.shares,
                "saves": perf.saves,
                "clicks": perf.clicks,
                "followers_gained": perf.followers_gained,
                "action": action,
                "reason": reason,
                "published_url": post.published_url if post else perf.post_id,
            }
        )
    rows.sort(key=lambda row: (row["action"] == "Boost 3-5 EUR", row["score"]), reverse=True)
    weekly_budget = 8
    boost_rows = [row for row in rows if row["action"] == "Boost 3-5 EUR"][:2]
    return {
        "weekly_budget_eur": weekly_budget,
        "recommended_spend_eur": min(weekly_budget, len(boost_rows) * 4),
        "boost_candidates": boost_rows,
        "all_ranked": rows[:20],
        "rules": [
            "Só promover posts com sinal orgânico real.",
            "Prioridade a saves, shares, comentários e clicks; likes contam pouco.",
            "Orçamento inicial: 3-5 EUR por post vencedor, máximo 8 EUR/semana.",
            "Posts medianos viram aprendizagem, não anúncio.",
        ],
    }


def _normalise_hashtags(raw, channel: str = "") -> str:
    """Return clean social hashtags as '#TagA #TagB', never Python/JSON list syntax."""
    if not raw:
        return ""
    values = []
    if isinstance(raw, (list, tuple, set)):
        values = [str(item) for item in raw]
    else:
        text = str(raw).strip()
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, (list, tuple, set)):
            values = [str(item) for item in parsed]
        else:
            values = re.findall(r"#?[\wÀ-ÿ]+", text.replace(",", " "))
            if "#" not in text:
                values = []

    tags = []
    seen = set()
    for value in values:
        tag = value.strip().strip("[](){}'\".,;:")
        if not tag:
            continue
        tag = tag[1:] if tag.startswith("#") else tag
        tag = unicodedata.normalize("NFKD", tag).encode("ascii", "ignore").decode("ascii")
        tag = re.sub(r"[^A-Za-z0-9_]", "", tag)
        if not tag:
            continue
        tag = f"#{tag}"
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)

    max_count = {"linkedin": 4, "instagram": 5}.get(channel, 5)
    return " ".join(tags[:max_count])


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _refresh_final_posts_file(state: "DashboardState") -> None:
    posts = load_final_posts(state.final_posts_path)
    changed = False
    for post in posts:
        clean_hashtags = _normalise_hashtags(post.hashtags, post.channel)
        if post.hashtags != clean_hashtags:
            post.hashtags = clean_hashtags
            changed = True
    if changed:
        write_jsonl(state.final_posts_path, posts)


def _build_learnings(items, drafts, performance):
    item_by_id = {item.item_id: item for item in items}
    draft_by_id = {draft.draft_id: draft for draft in drafts}
    rows = []
    for perf in performance:
        draft = draft_by_id.get(perf.draft_id)
        item = item_by_id.get(draft.item_id) if draft else None
        rows.append(
            {
                "performance": perf,
                "draft": draft,
                "item": item,
                "score": _engagement_score(perf),
                "section": perf.section or (item.section if item else ""),
                "source": item.source_name if item else "",
                "channel": perf.channel,
            }
        )

    best = sorted(rows, key=lambda row: row["score"], reverse=True)[:5]
    weakest = sorted(rows, key=lambda row: row["score"])[:5]
    by_section = defaultdict(list)
    by_source = defaultdict(list)
    by_channel = defaultdict(list)
    for row in rows:
        if row["section"]:
            by_section[row["section"]].append(row["score"])
        if row["source"]:
            by_source[row["source"]].append(row["score"])
        if row["channel"]:
            by_channel[row["channel"]].append(row["score"])

    def averages(groups):
        output = []
        for name, scores in groups.items():
            if not scores:
                continue
            output.append({"name": name, "avg_score": round(sum(scores) / len(scores), 2), "count": len(scores)})
        return sorted(output, key=lambda row: row["avg_score"], reverse=True)

    recommendations = []
    top_sections = averages(by_section)[:3]
    top_sources = averages(by_source)[:3]
    if top_sections:
        recommendations.append(
            "Dar mais peso inicial a secoes com melhor performance: "
            + ", ".join(row["name"] for row in top_sections)
            + "."
        )
    if top_sources:
        recommendations.append(
            "Priorizar fontes que ja geraram melhor resposta: "
            + ", ".join(row["name"] for row in top_sources)
            + "."
        )
    if not rows:
        recommendations.append("Ainda nao ha metricas suficientes. Publicar e registar resultados manualmente.")

    return {
        "best_posts": [_learning_row(row) for row in best],
        "weak_posts": [_learning_row(row) for row in weakest],
        "sections": top_sections,
        "sources": top_sources,
        "channels": averages(by_channel),
        "recommendations": recommendations,
    }


def _learning_row(row):
    perf = row["performance"]
    draft = row["draft"]
    return {
        "draft_id": perf.draft_id,
        "title": draft.title if draft else perf.topic,
        "channel": perf.channel,
        "section": row["section"],
        "source": row["source"],
        "score": row["score"],
        "impressions": perf.impressions,
        "likes": perf.likes,
        "comments": perf.comments,
        "shares": perf.shares,
        "saves": perf.saves,
        "clicks": perf.clicks,
        "notes": perf.notes,
    }


class DashboardState:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    @property
    def raw_path(self) -> Path:
        return self.data_dir / "raw_articles.jsonl"

    @property
    def processed_path(self) -> Path:
        return self.data_dir / "processed_items.jsonl"

    @property
    def drafts_path(self) -> Path:
        return self.data_dir / "content_drafts.jsonl"

    @property
    def performance_path(self) -> Path:
        return self.data_dir / "content_performance.jsonl"

    @property
    def trends_path(self) -> Path:
        return self.data_dir / "trend_signals.jsonl"

    @property
    def assets_path(self) -> Path:
        return self.data_dir / "content_assets.jsonl"

    @property
    def radar_signals_path(self) -> Path:
        return self.data_dir / "radar_signals.jsonl"

    @property
    def editorial_topics_path(self) -> Path:
        return self.data_dir / "editorial_topics.jsonl"

    @property
    def final_posts_path(self) -> Path:
        return self.data_dir / "final_posts.jsonl"

    @property
    def newsletter_issues_path(self) -> Path:
        return self.data_dir / "newsletter_issues.jsonl"

    @property
    def sources_config_path(self) -> Path:
        return self.data_dir.parent / "config" / "sources.sample.json"

    @property
    def buffer_channels_path(self) -> Path:
        return self.data_dir / "buffer_channels.json"

    @property
    def final_assets_dir(self) -> Path:
        return self.data_dir / "final_assets"

    @property
    def site_dir(self) -> Path:
        return self.data_dir.parent / "site"

    def snapshot(self) -> dict:
        _refresh_final_posts_file(self)
        articles = load_raw_articles(self.raw_path)
        items = load_processed_items(self.processed_path)
        drafts = load_content_drafts(self.drafts_path)
        performance = load_content_performance(self.performance_path)
        assets = load_content_assets(self.assets_path)
        buffer_channels = _load_buffer_channels(self.buffer_channels_path)
        radar_signals = sorted(
            load_radar_signals(self.radar_signals_path),
            key=lambda signal: (signal.engagement_score, signal.fetched_at),
            reverse=True,
        )
        editorial_topics = sorted(
            load_editorial_topics(self.editorial_topics_path),
            key=lambda topic: (topic.urgency_score, topic.created_at),
            reverse=True,
        )
        final_posts = _ensure_image_variants_for_posts(self, load_final_posts(self.final_posts_path))
        newsletter_issues = sorted(
            load_newsletter_issues(self.newsletter_issues_path),
            key=lambda issue: issue.created_at,
            reverse=True,
        )
        trends = sorted(
            load_trend_signals(self.trends_path),
            key=lambda signal: signal.engagement_score,
            reverse=True,
        )
        item_by_id = {item.item_id: item for item in items}
        assets_by_draft = defaultdict(list)
        for asset in assets:
            assets_by_draft[asset.draft_id].append(asset)

        article_status = Counter(article.status for article in articles)
        item_status = Counter(item.editorial_status for item in items)
        draft_status = Counter(draft.status for draft in drafts)
        draft_channel = Counter(draft.channel for draft in drafts)
        radar_status = Counter(signal.status for signal in radar_signals)
        topic_status = Counter(topic.status for topic in editorial_topics)
        final_post_status = Counter(post.status for post in final_posts)
        radar_inbox_signals = [
            signal for signal in radar_signals if signal.status in {"new", "topic_candidate"}
        ]
        verifying_signals = [signal for signal in radar_signals if signal.status == "verifying"]
        verified_signals = [
            signal for signal in radar_signals if signal.status in {"verified", "verified_secondary"}
        ]
        selected_signals = [signal for signal in radar_signals if signal.status == "selected"]
        review_posts = [post for post in final_posts if post.status == "needs_final_review"]
        final_review_topics = {post.topic_id for post in review_posts}
        final_approved_topics = {
            post.topic_id for post in final_posts if post.status == "approved_for_schedule"
        }
        final_scheduled_topics = {
            post.topic_id for post in final_posts if post.status == "scheduled"
        }
        final_published_topics = {
            post.topic_id for post in final_posts if post.status == "published"
        }

        review_items = [
            item
            for item in items
            if item.should_cover and item.editorial_status in {"needs_review", "needs_source_check"}
        ]
        review_items.sort(
            key=lambda item: (
                item.relevance_score,
                item.portugal_relevance_score,
                item.builder_relevance_score,
                item.business_relevance_score,
                -item.hype_score,
            ),
            reverse=True,
        )

        draft_queue = [draft for draft in drafts if draft.status in {"draft", "needs_edit"}]
        ready_to_schedule = [draft for draft in drafts if draft.status == "approved"]
        scheduled = [draft for draft in drafts if draft.status == "scheduled"]
        published = [draft for draft in drafts if draft.status == "published"]

        return {
            "counts": {
                "radar_signals_v2": len(radar_inbox_signals),
                "verifying": len(verifying_signals),
                "verified_selection": len(verified_signals) + len(selected_signals),
                "a_rever": len(final_review_topics),
                "topics": len(editorial_topics),
                "topics_needs_review": topic_status.get("needs_review", 0),
                "final_posts": len(final_posts),
                "final_needs_review": final_post_status.get("needs_final_review", 0),
                "final_approved": len(final_approved_topics),
                "final_scheduled": len(final_scheduled_topics),
                "final_published": len(final_published_topics),
                "newsletter_drafts": sum(
                    1 for issue in newsletter_issues if issue.status in {"draft", "approved"}
                ),
                "raw_articles": len(articles),
                "new_articles": article_status.get("new", 0),
                "duplicates": article_status.get("duplicate", 0),
                "processed_items": len(items),
                "needs_review": item_status.get("needs_review", 0),
                "rejected_items": item_status.get("rejected", 0),
                "drafts": len(drafts),
                "draft": draft_status.get("draft", 0) + draft_status.get("needs_edit", 0),
                "approved_drafts": draft_status.get("approved", 0),
                "scheduled": draft_status.get("scheduled", 0),
                "published": draft_status.get("published", 0),
                "performance_records": len(performance),
                "trend_signals": len(trends),
                "assets": len(assets),
            },
            "status": {
                "radar": dict(radar_status),
                "topics": dict(topic_status),
                "final_posts": dict(final_post_status),
                "articles": dict(article_status),
                "items": dict(item_status),
                "drafts": dict(draft_status),
                "channels": dict(draft_channel),
            },
            "recent_articles": [_to_dict(article) for article in articles[-20:]][::-1],
            "radar_signals_v2": [_to_dict(signal) for signal in radar_signals[:60]],
            "radar_inbox_signals": [_to_dict(signal) for signal in radar_inbox_signals[:20]],
            "verifying_signals": [_to_dict(signal) for signal in verifying_signals],
            "verified_signals": [_to_dict(signal) for signal in verified_signals],
            "selected_signals": [_to_dict(signal) for signal in selected_signals],
            "editorial_topics": [
                _topic_payload(topic, radar_signals) for topic in editorial_topics[:40]
            ],
            "final_posts": [_to_dict(post) for post in final_posts],
            "final_ready_to_schedule": [
                _to_dict(post) for post in final_posts if post.status == "approved_for_schedule"
            ],
            "final_scheduled_posts": [_to_dict(post) for post in final_posts if post.status == "scheduled"],
            "final_published_posts": [_to_dict(post) for post in final_posts if post.status == "published"],
            "newsletter_issues": [_to_dict(issue) for issue in newsletter_issues[:12]],
            "newsletter_sample": _to_dict(generate_sample_issue()),
            "review_items": [_to_dict(item) for item in review_items[:30]],
            "draft_queue": [_draft_payload(draft, item_by_id, assets_by_draft) for draft in draft_queue[:40]],
            "ready_to_schedule": [
                _draft_payload(draft, item_by_id, assets_by_draft) for draft in ready_to_schedule[:40]
            ],
            "scheduled": [_draft_payload(draft, item_by_id, assets_by_draft) for draft in scheduled[:30]],
            "published": [_draft_payload(draft, item_by_id, assets_by_draft) for draft in published[:30]],
            "performance": [_to_dict(perf) for perf in performance[-50:]][::-1],
            "trends": [_to_dict(signal) for signal in trends[:40]],
            "assets": [_to_dict(asset) for asset in assets[-80:]][::-1],
            "buffer_channels": buffer_channels,
            "buffer_available": BufferClient().available,
            "learnings": _build_learnings(items, drafts, performance),
            "growth": _boost_candidates(final_posts, performance),
        }


def _topic_payload(topic, radar_signals):
    payload = _to_dict(topic)
    by_id = {signal.signal_id: signal for signal in radar_signals}
    payload["signals"] = [_to_dict(by_id[signal_id]) for signal_id in topic.source_signal_ids if signal_id in by_id]
    return payload


def _draft_payload(draft, item_by_id, assets_by_draft):
    payload = _to_dict(draft)
    item = item_by_id.get(draft.item_id)
    payload["text"] = draft.body or draft.caption or draft.carousel_outline
    payload["section"] = item.section if item else ""
    payload["source_name"] = item.source_name if item else ""
    payload["source_url"] = item.source_url if item else ""
    payload["assets"] = [_to_dict(asset) for asset in assets_by_draft.get(draft.draft_id, [])]
    return payload


def _find_signal(signals_path: Path, signal_id: str):
    for signal in load_radar_signals(signals_path):
        if signal.signal_id == signal_id:
            return signal
    raise ValueError(f"Signal not found: {signal_id}")


def _update_signal_verification_fields(
    signals_path: Path,
    signal_id: str,
    *,
    source_name: str,
    title: str,
    url: str,
    published_at: str,
    summary: str,
    notes: str,
):
    signals = load_radar_signals(signals_path)
    for signal in signals:
        if signal.signal_id != signal_id:
            continue
        signal.status = "verified"
        signal.source_name = source_name or signal.source_name
        signal.title = title or signal.title
        signal.url = url or signal.url
        signal.published_at = published_at or signal.published_at
        signal.summary = summary or signal.summary
        if notes:
            signal.notes = f"{signal.notes}\n[{utc_now_iso()}] {notes}".strip()
        write_jsonl(signals_path, signals)
        return signal
    raise ValueError(f"Signal not found: {signal_id}")


def _polish_final_post_copy(
    *,
    channel: str,
    title: str,
    body: str,
    hashtags: str,
    source_urls: list[str],
) -> dict:
    provider = GeminiGroundedSearchProvider()
    if not provider.available:
        return {
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "editor_notes": "PT-PT polish nao aplicado: GEMINI_API_KEY indisponivel.",
        }
    try:
        polished = provider.polish_final_post(
            channel=channel,
            title=title,
            body=body,
            hashtags=hashtags,
            source_urls=source_urls,
        )
    except RuntimeError as exc:
        return {
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "editor_notes": f"PT-PT polish nao aplicado: {exc}",
        }

    return {
        "title": polished.title or title,
        "body": polished.body or body,
        "hashtags": polished.hashtags if polished.hashtags != "" else hashtags,
        "editor_notes": (
            "PT-PT Editorial Polish aplicado com prompt Gemini. "
            "Evaristo/Gervasio fica pendente de API estavel. "
            f"{polished.rationale}".strip()
        ),
    }


def _high_quality_image_prompt(title: str, body: str, feedback: str = "") -> str:
    feedback_line = f"\nPedido adicional do editor: {feedback.strip()}" if feedback.strip() else ""
    return (
        'Cria uma imagem sem texto editorial premium para partilhar no LinkedIn e Instagram sobre este tema: "'
        f"{title}"
        '"\n\n'
        "Resultado esperado: imagem quadrada 1:1, visual forte, original e memorável, com qualidade de campanha editorial. "
        "Estilo: fotorealista/cinemático, luz natural sofisticada, composição limpa, profundidade, textura real, "
        "sem texto escrito na imagem, sem mockups de dashboards genéricos, sem ícones flutuantes baratos, sem aspecto stock. "
        "Deve comunicar a ideia central da notícia através de uma metáfora visual concreta, humana e relevante. "
        "Se o tema envolver Portugal, pode usar sinais visuais subtis portugueses ou europeus, mas sem mapas literais forçados. "
        "Evita clichés de robôs azuis, circuitos neon e pessoas a apontar para hologramas, salvo se forem essenciais ao conceito. "
        "A imagem deve funcionar como capa premium de uma publicação de tecnologia e sociedade."
        f"{feedback_line}"
    )


def _build_final_pack_from_signal(state: DashboardState, signal_id: str) -> dict:
    signal = _find_signal(state.radar_signals_path, signal_id)
    if signal.status not in {"verified", "verified_secondary", "selected"}:
        raise ValueError("Só sinais verificados podem gerar pacote final.")

    source_url = signal.url
    topic = add_editorial_topic(
        state.editorial_topics_path,
        title=signal.title[:120],
        thesis=signal.summary or signal.why_it_matters or signal.title,
        portugal_angle=(
            "Validar o impacto para empresas, profissionais e builders em Portugal "
            "antes de publicar."
        ),
        audience="PTIA",
        source_signal_ids=[signal.signal_id],
        urgency_score=max(6, min(10, signal.engagement_score // 10 or 6)),
    )
    update_topic_status(
        state.editorial_topics_path,
        topic.topic_id,
        "approved_for_final",
        "Criado a partir de Verified Selection.",
    )

    base_summary = signal.summary or "A fonte assinala uma novidade relevante em inteligência artificial."
    why_it_matters = signal.why_it_matters or (
        "O ponto a observar é se esta novidade muda decisões concretas de trabalho, produto ou investimento."
    )
    ptia_lens = (
        "A parte interessante não é o anúncio em si. É o que ele revela sobre a velocidade com que a IA "
        "está a sair dos laboratórios e a entrar em decisões, processos e relações de poder. "
        "Há entusiasmo legítimo aqui, mas também uma pergunta incómoda: quem está preparado para usar isto "
        "com ambição, critério e responsabilidade?"
    )
    next_action = (
        "O próximo passo é separar promessa de capacidade real: quem já pode usar isto, que barreiras existem, "
        "e que organizações têm coragem para transformar a novidade em vantagem."
    )
    hashtags = "#InteligenciaArtificial #IA #Portugal #PTIA"
    image_prompt = _high_quality_image_prompt(
        signal.title,
        f"{base_summary}\n\n{why_it_matters}\n\n{ptia_lens}",
    )
    source_line = f"Fonte original: {source_url}"
    posts = [
        add_final_post(
            state.final_posts_path,
            topic_id=topic.topic_id,
            channel="linkedin",
            title=signal.title,
            body=(
                f"{signal.title}\n\n"
                f"{base_summary}\n\n"
                f"{ptia_lens}\n\n"
                f"{why_it_matters} {next_action}\n\n"
                f"{source_line}\n\n"
                "Isto entraria na tua lista de prioridades para os próximos meses?"
            ),
            hashtags=hashtags,
            image_prompt=image_prompt,
            source_urls=[source_url],
        ),
        add_final_post(
            state.final_posts_path,
            topic_id=topic.topic_id,
            channel="instagram",
            title=signal.title,
            body=(
                f"{signal.title}\n\n"
                f"{base_summary}\n\n"
                f"{ptia_lens}\n\n"
                "- O anúncio é só o ponto de partida\n"
                "- O valor está na execução\n"
                "- O risco é confundir acesso com transformação\n\n"
                f"{source_line}"
            ),
            hashtags=hashtags,
            image_prompt=image_prompt,
            source_urls=[source_url],
        ),
        add_final_post(
            state.final_posts_path,
            topic_id=topic.topic_id,
            channel="site",
            title=signal.title,
            body=(
                f"{base_summary}\n\n"
                f"{ptia_lens}\n\n"
                f"{why_it_matters}\n\n"
                f"{next_action}\n\n"
                f"{source_line}"
            ),
            hashtags="",
            image_prompt=image_prompt,
            source_urls=[source_url],
        ),
    ]
    polished_posts = []
    for post in posts:
        polished = _polish_final_post_copy(
            channel=post.channel,
            title=post.title,
            body=post.body,
            hashtags=post.hashtags,
            source_urls=post.source_urls,
        )
        polished_posts.append(
            update_final_post_copy(
                state.final_posts_path,
                post.post_id,
                title=polished["title"],
                body=polished["body"],
                hashtags=polished["hashtags"],
                notes=polished["editor_notes"],
            )
        )
    posts = polished_posts
    update_signal_status(
        state.radar_signals_path,
        signal.signal_id,
        "used",
        "Pacote final criado para revisão.",
    )
    return {"topic": _to_dict(topic), "posts": [_to_dict(post) for post in posts]}


def _load_sources(path: Path) -> list[Source]:
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    return [Source.from_record(record) for record in records]


def _load_buffer_channels(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_buffer_channels(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _buffer_channel_id_for(post_channel: str, config: dict) -> str:
    channels = config.get("channels", {})
    if post_channel == "linkedin":
        return str(channels.get("linkedin") or channels.get("linkedin_page") or "")
    if post_channel == "instagram":
        return str(channels.get("instagram") or "")
    return ""


def _image_path_for_channel(post) -> str:
    variants = getattr(post, "image_variants", {}) or {}
    return str(variants.get(post.channel) or post.image_path or "")


def _public_image_url_for_buffer(post) -> str:
    image_path = _image_path_for_channel(post)
    if not image_path:
        return ""
    if image_path.startswith(("https://", "http://")):
        return image_path
    base_url = (
        os.getenv("PTIA_PUBLIC_ASSET_BASE_URL")
        or os.getenv("PTIA_PUBLIC_SITE_URL")
        or "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site"
    ).strip().rstrip("/")
    return f"{base_url}/assets/final/{quote(Path(image_path).name)}"


def _copy_image_to_public_site_assets(state: DashboardState, post) -> str:
    image_path = _image_path_for_channel(post)
    if not image_path or image_path.startswith(("https://", "http://")):
        return image_path
    source = Path(image_path)
    if not source.exists():
        return ""
    target_dir = state.site_dir / "assets" / "final"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
        shutil.copy2(source, target)
    return str(target)


def _can_auto_deploy_site(state: DashboardState) -> bool:
    return (state.site_dir / ".vercel" / "project.json").exists()


def _public_url_available(url: str) -> bool:
    if not url:
        return False
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urlopen_direct(request, timeout=20) as response:
            return response.status < 400
    except Exception:  # noqa: BLE001 - a failed preflight means Buffer will fail too.
        return False


def _deploy_site_assets_to_vercel(state: DashboardState) -> None:
    if not _can_auto_deploy_site(state):
        return
    env = os.environ.copy()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "GIT_HTTP_PROXY", "GIT_HTTPS_PROXY"):
        env[key] = ""
    result = subprocess.run(
        ["vercel", "deploy", "--prod", "--yes", "--scope", "joaoncdferreira-ais-projects"],
        cwd=state.site_dir,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        raise ValueError(f"Falhou deploy das imagens para Vercel antes do Buffer: {output[-1000:]}")


def _publish_site_assets_to_git(state: DashboardState) -> None:
    base_url = (
        os.getenv("PTIA_PUBLIC_ASSET_BASE_URL")
        or os.getenv("PTIA_PUBLIC_SITE_URL")
        or "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site"
    )
    if "raw.githubusercontent.com" not in base_url:
        return

    repo_root = state.data_dir.parent
    env = os.environ.copy()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "GIT_HTTP_PROXY", "GIT_HTTPS_PROXY"):
        env[key] = ""

    commands = [
        ["git", "add", "site/assets/final"],
        ["git", "diff", "--cached", "--quiet"],
    ]
    subprocess.run(commands[0], cwd=repo_root, env=env, capture_output=True, text=True, timeout=60, check=False)
    diff = subprocess.run(commands[1], cwd=repo_root, env=env, capture_output=True, text=True, timeout=60, check=False)
    if diff.returncode == 0:
        return
    commit = subprocess.run(
        ["git", "commit", "-m", "Publish scheduled media assets"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if commit.returncode != 0:
        output = "\n".join(part for part in [commit.stdout, commit.stderr] if part).strip()
        raise ValueError(f"Falhou commit das imagens publicas antes do Buffer: {output[-1000:]}")
    push = subprocess.run(
        ["git", "push"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if push.returncode != 0:
        output = "\n".join(part for part in [push.stdout, push.stderr] if part).strip()
        raise ValueError(f"Falhou push das imagens publicas antes do Buffer: {output[-1000:]}")


def _ensure_public_images_for_buffer(state: DashboardState, posts: list) -> None:
    social_posts = [
        post
        for post in posts
        if post.channel in {"linkedin", "instagram"} and _image_path_for_channel(post)
    ]
    if not social_posts or not _can_auto_deploy_site(state):
        return

    for post in social_posts:
        _copy_image_to_public_site_assets(state, post)

    missing = [post for post in social_posts if not _public_url_available(_public_image_url_for_buffer(post))]
    if missing:
        _publish_site_assets_to_git(state)
        missing = [post for post in social_posts if not _public_url_available(_public_image_url_for_buffer(post))]

    if missing:
        _deploy_site_assets_to_vercel(state)

    still_missing = [
        _public_image_url_for_buffer(post)
        for post in social_posts
        if not _public_url_available(_public_image_url_for_buffer(post))
    ]
    if still_missing:
        raise ValueError(
            "As imagens ainda nao estao publicas num URL acessivel pelo Buffer. "
            f"Primeiro URL em falta: {still_missing[0]}"
        )


def _discover_buffer_channels(path: Path) -> dict:
    client = BufferClient()
    organizations, channels = client.discover_channels()
    service_map: dict[str, str] = {}
    channel_records = []
    for channel in channels:
        service = channel.service.lower()
        channel_records.append(
            {
                "id": channel.id,
                "name": channel.name,
                "display_name": channel.display_name,
                "service": channel.service,
            }
        )
        if "instagram" in service and not service_map.get("instagram"):
            service_map["instagram"] = channel.id
        if "linkedin" in service and not service_map.get("linkedin"):
            service_map["linkedin"] = channel.id
    payload = {
        "organizations": [{"id": org.id, "name": org.name} for org in organizations],
        "channels": service_map,
        "all_channels": channel_records,
        "updated_at": utc_now_iso(),
    }
    _write_buffer_channels(path, payload)
    return payload


def _schedule_post_in_buffer(state: DashboardState, post_id: str, scheduled_time: str):
    posts = {post.post_id: post for post in load_final_posts(state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
    if post.channel == "site":
        _copy_image_to_public_site_assets(state, post)
        return update_final_post_status(
            state.final_posts_path,
            post_id,
            "scheduled",
            scheduled_time=scheduled_time,
        )
    image_url = _public_image_url_for_buffer(post)
    if post.channel == "instagram":
        if not _image_path_for_channel(post):
            raise ValueError("Instagram precisa de imagem final antes de agendar.")
        _copy_image_to_public_site_assets(state, post)
        image_url = _public_image_url_for_buffer(post)
        if not image_url:
            update_final_post_status(
                state.final_posts_path,
                post_id,
                "scheduled",
                scheduled_time=scheduled_time,
                buffer_post_id="manual_buffer_media_required",
            )
            return update_final_post_copy(
                state.final_posts_path,
                post_id,
                notes=(
                    "Instagram marcado no plano, mas nao enviado ao Buffer: "
                    "a imagem existe localmente e ainda nao tem URL publico para media upload."
                ),
            )
    channel_config = _load_buffer_channels(state.buffer_channels_path)
    _ensure_public_images_for_buffer(state, [post])
    channel_id = _buffer_channel_id_for(post.channel, channel_config)
    if not channel_id:
        channel_config = _discover_buffer_channels(state.buffer_channels_path)
        channel_id = _buffer_channel_id_for(post.channel, channel_config)
    if not channel_id:
        raise ValueError(f"Buffer nao tem canal configurado para {post.channel}.")
    if image_url:
        _copy_image_to_public_site_assets(state, post)
    buffer_post = BufferClient().create_scheduled_post(
        channel_id=channel_id,
        text=_final_post_text(post),
        due_at=scheduled_time,
        image_url=image_url,
        post_type="post" if post.channel == "instagram" else "",
    )
    return update_final_post_status(
        state.final_posts_path,
        post_id,
        "scheduled",
        scheduled_time=scheduled_time,
        buffer_post_id=buffer_post.id,
    )


def _final_post_text(post) -> str:
    hashtags_value = _normalise_hashtags(post.hashtags, post.channel)
    hashtags = f"\n\n{hashtags_value}" if hashtags_value else ""
    sources = ""
    if post.source_urls:
        sources = "\n\nFontes:\n" + "\n".join(f"- {url}" for url in post.source_urls)
    return f"{post.body}{hashtags}{sources}".strip()


def _generate_final_image(state: DashboardState, post_id: str, feedback: str = ""):
    posts = {post.post_id: post for post in load_final_posts(state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
    image_path = create_final_post_image(post, state.final_assets_dir, feedback=feedback)
    return update_final_post_status(
        state.final_posts_path,
        post_id,
        post.status,
        image_path=str(image_path),
        image_status="needs_review",
    )


def _safe_asset_ext(filename: str, data_url: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    if data_url.startswith("data:image/png"):
        return ".png"
    if data_url.startswith("data:image/webp"):
        return ".webp"
    return ".jpg"


IMAGE_VARIANT_SPECS = {
    "instagram": (1080, 1080, "cover"),
    "linkedin": (1200, 627, "contain_blur"),
    "site": (1600, 900, "contain_blur"),
}


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, (248, 245, 237))
        background.paste(image.convert("RGBA"), mask=image.convert("RGBA").getchannel("A"))
        return background
    return image.convert("RGB")


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _contain_on_blur(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    background = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=28))
    darkener = Image.new("RGB", (width, height), (5, 26, 59))
    background = Image.blend(background, darkener, 0.16)

    foreground = image.copy()
    foreground.thumbnail((width, height), Image.Resampling.LANCZOS)
    x = (width - foreground.width) // 2
    y = (height - foreground.height) // 2
    background.paste(foreground, (x, y))
    return background


def _format_image_variants(source_path: Path, out_dir: Path, post_id: str) -> dict[str, str]:
    """Create channel-safe images from one master image.

    Instagram needs a square asset. LinkedIn and site cards are landscape; using a
    blurred contain canvas keeps the whole generated image visible instead of
    cropping faces, logos or maps at the top/bottom.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as opened:
        image = ImageOps.exif_transpose(opened)
        image = _flatten_for_jpeg(image)

    variants: dict[str, str] = {}
    for channel, (width, height, mode) in IMAGE_VARIANT_SPECS.items():
        if mode == "cover":
            variant = _cover_crop(image, (width, height))
        else:
            variant = _contain_on_blur(image, (width, height))
        path = out_dir / f"{post_id}_{channel}_{width}x{height}.jpg"
        variant.save(path, "JPEG", quality=92, optimize=True)
        variants[channel] = str(path)
    return variants


def _ensure_image_variants_for_posts(state: DashboardState, posts: list) -> list:
    changed = False
    for post in posts:
        if post.image_variants or not post.image_path:
            continue
        source_path = Path(post.image_path)
        if not source_path.exists() or source_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        try:
            post.image_variants = _format_image_variants(source_path, state.final_assets_dir, post.post_id)
            changed = True
        except Exception:
            continue
    if changed:
        write_jsonl(state.final_posts_path, posts)
    return posts


def _apply_image_to_topic_package(
    state: DashboardState,
    *,
    reference_post_id: str,
    image_path: str,
    image_variants: dict[str, str],
    image_status: str,
):
    posts = load_final_posts(state.final_posts_path)
    reference = next((post for post in posts if post.post_id == reference_post_id), None)
    if not reference:
        raise ValueError(f"Final post not found: {reference_post_id}")
    updated = []
    for post in posts:
        if post.topic_id != reference.topic_id:
            continue
        if post.status not in {"needs_final_review", "approved_for_schedule", "scheduled"}:
            continue
        post.image_path = image_path
        post.image_variants = image_variants
        post.image_status = image_status
        updated.append(post)
    write_jsonl(state.final_posts_path, posts)
    return next(post for post in updated if post.post_id == reference_post_id)


def _upload_final_image(state: DashboardState, post_id: str, filename: str, data_url: str):
    posts = {post.post_id: post for post in load_final_posts(state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
    if "," not in data_url or not data_url.startswith("data:image/"):
        raise ValueError("Imagem invalida. Usa PNG, JPG ou WebP.")
    header, encoded = data_url.split(",", 1)
    raw = base64.b64decode(encoded)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("Imagem demasiado pesada. Maximo: 10 MB.")
    state.final_assets_dir.mkdir(parents=True, exist_ok=True)
    ext = _safe_asset_ext(filename, header)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", Path(filename or "imagem").stem).strip("-")[:50] or "imagem"
    file_path = state.final_assets_dir / f"{post.post_id}_{stable_hash(filename + encoded[:128], 8)}_{safe_name}{ext}"
    file_path.write_bytes(raw)
    variants = _format_image_variants(file_path, state.final_assets_dir, post.post_id)
    return _apply_image_to_topic_package(
        state,
        reference_post_id=post_id,
        image_path=str(file_path),
        image_variants=variants,
        image_status="needs_review",
    )


def _sync_topic_posts_from_reference(
    state: DashboardState,
    reference_post_id: str,
    feedback: str,
) -> list:
    posts = load_final_posts(state.final_posts_path)
    reference = next((post for post in posts if post.post_id == reference_post_id), None)
    if not reference:
        raise ValueError(f"Final post not found: {reference_post_id}")
    siblings = [
        post
        for post in posts
        if post.topic_id == reference.topic_id
        and post.post_id != reference.post_id
        and post.status in {"needs_final_review", "approved_for_schedule"}
    ]
    if not siblings:
        return [reference]
    provider = GeminiGroundedSearchProvider()
    if not provider.available:
        raise RuntimeError("GEMINI_API_KEY não está configurada.")
    updated = [reference]
    reference_text = f"Título: {reference.title}\n\nTexto:\n{reference.body}\n\nHashtags:\n{reference.hashtags}"
    for sibling in siblings:
        rewrite = provider.rewrite_final_post(
            channel=sibling.channel,
            title=sibling.title,
            body=sibling.body,
            hashtags=sibling.hashtags,
            source_urls=sibling.source_urls,
            feedback=(
                "Actualiza este canal para ficar coerente com o draft de referência abaixo, "
                "sem copiar literalmente quando o canal exigir outro formato. "
                "Mantém a fonte original, o tom editorial e as regras do canal. "
                "Não forces um ângulo Portugal se ele não for material.\n\n"
                f"Pedido do editor: {feedback}\n\n"
                f"Draft de referência ({reference.channel}):\n{reference_text}"
            ),
        )
        updated.append(
            update_final_post_copy(
                state.final_posts_path,
                sibling.post_id,
                title=rewrite.title or sibling.title,
                body=rewrite.body or sibling.body,
                hashtags=rewrite.hashtags if rewrite.hashtags != "" else sibling.hashtags,
                image_prompt=_high_quality_image_prompt(
                    rewrite.title or sibling.title,
                    rewrite.body or sibling.body,
                ),
                notes=f"Sync pacote a partir de {reference.channel}. Pedido: {feedback}\nRewrite: {rewrite.rationale}",
            )
        )
    return updated


def _approve_final_package(state: DashboardState, reference_post_id: str) -> list:
    posts = load_final_posts(state.final_posts_path)
    reference = next((post for post in posts if post.post_id == reference_post_id), None)
    if not reference:
        raise ValueError(f"Final post not found: {reference_post_id}")
    package_posts = [
        post
        for post in posts
        if post.topic_id == reference.topic_id and post.status == "needs_final_review"
    ]
    if not package_posts:
        raise ValueError("Este pacote ja nao esta em A Rever.")
    updated = []
    for post in package_posts:
        updated.append(
            update_final_post_status(
                state.final_posts_path,
                post.post_id,
                "approved_for_schedule",
            )
        )
    return updated


def _package_posts_for_topic(state: DashboardState, topic_id: str, status: str) -> list:
    return [
        post
        for post in load_final_posts(state.final_posts_path)
        if post.topic_id == topic_id and post.status == status
    ]


def _schedule_final_package(state: DashboardState, topic_id: str, scheduled_time: str) -> list:
    posts = _package_posts_for_topic(state, topic_id, "approved_for_schedule")
    if not posts:
        raise ValueError("Nao ha posts aprovados neste pacote para agendar.")
    _ensure_public_images_for_buffer(state, posts)
    updated = []
    for post in posts:
        updated.append(_schedule_post_in_buffer(state, post.post_id, scheduled_time))
    return updated


def _reject_final_post(state: DashboardState, post_id: str) -> object:
    posts = {post.post_id: post for post in load_final_posts(state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
    if post.status == "scheduled" and post.buffer_post_id and post.buffer_post_id != "manual_buffer_media_required":
        try:
            BufferClient().delete_post(post.buffer_post_id)
            notes = f"Rejeitado e removido do Buffer: {post.buffer_post_id}"
        except Exception as exc:  # noqa: BLE001 - keep local rejection visible if Buffer rejects deletion.
            notes = f"Rejeitado localmente. Falhou remover do Buffer {post.buffer_post_id}: {exc}"
    else:
        notes = "Rejeitado"
    post = update_final_post_status(
        state.final_posts_path,
        post_id=post_id,
        status="rejected",
        buffer_post_id="",
        image_status=post.image_status,
    )
    return update_final_post_copy(state.final_posts_path, post_id=post_id, notes=notes)


def _site_feed(state: DashboardState) -> dict:
    posts = _ensure_image_variants_for_posts(state, load_final_posts(state.final_posts_path))
    site_posts = [
        post for post in posts if post.channel == "site" and post.status in {"scheduled", "published"}
    ]
    site_posts.sort(key=lambda post: post.scheduled_time or post.created_at, reverse=True)
    deduped_posts = []
    seen_keys = set()
    for post in site_posts:
        key = post.source_urls[0] if post.source_urls else post.title.strip().lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_posts.append(post)
    return {
        "brand": "PTIA.pt",
        "updated_at": utc_now_iso(),
        "posts": [
            {
                "id": post.post_id,
                "title": post.title,
                "body": post.body,
                "source_urls": post.source_urls,
                "image_path": post.image_path,
                "image_url": (
                    f"/asset?path={quote(post.image_variants.get('site') or post.image_path)}"
                    if (post.image_variants.get("site") or post.image_path)
                    else ""
                ),
                "published_at": post.published_url or post.scheduled_time or post.created_at,
                "section": _site_section_for_post(post),
            }
            for post in deduped_posts
        ],
    }


def _site_section_for_post(post: FinalPost) -> str:
    text = f"{post.title} {post.body} {' '.join(post.source_urls)}".lower()
    if any(term in text for term in ["chief ai officer", "caio"]):
        return "Histórias reais"
    if any(term in text for term in ["portugal", "portugues", "lisboa", "observador", "jornaleconomico", "grandeconsumo"]):
        return "Portugal"
    if any(term in text for term in ["ai act", "regula", "gdpr", "cnpd", "bruxelas", "european commission"]):
        return "Regulação"
    if any(term in text for term in ["builder", "framework", "github", "developer", "agente", "sdk", "api", "código"]):
        return "Builders"
    if any(term in text for term in ["emprego", "trabalho", "liderança", "empresa"]):
        return "Histórias reais"
    if any(term in text for term in ["futuro", "previs", "próxima", "tendência"]):
        return "Previsões Futuras"
    return "Mundo"


def _write_verified_candidate(
    state: DashboardState,
    *,
    source_type: str,
    source_label: str,
    candidate,
    score: int = 55,
) -> dict | None:
    verification = verify_search_candidate(candidate)
    if verification.status != "verified":
        return None
    signal = add_radar_signal(
        state.radar_signals_path,
        source_type=source_type,
        source_name=verification.source_name,
        title=verification.title or candidate.title,
        url=verification.verified_url or candidate.url,
        published_at=verification.published_at,
        engagement_score=score,
        summary=verification.summary or candidate.summary,
        topic_hint=candidate.title,
        why_it_matters=candidate.why_it_matters,
        why_engaged="",
        notes=f"{source_label}; fonte e data verificadas localmente.",
        status="verified",
        require_recent=True,
    )
    return _to_dict(signal)


def _run_rss_scout(state: DashboardState, *, limit: int = 12) -> dict:
    written: list[dict] = []
    rejected: list[dict] = []
    sources = [
        source
        for source in _load_sources(state.sources_config_path)
        if source.active and source.rss_url.strip()
    ]
    for source in sources:
        if len(written) >= limit:
            break
        try:
            articles = fetch_source(source, limit=4)
        except Exception as exc:  # noqa: BLE001 - keep scout resilient.
            rejected.append({"source": source.name, "status": f"feed_error: {exc}"})
            continue
        for article in articles:
            if len(written) >= limit:
                break
            try:
                signal = add_radar_signal(
                    state.radar_signals_path,
                    source_type="rss_source",
                    source_name=article.source_name,
                    title=article.title_original,
                    url=article.url,
                    published_at=article.published_at,
                    engagement_score=max(45, min(80, source.trust_score * 8)),
                    summary=article.raw_excerpt,
                    topic_hint=source.category,
                    why_it_matters="Sinal recolhido directamente de uma fonte PTIA configurada.",
                    why_engaged="",
                    notes="RSS Scout; fonte configurada e data dos ultimos 5 dias verificada.",
                    status="verified",
                    require_recent=True,
                )
            except Exception as exc:  # noqa: BLE001 - reject old/invalid feed entries.
                rejected.append({"source": source.name, "title": article.title_original, "status": str(exc)})
                continue
            written.append(_to_dict(signal))
    return {"written": written, "rejected": rejected}


def _run_discovery_scout(state: DashboardState, *, source: str, limit: int = 8) -> dict:
    presets = {
        "rundown": {
            "source_name": "The Rundown AI",
            "source_url": "https://www.rundown.ai/articles",
            "focus": "temas quentes de IA global que funcionem para PTIA, sempre com fonte original",
            "score": 58,
        },
        "portugal": {
            "source_name": "fontes portuguesas sobre IA",
            "source_url": "https://www.google.com/search?q=Intelig%C3%AAncia+Artificial+Portugal",
            "focus": "noticias de IA em Portugal, governo, empresas, universidades, startups e regulacao",
            "score": 62,
        },
    }
    config = presets.get(source)
    if not config:
        raise ValueError("Fonte de scout desconhecida.")
    provider = GeminiGroundedSearchProvider()
    candidates = provider.scout_discovery_source(
        source_name=str(config["source_name"]),
        source_url=str(config["source_url"]),
        focus=str(config["focus"]),
        limit=limit,
    )
    written = []
    rejected = []
    for candidate in candidates:
        signal = _write_verified_candidate(
            state,
            source_type=f"{source}_scout",
            source_label=f"{config['source_name']} Scout",
            candidate=candidate,
            score=int(config["score"]),
        )
        if signal:
            written.append(signal)
        else:
            rejected.append({"url": candidate.url, "source": candidate.source_name, "status": "not_verified"})
    return {"written": written, "rejected": rejected}


HTML = r"""<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PTIA Editorial Engine</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@400;500;600&display=swap');
    
    :root {
      /* Background & Panels */
      --bg-blue-1: #0A192F;
      --bg-blue-2: #020C1B;
      --bg-blue-3: #112240;
      --card-cream: #F9F7F1;
      --card-cream-hover: #FFFFFF;
      --card-rail: #EFECE1;
      
      /* Colors */
      --ptia-navy: #051A3B; 
      --ink: #1C1914;
      --ink-light: #4A463F;
      --accent-gold: #C0A062;
      
      /* Semantic */
      --text-main: var(--ink);
      --text-muted: var(--ink-light);
      --line: rgba(5, 26, 59, 0.1);
      --line-dark: rgba(255, 255, 255, 0.1);
      
      --radius: 12px;
      --radius-sm: 6px;
      --shadow-soft: 0 4px 20px rgba(0,0,0,0.06);
      --shadow-dark: 0 10px 40px rgba(0,0,0,0.5);
    }
    
    * { box-sizing: border-box; }
    
    body {
      margin: 0;
      font-family: 'Inter', system-ui, sans-serif;
      background: linear-gradient(135deg, var(--bg-blue-2), var(--bg-blue-1), var(--bg-blue-3));
      background-size: 200% 200%;
      animation: gradientBG 15s ease infinite;
      color: #E0E0E0; 
      min-height: 100vh;
      position: relative;
      -webkit-font-smoothing: antialiased;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      background-image:
        radial-gradient(rgba(255,255,255,0.07) 1px, transparent 1px),
        linear-gradient(120deg, rgba(192,160,98,0.08), transparent 38%, rgba(255,255,255,0.04) 62%, transparent);
      background-size: 32px 32px, 260% 260%;
      opacity: 0.55;
      animation: backgroundDrift 34s linear infinite;
    }
    
    @keyframes gradientBG {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }
    @keyframes movePattern {
      0% { background-position: 0 0; }
      100% { background-position: 20px 20px; }
    }
    @keyframes backgroundDrift {
      0% { background-position: 0 0, 0% 50%; }
      100% { background-position: 32px 32px, 100% 50%; }
    }
    
    /* Headers with Serif */
    h1, h2, h3, .serif {
      font-family: 'Cormorant Garamond', serif;
      font-weight: 600;
    }
    
    header {
      display: flex; justify-content: space-between; gap: 24px; align-items: center;
      padding: 18px 40px;
      background: rgba(2, 12, 27, 0.7);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--line-dark);
      position: sticky; top: 0; z-index: 10;
    }
    header, .wrap { position: relative; z-index: 1; }
    
    h1 { margin: 0; font-size: 28px; color: var(--card-cream); font-weight: 700; letter-spacing: 0.02em; }
    h2 { margin: 0 0 16px; font-size: 22px; color: var(--ptia-navy); }
    h3 { margin: 0 0 12px; font-size: 18px; color: var(--ink); line-height: 1.3; }
    p { margin: 0; }
    
    /* Forms & Buttons */
    button, input, textarea, select {
      font-family: 'Inter', sans-serif; 
      border: 1px solid var(--line);
      border-radius: var(--radius-sm); 
      background: #FFFFFF; 
      color: var(--ink);
      transition: all 0.2s ease;
    }
    input, textarea { width: 100%; padding: 12px 14px; font-size: 14px; }
    textarea { min-height: 90px; resize: vertical; line-height: 1.6; }
    input:focus, textarea:focus { outline: none; border-color: var(--ptia-navy); box-shadow: 0 0 0 3px rgba(5, 26, 59, 0.1); }
    
    button { cursor: pointer; padding: 10px 20px; font-weight: 500; font-size: 13px; letter-spacing: 0.02em; display: inline-flex; align-items: center; justify-content: center; }
    button:hover { transform: translateY(-1px); box-shadow: var(--shadow-soft); }
    button:active { transform: translateY(0); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    
    button.primary { background: var(--ptia-navy); border-color: var(--ptia-navy); color: var(--card-cream); }
    button.primary:hover { background: #0A2B60; }
    button.good { background: #1B4D3E; border-color: #1B4D3E; color: var(--card-cream); }
    button.bad { background: #8B2E2E; border-color: #8B2E2E; color: var(--card-cream); }
    
    .wrap { padding: 40px; max-width: 1500px; margin: 0 auto; }
    
    /* Stats Row (Dark) */
    .stats { display: grid; grid-template-columns: repeat(7, 1fr); gap: 16px; margin-bottom: 32px; }
    .stat {
      padding: 24px 20px; 
      background-color: var(--card-cream);
      background-image: radial-gradient(rgba(192, 160, 98, 0.08) 1px, transparent 1px);
      background-size: 10px 10px;
      animation: movePattern 30s linear infinite;
      border: 1px solid rgba(0,0,0,0.05);
      border-radius: var(--radius); 
      display: flex; flex-direction: column; gap: 8px;
      cursor: pointer; transition: all 0.3s;
      box-shadow: var(--shadow-soft);
    }
    .stat:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.08); }
    .stat.active { 
      border: 4px solid var(--accent-gold); 
      transform: translateY(-4px);
      box-shadow: 0 12px 30px rgba(192, 160, 98, 0.3), inset 0 0 20px rgba(192, 160, 98, 0.15);
    }
    .stat strong { font-family: 'Cormorant Garamond', serif; font-size: 36px; font-weight: 600; line-height: 1; color: var(--text-main); }
    .stat span { color: var(--text-muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; }
    .stat.active strong { color: var(--ptia-navy); }
    .stat.active span { color: var(--accent-gold); font-weight: 800; }
    
    /* Tabs */
    .tabs { 
      display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 32px; padding: 6px; 
      background: rgba(255, 255, 255, 0.08); 
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.2); 
      border-radius: 999px; width: fit-content;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
    }
    .tab { border: 0; background: transparent; color: rgba(255,255,255,0.7); padding: 10px 20px; border-radius: 999px; font-size: 13px; text-shadow: 0 1px 2px rgba(0,0,0,0.2); }
    .tab:hover { color: #ffffff; background: rgba(255,255,255,0.1); }
    .tab.active { background: #ffffff; color: var(--ptia-navy); font-weight: 700; text-shadow: none; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    
    /* Layout Grids */
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
    .radar-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 32px; align-items: start; }
    .quick-stack { display: grid; gap: 24px; }
    
    /* Panels (Cream Reading Areas) */
    .panel, .card, .final-layout {
      background-color: var(--card-cream);
      background-image: radial-gradient(rgba(192, 160, 98, 0.08) 1px, transparent 1px);
      background-size: 10px 10px;
      animation: movePattern 30s linear infinite;
      border: 1px solid rgba(0,0,0,0.05);
      border-radius: var(--radius);
      box-shadow: var(--shadow-soft);
      color: var(--text-main);
    }
    .panel { padding: 32px; }
    
    /* Individual Cards */
    .card { padding: 24px; margin: 0 0 16px; transition: all 0.2s ease; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.08); }
    
    .meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 16px; }
    .pill {
      display: inline-flex; align-items: center; padding: 4px 10px;
      border-radius: 4px; background: var(--card-rail); color: var(--ink-light);
      font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
    }
    
    .text { font-size: 15px; line-height: 1.7; white-space: pre-wrap; color: var(--text-main); }
    
    /* Post Box */
    .final-box { display: grid; grid-template-columns: 1fr 280px; gap: 24px; margin-top: 20px; }
    .post-copy {
      border: 1px solid var(--line);
      background: #FFFFFF;
      border-radius: var(--radius-sm);
      padding: 24px;
      color: var(--ink);
      font-size: 15px;
      line-height: 1.8;
      white-space: pre-wrap;
    }
    .edit-copy { min-height: 360px; font-family: inherit; line-height: 1.65; }
    .compact-input { min-height: 44px; }
    
    .asset-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); gap: 12px; }
    .asset-preview { width: 100%; aspect-ratio: 1/1; border: 1px solid var(--line); border-radius: var(--radius-sm); object-fit: cover; }
    .preview-overlay {
      position: fixed; inset: 0; z-index: 50; display: none; align-items: center; justify-content: center;
      padding: 24px; background: rgba(5, 26, 59, 0.74); backdrop-filter: blur(8px);
    }
    .preview-overlay.open { display: flex; }
    .preview-dialog {
      width: min(980px, 100%); max-height: 92vh; overflow: auto; background: #f8f5ed;
      border: 1px solid rgba(192, 160, 98, 0.45); border-radius: 18px; padding: 18px;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.32);
    }
    .preview-top { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; }
    .social-preview {
      margin: 0 auto; background:#fff; color:#111; border:1px solid #d9d9d9; box-shadow:0 16px 50px rgba(0,0,0,.12);
      font-family: Arial, sans-serif; overflow:hidden;
    }
    .instagram-preview { width:min(430px, 100%); border-radius: 14px; }
    .linkedin-preview { width:min(620px, 100%); border-radius: 10px; }
    .social-header { display:flex; align-items:center; gap:10px; padding:12px 14px; border-bottom:1px solid #eee; }
    .social-avatar { width:36px; height:36px; border-radius:50%; background:#051A3B; color:#c0a062; display:flex; align-items:center; justify-content:center; font-family:Georgia,serif; font-weight:700; }
    .social-name { font-weight:700; font-size:14px; }
    .social-sub { color:#777; font-size:12px; margin-top:2px; }
    .social-image { width:100%; aspect-ratio:1/1; object-fit:cover; background:#f4efe4; border-bottom:1px solid #eee; }
    .linkedin-preview .social-image { aspect-ratio: 1.91/1; }
    .social-body { padding:14px; white-space:pre-wrap; font-size:14px; line-height:1.48; }
    .social-actions { display:flex; gap:22px; padding:11px 14px; border-top:1px solid #eee; color:#666; font-size:13px; }
    .newsletter-layout {
      display: grid;
      grid-template-columns: minmax(360px, 0.44fr) minmax(620px, 0.56fr);
      gap: 32px;
      align-items: start;
      margin-top: 32px;
    }
    .newsletter-list { display: grid; gap: 18px; align-content: start; }
    .newsletter-preview {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: #fffdf7;
      padding: 0;
      overflow: hidden;
      max-height: 780px;
    }
    .newsletter-preview iframe { width: 100%; height: 760px; border: 0; background: #fffdf7; }
    .newsletter-textarea { min-height: 360px; font-family: Consolas, "Liberation Mono", monospace; }
    .newsletter-empty { min-height: 220px; display: grid; align-content: center; }
    
    .label { display: block; margin: 0 0 6px; color: var(--ink-light); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    .hint { margin-top: 8px; color: var(--ink-light); font-size: 12px; line-height: 1.4; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
    .schedule-date-inline { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 10px; background: #fff; color: var(--ink); font-size: 13px; font-weight: 700; }
    .schedule-date-inline input { border: 0; background: transparent; color: var(--ink); font: inherit; min-height: 26px; }
    .schedule-day-pills { display: inline-flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .day-pill { border: 1px solid var(--line); border-radius: 999px; background: #fff; color: var(--ink); padding: 9px 13px; font-size: 12px; font-weight: 800; cursor: pointer; }
    .day-pill.active { background: var(--ink); color: #fff; border-color: var(--ink); }
    .hidden { display: none; }
    
    .two { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .learning-list { display: grid; gap: 16px; }
    .form-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-top: 16px; }
    
    .notice { color: var(--ink-light); font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
    header .notice { color: rgba(255, 255, 255, 0.6); margin-bottom: 0; }
    
    /* Top Header PTIA Mark */
    .header-copy { display: flex; align-items: center; min-width: 0; }
    .header-actions { display: flex; align-items: center; gap: 16px; }
    .header-brand-logo {
      height: 82px;
      width: auto;
      max-width: min(440px, 60vw);
      object-fit: contain;
      border-radius: 0;
      box-shadow: none;
      filter: drop-shadow(0 8px 18px rgba(0,0,0,0.28));
    }
    
    /* Final layout splits */
    .final-layout { display: grid; grid-template-columns: 240px 1fr; gap: 0; overflow: hidden; margin-bottom: 24px; }
    .channel-rail { background: var(--card-rail); border-right: 1px solid var(--line); padding: 32px 24px; }
    .channel-rail h2 { margin-bottom: 24px; color: var(--ptia-navy); }
    .channel-rail button { width: 100%; justify-content: flex-start; text-align: left; margin-bottom: 8px; border: 0; background: transparent; color: var(--ink-light); font-size: 14px; padding: 12px 16px; }
    .channel-rail button:hover { background: rgba(0,0,0,0.04); color: var(--ink); }
    .channel-rail button.active { background: #FFFFFF; color: var(--ptia-navy); font-weight: 600; box-shadow: var(--shadow-soft); }
    .channel-stage { padding: 32px; background: var(--card-cream); }
    
    .channel-grid { display: grid; grid-template-columns: 1fr 340px; gap: 32px; align-items: start; }
    .source-list { margin: 12px 0 0; padding-left: 20px; color: var(--ink-light); font-size: 14px; }
    .hero-note { border-left: 3px solid var(--accent-gold); padding: 16px 20px; background: #FFFFFF; color: var(--ink); margin-bottom: 24px; line-height: 1.6; font-size: 15px; font-style: italic; font-family: 'Cormorant Garamond', serif; }
    
    .contribute-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    
    .workflow-note { 
      background: var(--card-cream); border: 1px dashed rgba(0,0,0,0.15); 
      border-radius: var(--radius); padding: 20px 24px; display: grid; gap: 10px; 
      color: var(--text-main); box-shadow: var(--shadow-soft);
    }
    .workflow-note strong { color: var(--ptia-navy); font-size: 16px; font-family: 'Cormorant Garamond', serif; }
    .workflow-note .notice { color: var(--ink-light) !important; margin-bottom: 0; }
    .workflow-note > p[style], .workflow-note > button.primary { display: none; }

    .source-actions { display: grid; gap: 12px; margin-top: 14px; }
    .source-button {
      width: 100%;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 16px;
      border-radius: var(--radius-sm);
      background: #fff;
      color: var(--ink);
      text-align: left;
    }
    .source-button span { display: block; color: var(--ink-light); font-size: 12px; font-weight: 500; margin-top: 4px; }

    .empty-workflow {
      min-height: 360px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 56px 24px;
    }
    .empty-workflow-inner { max-width: 620px; display: grid; gap: 18px; justify-items: center; }
    .empty-workflow h2 { font-size: 30px; margin-bottom: 0; }
    .steps-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; width: 100%; margin-top: 8px; }
    .step-chip {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      padding: 14px;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.45;
    }

    .published-layout { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 28px; align-items: start; }
    .metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }
    .metric-card { background: #fff; border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 16px; }
    .metric-card strong { display: block; color: var(--ptia-navy); font-size: 22px; font-family: 'Cormorant Garamond', serif; }
    .metric-card span { color: var(--ink-light); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }

    .signal-card { padding: 0; overflow: hidden; }
    .signal-card summary {
      list-style: none;
      cursor: pointer;
      padding: 22px 24px;
      display: grid;
      gap: 12px;
    }
    .signal-card summary::-webkit-details-marker { display: none; }
    .signal-card summary::after {
      content: "Abrir leitura";
      color: var(--ptia-navy);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .signal-card details[open] summary::after { content: "Fechar"; }
    .signal-body {
      border-top: 1px solid var(--line);
      padding: 0 24px 24px;
      display: grid;
      gap: 14px;
    }
    .signal-card > .actions { padding: 0 24px 24px; margin-top: 0; }
    .signal-preview { color: var(--ink-light); font-size: 14px; line-height: 1.55; }
    .signal-title { color: var(--ink); font-size: 18px; margin: 0; line-height: 1.35; }
    .origin-tag {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border: 1px solid rgba(196, 159, 82, 0.38);
      border-radius: 999px;
      background: rgba(196, 159, 82, 0.12);
      color: var(--ptia-navy);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    
    .empty-state { padding: 48px; border: 1px dashed var(--line); border-radius: var(--radius); background: var(--card-rail); color: var(--ink-light); text-align: center; font-size: 15px; }
    
    /* Scheduling */
    .schedule-row { display: grid; grid-template-columns: 160px 1fr auto; gap: 16px; align-items: end; margin-top: 20px; }
    .schedule-board { display: grid; gap: 34px; margin-top: 28px; }
    .slot-row { display: grid; grid-template-columns: 104px repeat(3, minmax(0, 1fr)); gap: 24px; align-items: stretch; }
    
    .slot-time { 
      background: var(--card-cream); border: 1px solid var(--line); color: var(--ptia-navy); 
      border-radius: var(--radius); padding: 20px; font-weight: 600; font-size: 18px; 
      display: flex; align-items: center; justify-content: center; font-family: 'Cormorant Garamond', serif; 
    }
    .slot-card { min-height: 190px; display: flex; flex-direction: column; justify-content: space-between; background: #FFFFFF; margin: 0; }
    .slot-card.empty { background: var(--card-rail); border: 1px dashed rgba(0,0,0,0.1); box-shadow: none; }
    .slot-channel, .channel-pill {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      background: var(--card-rail);
      border: 1px solid var(--line);
      color: var(--ptia-navy);
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .slot-headline { font-weight: 600; line-height: 1.4; margin: 12px 0; color: var(--ink); font-size: 16px; font-family: 'Cormorant Garamond', serif; }
    
    .field { display: grid; gap: 8px; margin-bottom: 20px; }
    .field label { color: var(--ink); font-size: 13px; font-weight: 600; }
    .field small { color: var(--ink-light); font-size: 12px; }
    
    .toast { position: fixed; right: 32px; bottom: 32px; padding: 16px 24px; border-radius: var(--radius-sm); background: var(--ptia-navy); color: #fff; box-shadow: var(--shadow-dark); opacity: 0; transform: translateY(20px); transition: all .4s ease; pointer-events: none; z-index: 100; font-size: 14px; }
    .toast.show { opacity: 1; transform: translateY(0); }
    
    a { color: var(--ptia-navy); text-decoration: underline; text-decoration-color: rgba(5, 26, 59, 0.3); text-underline-offset: 4px; font-weight: 500; transition: all 0.2s; }
    a:hover { color: var(--accent-gold); text-decoration-color: var(--accent-gold); }
    
    @media (max-width: 1200px) {
      .stats { grid-template-columns: repeat(4, 1fr); }
      .grid, .radar-grid { grid-template-columns: 1fr; }
      .two, .final-layout, .channel-grid, .contribute-grid, .slot-row, .newsletter-layout { grid-template-columns: 1fr; }
      .steps-row, .published-layout, .metric-grid { grid-template-columns: 1fr; }
      .final-box, .schedule-row { grid-template-columns: 1fr; }
      .slot-time { height: 80px; }
    }
    @media (max-width: 768px) {
      header { flex-direction: column; align-items: flex-start; }
      .wrap { padding: 24px; }
      .stats { grid-template-columns: repeat(2, 1fr); }
      .form-row { grid-template-columns: 1fr; }
    }
    @media (max-width: 640px) {
      body { overflow-x: hidden; }
      header {
        position: sticky;
        padding: 12px 14px;
        gap: 10px;
      }
      .header-brand-logo {
        height: 54px;
        max-width: 230px;
      }
      .header-actions { width: 100%; }
      .header-actions button { width: 100%; min-height: 46px; }
      .wrap { padding: 18px 14px 40px; }
      .stats {
        display: flex;
        overflow-x: auto;
        gap: 10px;
        padding: 0 0 10px;
        margin-bottom: 18px;
        scroll-snap-type: x mandatory;
      }
      .stat {
        min-width: 132px;
        padding: 18px 14px;
        scroll-snap-align: start;
      }
      .stat strong { font-size: 30px; }
      .tabs {
        width: 100%;
        flex-wrap: nowrap;
        overflow-x: auto;
        border-radius: 18px;
        margin-bottom: 20px;
      }
      .tab {
        min-width: max-content;
        min-height: 44px;
        padding: 10px 16px;
      }
      .panel { padding: 20px; }
      .card { padding: 18px; margin-bottom: 14px; }
      .grid, .two, .radar-grid, .channel-grid, .contribute-grid,
      .final-box, .schedule-row, .published-layout, .metric-grid,
      .newsletter-layout {
        grid-template-columns: 1fr;
        gap: 16px;
      }
      .quick-stack { gap: 16px; }
      input, textarea, select { font-size: 16px; min-height: 46px; }
      button { min-height: 44px; }
      .actions { display: grid; grid-template-columns: 1fr; gap: 10px; }
      .actions button, .actions a { width: 100%; justify-content: center; text-align: center; }
      .final-layout { display: block; overflow: visible; }
      .channel-rail {
        border-right: 0;
        border-bottom: 1px solid var(--line);
        padding: 18px;
      }
      .channel-rail button { justify-content: center; text-align: center; }
      .channel-stage { padding: 18px; }
      .slot-row {
        grid-template-columns: 1fr;
        gap: 12px;
        margin-bottom: 26px;
      }
      .slot-time { height: auto; min-height: 54px; }
      .slot-card { min-height: 170px; }
      .post-copy { padding: 16px; font-size: 14px; line-height: 1.65; }
      .asset-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .toast {
        left: 14px;
        right: 14px;
        bottom: 16px;
        text-align: center;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-copy">
      <img src="/asset?path=data/ptia-logo-cutout.png" class="header-brand-logo" alt="PTIA" />
    </div>
    <div class="header-actions">
      <button class="primary" onclick="loadState()">Atualizar</button>
    </div>
  </header>
  <main class="wrap">
    <section class="stats" id="stats"></section>
    <nav class="tabs">
      <button class="tab active" data-tab="flow" onclick="showTab('flow')">1 Radar</button>
      <button class="tab" data-tab="verifying_tab" onclick="showTab('verifying_tab')">2 Verifying</button>
      <button class="tab" data-tab="verified_tab" onclick="showTab('verified_tab')">3 Verified Selection</button>
      <button class="tab" data-tab="final_draft_pack" onclick="showTab('final_draft_pack')">4 A Rever</button>
      <button class="tab" data-tab="schedule" onclick="showTab('schedule')">5 Final OK</button>
      <button class="tab" data-tab="scheduled_tab" onclick="showTab('scheduled_tab')">6 Scheduled</button>
      <button class="tab" data-tab="published_tab" onclick="showTab('published_tab')">7 Published</button>
      <button class="tab" data-tab="newsletter_tab" onclick="showTab('newsletter_tab')">8 Newsletter</button>
      <button class="tab" data-tab="growth_tab" onclick="showTab('growth_tab')">9 Growth</button>
    </nav>
    <section id="flow" class="tab-panel"></section>
    <section id="verifying_tab" class="tab-panel hidden"></section>
    <section id="verified_tab" class="tab-panel hidden"></section>
    <section id="topics_v2" class="tab-panel hidden"></section>
    <section id="final_draft_pack" class="tab-panel hidden"></section>
    <section id="final_posts_v2" class="tab-panel hidden"></section>
    <section id="review" class="tab-panel hidden"></section>
    <section id="trends" class="tab-panel hidden"></section>
    <section id="drafts" class="tab-panel hidden"></section>
    <section id="assets" class="tab-panel hidden"></section>
    <section id="schedule" class="tab-panel hidden"></section>
    <section id="scheduled_tab" class="tab-panel hidden"></section>
    <section id="published_tab" class="tab-panel hidden"></section>
    <section id="newsletter_tab" class="tab-panel hidden"></section>
    <section id="growth_tab" class="tab-panel hidden"></section>
    <section id="performance" class="tab-panel hidden"></section>
    <section id="learnings" class="tab-panel hidden"></section>
  </main>
  <div id="preview_overlay" class="preview-overlay" onclick="closeSocialPreview(event)">
    <div class="preview-dialog" onclick="event.stopPropagation()">
      <div class="preview-top">
        <strong>Preview</strong>
        <button onclick="closeSocialPreview()">Fechar</button>
      </div>
      <div id="preview_content"></div>
    </div>
  </div>
  <div id="toast" class="toast"></div>
  <script>
    let state = {};
    let activeFinalChannel = 'linkedin';
    let activeFinalTopicId = '';
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const short = (value, max = 340) => {
      const text = String(value ?? '');
      return text.length > max ? text.slice(0, max).trim() + '...' : text;
    };
    function showTab(id) {
      document.querySelectorAll('.tab-panel').forEach(el => el.classList.add('hidden'));
      document.getElementById(id).classList.remove('hidden');
      document.querySelectorAll('.tab').forEach(el => el.classList.toggle('active', el.dataset.tab === id));
      if (state.counts) renderStats();
    }
    async function api(path, payload) {
      const response = await fetch(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const raw = await response.text();
        let message = raw;
        try {
          const parsed = JSON.parse(raw);
          message = parsed.error || raw;
        } catch (_) {}
        showToast('Erro: ' + message);
        throw new Error(message);
      }
      await loadState();
    }
    function showToast(message) {
      const toast = document.getElementById('toast');
      toast.textContent = message;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2600);
    }
    async function loadState() {
      const response = await fetch('/api/state');
      state = await response.json();
      render();
    }
    function renderStats() {
      const c = state.counts || {};
      const stats = [
        ['Radar', c.radar_signals_v2, 'flow'],
        ['Verifying', c.verifying, 'verifying_tab'],
        ['Verified Selection', c.verified_selection, 'verified_tab'],
        ['A Rever', c.a_rever, 'final_draft_pack'],
        ['Final OK', c.final_approved, 'schedule'],
        ['Scheduled', c.final_scheduled, 'scheduled_tab'],
        ['Published', c.final_published, 'published_tab'],
        ['Newsletter', c.newsletter_drafts, 'newsletter_tab'],
        ['Growth', state.growth?.boost_candidates?.length || 0, 'growth_tab'],
      ];
      const activeId = document.querySelector('.tab.active')?.dataset.tab || 'flow';
      document.getElementById('stats').innerHTML = stats.map(([label, value, tabId]) => `
        <button class="stat ${activeId === tabId ? 'active' : ''}" onclick="showTab('${tabId}')"><strong>${esc(value || 0)}</strong><span>${esc(label)}</span></button>
      `).join('');
    }
    function card(title, meta, text, actions = '') {
      return `<article class="card"><h3>${esc(title)}</h3><div class="meta">${meta}</div><p class="text">${esc(short(text))}</p>${actions}</article>`;
    }
    function pill(value) { return `<span class="pill">${esc(value)}</span>`; }
    function renderFlow() {
      const c = state.counts || {};
      document.getElementById('flow').innerHTML = `
        <div class="radar-grid">
          <div class="quick-stack">
            <form class="panel" onsubmit="submitQuickCapture(event)">
              <h2>Capturar sinal</h2>
              <p class="notice" style="margin-bottom:12px">Cola um link. O engine pesquisa a notícia, encontra fonte credível, valida data dos últimos 5 dias e só depois deixa entrar.</p>
              <div class="field"><label>Link</label><input id="quick_link" placeholder="https://..."></div>
              <button class="primary" type="submit">Pesquisar fonte</button>
            </form>
            <form class="panel" onsubmit="submitQuickCapture(event)">
              <h2>Guardar pensamento</h2>
              <p class="notice" style="margin-bottom:12px">Ideias tuas ficam como matéria-prima editorial. Não passam para notícia sem fonte.</p>
              <div class="field"><label>Pensamento</label><textarea id="quick_thought" placeholder="Ex: Este tema parece forte para PME portuguesas porque..."></textarea></div>
              <button class="good" type="submit">Guardar pensamento</button>
            </form>
          </div>
          <aside class="workflow-note">
            <strong>Gerar radar</strong>
            <p class="notice">Escolhe a origem. Tudo tem de passar por fonte credÃ­vel e data dos Ãºltimos 5 dias antes de entrar em Verified Selection.</p>
            <div class="source-actions">
              <button class="source-button" onclick="runGeminiScout()">Gemini Scout <span>Panorama global + Portugal, com fontes verificadas.</span></button>
              <button class="source-button" onclick="runSourceScout('rss')">Fontes PTIA RSS <span>OpenAI, Google, Microsoft, NVIDIA, MIT, The Decoder e outras fontes configuradas.</span></button>
              <button class="source-button" onclick="runSourceScout('rundown')">The Rundown AI <span>Usa como descoberta; procura a fonte original antes de aprovar.</span></button>
              <button class="source-button" onclick="runSourceScout('portugal')">Radar Portugal <span>Procura IA em Portugal: governo, empresas, universidades e regulaÃ§Ã£o.</span></button>
            </div>
            <p class="notice" style="color:#cbd5e1">3. Revês LinkedIn, Instagram e Site.</p>
            <p class="notice" style="color:#cbd5e1">4. Defines hora em Final OK e marcas scheduled.</p>
            <button class="primary" onclick="runGeminiScout()">Gemini Scout hoje</button>
          </aside>
        </div>
        <div class="grid" style="margin-top:14px">
          <div class="panel"><h2>Verifying</h2><div class="meta">${pill(c.verifying || 0)}</div><p class="notice">Links em pesquisa de fonte credível.</p><div class="actions"><button onclick="showTab('verifying_tab')">Abrir</button></div></div>
          <div class="panel"><h2>Verified Selection</h2><div class="meta">${pill(c.verified_selection || 0)}</div><p class="notice">Escolhe 3-4 por dia para criar pacote final.</p><div class="actions"><button onclick="showTab('verified_tab')">Selecionar</button></div></div>
          <div class="panel"><h2>A Rever</h2><div class="meta">${pill(c.a_rever || 0)}</div><p class="notice">Final drafts por Instagram, LinkedIn e Site.</p><div class="actions"><button onclick="showTab('final_draft_pack')">Rever</button></div></div>
        </div>
        <div class="panel" style="margin-top:14px">
          <h2>Radar inbox</h2>
          <p class="notice" style="margin-bottom:12px">Estes são os sinais que o contador do Radar está a contar. Usados e rejeitados saem daqui.</p>
          ${renderSignalList(state.radar_inbox_signals || [], 'Radar limpo. Corre Gemini Scout ou cola um link para alimentar a inbox.', 'radar')}
        </div>
      `;
    }
    function renderSignalList(signals, empty, mode = 'radar') {
      return signals.map(signal => signalCard(signal, mode)).join('') || `<p class="notice">${empty}</p>`;
    }
    function sourceOriginLabel(signal) {
      const type = signal.source_type || '';
      if (type === 'rss_source') return 'Fontes PTIA RSS';
      if (type === 'gemini_scout') return 'Gemini Scout';
      if (type === 'rundown_scout') return 'The Rundown AI';
      if (type === 'portugal_scout') return 'Radar Portugal';
      if (type === 'news') return 'Link teu';
      if (type === 'thought') return 'Pensamento teu';
      return type || 'Origem desconhecida';
    }
    function signalCard(signal, mode = 'radar') {
      const isVerified = signal.status === 'verified' || signal.status === 'verified_secondary';
      const isSelected = signal.status === 'selected';
      const canVerify = mode === 'radar' && !isVerified && !isSelected && signal.status !== 'verifying';
      const verifyLabel = signal.status === 'verifying' ? 'Pesquisar fonte' : 'Mandar verificar';
      const actions = `
        <div class="actions">
          ${mode === 'verifying' || signal.status === 'verifying' || canVerify ? `<button class="primary" onclick="api('/api/reverify-signal',{signal_id:'${esc(signal.signal_id)}'})">${verifyLabel}</button>` : ''}
          ${mode === 'radar' && isVerified ? `<button class="good" onclick="api('/api/signal-status',{signal_id:'${esc(signal.signal_id)}',status:'selected',notes:'Escolhido para curadoria'})">Escolher para hoje</button>` : ''}
          ${mode === 'radar' && isSelected ? `<button class="primary" onclick="buildFinalPack('${esc(signal.signal_id)}')">Criar pacote final</button>` : ''}
          ${mode === 'verified' && !isSelected ? `<button class="good" onclick="api('/api/signal-status',{signal_id:'${esc(signal.signal_id)}',status:'selected',notes:'Escolhido para curadoria'})">Escolher para hoje</button>` : ''}
          ${mode === 'verified' && isSelected ? `<button class="primary" onclick="buildFinalPack('${esc(signal.signal_id)}')">Criar pacote final</button>` : ''}
          <button class="bad" onclick="api('/api/signal-status',{signal_id:'${esc(signal.signal_id)}',status:'rejected',notes:'Fora da linha editorial'})">Rejeitar</button>
          <a href="${esc(signal.url)}" target="_blank">Fonte</a>
        </div>`;
      return `<article class="card signal-card">
        <details>
        <summary>
          <span class="origin-tag">${esc(sourceOriginLabel(signal))}</span>
          <h3 class="signal-title">${esc(signal.title)}</h3>
          <div class="meta">${pill(signal.source_name)}${pill(`eng ${signal.engagement_score}`)}${pill(signal.status)}</div>
          <p class="signal-preview">${esc(signal.summary || signal.notes || 'Sem resumo ainda.')}</p>
        </summary>
        <div class="signal-body">
          <p class="text">${esc(signal.summary || signal.notes || '')}</p>
          <p class="text">${esc(signal.why_it_matters || 'Ainda sem leitura editorial.')}</p>
          <p class="text"><strong>Notas:</strong> ${esc(signal.notes || 'Sem notas.')}</p>
        </div>
        </details>
        ${actions}
      </article>`;
    }
    function renderVerifying() {
      document.getElementById('verifying_tab').innerHTML = `
        <div class="panel"><h2>Verifying</h2><p class="notice">Links teus que o engine ainda está a tentar validar. Se não houver fonte credível/data, não passa.</p></div>
        ${renderSignalList(state.verifying_signals || [], 'Nada em verificação.', 'verifying')}
      `;
    }
    function renderVerified() {
      const verified = [...(state.verified_signals || []), ...(state.selected_signals || [])];
      document.getElementById('verified_tab').innerHTML = `
        <div class="panel"><h2>Verified Selection</h2><p class="notice">Só entram fontes credíveis. Selecciona 3-4 por dia para curadoria.</p></div>
        ${renderSignalList(verified, 'Ainda sem fontes verificadas.', 'verified')}
      `;
    }
    function val(id) { return document.getElementById(id)?.value.trim() || ''; }
    async function submitQuickCapture(event) {
      event.preventDefault();
      await api('/api/quick-capture', {
        link: val('quick_link'),
        thought: val('quick_thought')
      });
      showToast('Guardado no Radar');
      document.getElementById('quick_link').value = '';
      document.getElementById('quick_thought').value = '';
      showTab('flow');
    }
    async function runGeminiScout() {
      showToast('Gemini Scout a pesquisar...');
      await api('/api/gemini-scout', {limit: 8});
      showToast('Gemini Scout concluído');
      showTab('verified_tab');
    }
    async function runSourceScout(source) {
      const labels = {rss: 'Fontes RSS', rundown: 'The Rundown AI', portugal: 'Radar Portugal'};
      showToast(`${labels[source] || 'Fonte'} a pesquisar...`);
      await api('/api/source-scout', {source, limit: 8});
      showToast(`${labels[source] || 'Fonte'} concluido`);
      showTab('verified_tab');
    }
    async function buildFinalPack(signalId) {
      await api('/api/build-final-pack', {signal_id: signalId});
      showToast('Pacote final criado');
      showTab('final_draft_pack');
    }
    async function approveFinalPackage(postId) {
      showToast('A alinhar e enviar o pacote para Final OK...');
      const feedback = val(`rewrite_${postId}`) || 'LinkedIn aprovado como canal principal. Ajusta Instagram e Site para ficarem coerentes, sem obrigar a mesma estrutura.';
      await api('/api/rewrite-final-package', {post_id: postId, feedback});
      await api('/api/approve-final-package', {post_id: postId});
      showToast('Pacote enviado para Final OK');
      showTab('schedule');
    }
    async function rewriteFinalPost(postId) {
      const feedback = val(`rewrite_${postId}`);
      if (!feedback) {
        showToast('Escreve primeiro o que queres melhorar');
        return;
      }
      showToast('A reescrever este canal...');
      await api('/api/rewrite-final-post', {post_id: postId, feedback});
      showToast('Draft reescrito');
      showTab('final_draft_pack');
    }
    async function rewriteFinalPackage(postId) {
      const feedback = val(`rewrite_${postId}`);
      if (!feedback) {
        showToast('Escreve primeiro o que queres melhorar');
        return;
      }
      showToast('A alinhar os 3 canais do pacote...');
      await api('/api/rewrite-final-package', {post_id: postId, feedback});
      showToast('Pacote alinhado');
      showTab('final_draft_pack');
    }
    async function polishFinalPost(postId) {
      showToast('A aplicar polish PT-PT...');
      await api('/api/polish-final-post', {post_id: postId});
      showToast('Polish PT-PT aplicado');
      showTab('final_draft_pack');
    }
    async function generateFinalImage(postId) {
      const feedback = val(`image_feedback_${postId}`);
      const promptField = document.getElementById(`edit_image_prompt_${postId}`);
      if (feedback && promptField) {
        promptField.value = `${promptField.value}\n\nPedido adicional do editor: ${feedback}`;
        await saveFinalPostCopy(postId, false, false);
      }
      await navigator.clipboard.writeText(promptField ? promptField.value : '');
      showToast('Prompt copiado. Gera no ChatGPT Images/Nano Banana e carrega aqui a imagem final.');
    }
    function openImageGenerator() {
      window.open('https://chatgpt.com/', '_blank');
    }
    function uploadFinalImage(postId, input) {
      const file = input.files && input.files[0];
      if (!file) return;
      if (!file.type.startsWith('image/')) {
        showToast('Ficheiro invalido. Usa PNG, JPG ou WebP.');
        return;
      }
      const reader = new FileReader();
      reader.onload = async () => {
        showToast('A carregar imagem final...');
        await api('/api/upload-final-image', {post_id: postId, filename: file.name, data_url: reader.result});
        showToast('Imagem carregada');
        showTab('final_draft_pack');
      };
      reader.readAsDataURL(file);
    }
    async function approveFinalImage(postId) {
      await api('/api/final-image-status', {post_id: postId, image_status: 'approved'});
      showToast('Imagem aprovada');
      showTab('final_draft_pack');
    }
    async function submitTopicThought(event) {
      event.preventDefault();
      await api('/api/add-topic', {
        title: val('topic_title'),
        thesis: val('topic_thesis'),
        portugal_angle: val('topic_portugal'),
        audience: val('topic_audience') || 'PTIA',
        signal_ids: val('topic_signals'),
        urgency_score: 7
      });
      showToast('Topic guardado');
      showTab('topics_v2');
    }
    function renderTopicsV2() {
      const topics = state.editorial_topics || [];
      document.getElementById('topics_v2').innerHTML = `
        <div class="panel"><h2>Topics a curar</h2><p class="notice">Aqui escolhemos os 5-10 temas. Um topic pode combinar varias fontes e sinais sociais.</p></div>
        ${topics.map(topic => card(
          topic.title,
          `${pill(topic.status)}${pill(`urg ${topic.urgency_score}`)}${pill(topic.audience)}`,
          `${topic.thesis}\n\nAngulo Portugal: ${topic.portugal_angle}\n\nSinais:\n${(topic.signals || []).map(s => `- ${s.source_name}: ${s.title}`).join('\n')}`,
          `<div class="actions">
            <button class="good" onclick="api('/api/topic-status',{topic_id:'${esc(topic.topic_id)}',status:'approved_for_final',notes:'Aprovado para post final'})">Aprovar topic</button>
            <button class="bad" onclick="api('/api/topic-status',{topic_id:'${esc(topic.topic_id)}',status:'rejected',notes:'Rejeitado'})">Rejeitar</button>
          </div>`
        )).join('') || '<div class="panel"><p class="notice">Sem topics ainda.</p></div>'}
      `;
    }
    function renderFinalPostsV2() {
      const posts = (state.final_posts || []).filter(post => post.status === 'needs_final_review');
      const postsByTopic = new Set((state.final_posts || []).map(post => post.topic_id));
      const approvedTopicsWithoutPost = (state.editorial_topics || []).filter(
        topic => topic.status === 'approved_for_final' && !postsByTopic.has(topic.topic_id)
      );
      document.getElementById('final_posts_v2').innerHTML = `
        <div class="panel"><h2>Post final para aprovacao</h2><p class="notice">Tem de estar 100% PT-PT, com fontes, hashtags e prompt/imagem. Se estiver medio, rejeitamos.</p></div>
        ${approvedTopicsWithoutPost.length ? `<div class="panel"><h2>Topics aprovados sem post final</h2><p class="notice">Estes topics ja passaram no primeiro check, mas ainda precisam de escrita final.</p>${approvedTopicsWithoutPost.map(topic => card(
          topic.title,
          `${pill(topic.status)}${pill(topic.audience)}${pill(`urg ${topic.urgency_score}`)}`,
          `${topic.thesis}\n\nAngulo Portugal: ${topic.portugal_angle}`
        )).join('')}</div>` : ''}
        ${posts.map(finalPostCard).join('') || '<div class="panel"><p class="notice">Sem posts finais para rever.</p></div>'}
      `;
    }
    function finalPostText(post) {
      const hashtags = post.hashtags ? `\n\n${post.hashtags}` : '';
      const sources = (post.source_urls || []).length ? `\n\nFontes:\n${post.source_urls.map(url => `- ${url}`).join('\n')}` : '';
      return `${post.body}${hashtags}${sources}`.trim();
    }
    function socialText(post) {
      const hashtags = post.hashtags ? `\n\n${post.hashtags}` : '';
      return `${post.body || ''}${hashtags}`.trim();
    }
    function findFinalPost(postId) {
      return (state.final_posts || []).find(post => post.post_id === postId);
    }
    function copyFinalPost(postId) {
      const post = findFinalPost(postId);
      if (!post) return;
      navigator.clipboard.writeText(finalPostText(post));
    }
    async function saveFinalPostCopy(postId, syncPackage = false, showSavedToast = true) {
      const payload = {
        post_id: postId,
        title: val(`edit_title_${postId}`),
        body: val(`edit_body_${postId}`),
        hashtags: val(`edit_hashtags_${postId}`),
        image_prompt: val(`edit_image_prompt_${postId}`),
        sync_topic: syncPackage,
      };
      await api('/api/update-final-post-copy', payload);
      if (showSavedToast) showToast(syncPackage ? 'Alterações guardadas e pacote alinhado' : 'Alterações guardadas');
      showTab('final_draft_pack');
    }
    function socialPreviewMarkup(post) {
      if (post.channel === 'site') {
        return `<article class="social-preview linkedin-preview">
          <div class="social-header">
            <div class="social-avatar">P</div>
            <div><div class="social-name">PTIA.pt</div><div class="social-sub">Preview artigo no site</div></div>
          </div>
          <div class="social-body">
            <h2 style="font-family:Georgia,serif;font-size:28px;line-height:1.1;margin:0 0 14px;color:#051A3B">${esc(post.title)}</h2>
            ${esc(post.body || '')}
          </div>
        </article>`;
      }
      const isLinkedin = post.channel === 'linkedin';
      const typeClass = isLinkedin ? 'linkedin-preview' : 'instagram-preview';
      const imagePath = channelImagePath(post);
      const image = imagePath
        ? `<img class="social-image" src="${assetPath(imagePath)}" alt="">`
        : `<div class="social-image" style="display:grid;place-items:center;color:#777;font-size:13px;">Sem imagem final</div>`;
      const sub = isLinkedin ? 'PTIA Portugal · LinkedIn' : 'ptia.pt · Instagram';
      const actions = isLinkedin ? 'Gosto · Comentar · Repostar · Enviar' : 'Gosto · Comentar · Enviar · Guardar';
      return `<article class="social-preview ${typeClass}">
        <div class="social-header">
          <div class="social-avatar">P</div>
          <div><div class="social-name">PTIA</div><div class="social-sub">${sub}</div></div>
        </div>
        ${image}
        <div class="social-body">${esc(socialText(post))}</div>
        <div class="social-actions">${actions}</div>
      </article>`;
    }
    function openSocialPreview(postId) {
      const post = findFinalPost(postId);
      if (!post) return;
      document.getElementById('preview_content').innerHTML = socialPreviewMarkup(post);
      document.getElementById('preview_overlay').classList.add('open');
    }
    function closeSocialPreview(event) {
      if (event && event.target.id !== 'preview_overlay') return;
      document.getElementById('preview_overlay').classList.remove('open');
    }
    function channelImagePath(post) {
      const variants = post.image_variants || {};
      return variants[post.channel] || post.image_path || '';
    }
    function finalPostCard(post) {
      const imagePath = channelImagePath(post);
      const image = imagePath
        ? `<img class="asset-preview" src="${assetPath(imagePath)}" alt="">`
        : `<div class="post-copy">${esc(post.image_prompt || 'Sem prompt de imagem.')}</div>`;
      return `<article class="card">
        <h3>${esc(post.title)}</h3>
        <div class="meta">${pill(post.channel)}${pill(post.status)}</div>
        <div class="final-box">
          <div><span class="label">Texto final</span><div class="post-copy">${esc(finalPostText(post))}</div></div>
          <div><span class="label">Imagem / prompt</span>${image}</div>
        </div>
        <div class="actions">
          <button onclick="copyFinalPost('${esc(post.post_id)}')">Copiar texto</button>
          <button class="good" onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'approved_for_schedule'})">Submeter para Final OK</button>
          <button class="bad" onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'rejected'})">Rejeitar</button>
        </div>
      </article>`;
    }
    function assetPath(path) { return `/asset?path=${encodeURIComponent(path)}`; }
    function packageTopicIds(posts) {
      return [...new Set(posts.map(post => post.topic_id || 'no_topic'))];
    }
    function packageLabel(topicId, posts) {
      const first = posts.find(post => (post.topic_id || 'no_topic') === topicId) || {};
      return first.title || 'Pacote sem titulo';
    }
    function preferredFinalPosts(topicId = '') {
      const allPosts = (state.final_posts || []).filter(post => post.status === 'needs_final_review');
      const topicIds = packageTopicIds(allPosts);
      const selectedTopicId = topicId || activeFinalTopicId || topicIds[0] || '';
      const posts = selectedTopicId
        ? allPosts.filter(post => (post.topic_id || 'no_topic') === selectedTopicId)
        : allPosts;
      const bestByChannel = {};
      posts.forEach(post => {
        const current = bestByChannel[post.channel];
        if (!current) bestByChannel[post.channel] = post;
      });
      return bestByChannel;
    }
    function setFinalPackage(topicId) {
      activeFinalTopicId = topicId;
      renderFinalDraftPack();
    }
    function setFinalChannel(channel) {
      activeFinalChannel = channel;
      renderFinalDraftPack();
    }
    function renderFinalDraftPack() {
      const reviewPosts = (state.final_posts || []).filter(post => post.status === 'needs_final_review');
      const topicIds = packageTopicIds(reviewPosts);
      if (topicIds.length && !topicIds.includes(activeFinalTopicId)) {
        activeFinalTopicId = topicIds[0];
      }
      const posts = preferredFinalPosts(activeFinalTopicId);
      const channels = [
        ['linkedin', 'LinkedIn', 'Post de autoridade e discussão'],
        ['instagram', 'Instagram', 'Legenda guardável e visual'],
        ['site', 'Site', 'Entrada curta com arquivo e fontes']
      ];
      if (posts.linkedin && !posts[activeFinalChannel]) {
        activeFinalChannel = 'linkedin';
      }
      if (!posts.linkedin && !posts.instagram && !posts.site) {
        document.getElementById('final_draft_pack').innerHTML = `
          <section class="panel empty-workflow">
            <div class="empty-workflow-inner">
              <h2>Ainda nao ha pacote para rever</h2>
              <p class="notice">Este ecran so deve aparecer depois de escolheres uma noticia em Verified Selection e criares o pacote final. Aqui revemos LinkedIn, Instagram e Site, reescrevemos se necessario e submetemos para Final OK.</p>
              <div class="steps-row">
                <div class="step-chip"><strong>1</strong><br>Vai a Verified Selection</div>
                <div class="step-chip"><strong>2</strong><br>Escolhe uma noticia verificada</div>
                <div class="step-chip"><strong>3</strong><br>Carrega Criar pacote final</div>
              </div>
              <div class="actions">
                <button class="primary" onclick="showTab('verified_tab')">Ir para Verified Selection</button>
                <button onclick="showTab('flow')">Voltar ao Radar</button>
              </div>
            </div>
          </section>
        `;
        return;
      }
      const active = posts[activeFinalChannel] || posts.linkedin || posts.instagram || posts.site;
      const rail = channels.map(([key, label, desc]) => `
        <button class="${key === activeFinalChannel ? 'active' : ''}" onclick="setFinalChannel('${key}')">
          ${label}<br><span class="notice">${desc}</span>
        </button>
      `).join('');
      const stage = active ? finalDraftStage(active) : '<p class="notice">Ainda nao ha drafts finais para os 3 canais.</p>';
      const packageSwitcher = topicIds.length > 1 ? `
        <div class="panel package-switcher">
          <span class="label">Pacotes em revisao</span>
          <div class="actions" style="margin-top:10px">
            ${topicIds.map((topicId, index) => `<button class="${topicId === activeFinalTopicId ? 'primary' : ''}" onclick="setFinalPackage('${esc(topicId)}')">${index + 1}. ${esc(short(packageLabel(topicId, reviewPosts), 54))}</button>`).join('')}
          </div>
        </div>
      ` : '';
      document.getElementById('final_draft_pack').innerHTML = `
        ${packageSwitcher}
        <div class="final-layout">
          <aside class="channel-rail">
            <h2>Pacote final</h2>
            <p class="notice" style="margin-bottom:14px;color:#cbd5e1">Revê o produto final por canal antes de submeter para Final OK.</p>
            ${rail}
          </aside>
          <section class="channel-stage">${stage}</section>
        </div>
        <div class="grid">
          ${channels.map(([key, label]) => summaryMini(label, posts[key])).join('')}
        </div>
      `;
    }
    function finalDraftStage(post) {
      const imagePath = channelImagePath(post);
      const variantLabel = post.image_variants?.[post.channel] ? `Imagem formatada para ${post.channel}` : 'Imagem original';
      const image = imagePath
        ? `<a href="${assetPath(imagePath)}" target="_blank"><img class="asset-preview" src="${assetPath(imagePath)}" alt=""></a><div class="hint">${esc(variantLabel)}</div>`
        : `<div class="post-copy">${esc(post.image_prompt || 'Sem imagem/prompt.')}</div>`;
      return `<div class="hero-note">Fonte obrigatoriamente datada dos ultimos 5 dias. Este pacote ainda precisa do teu check final antes de entrar em Final OK.</div>
        <h2>${esc(post.title)}</h2>
        <div class="meta">${pill(post.channel)}${pill(post.status)}${post.editor_notes && post.editor_notes.includes('PT-PT') ? pill('PT-PT polish') : ''}${pill('imagem ' + (post.image_status || 'needs_review'))}${pill((post.source_urls || []).length + ' fonte(s)')}</div>
        <div class="channel-grid">
          <div>
            <span class="label">Texto pronto a usar</span>
            <div class="field">
              <label>Título</label>
              <input class="compact-input" id="edit_title_${esc(post.post_id)}" value="${esc(post.title)}">
            </div>
            <div class="field" style="margin-top:12px">
              <label>Texto editável</label>
              <textarea class="edit-copy" id="edit_body_${esc(post.post_id)}">${esc(post.body || '')}</textarea>
            </div>
            <div class="field" style="margin-top:12px">
              <label>Hashtags</label>
              <input class="compact-input" id="edit_hashtags_${esc(post.post_id)}" value="${esc(post.hashtags || '')}">
            </div>
            <div class="field" style="margin-top:12px">
              <label>O que queres melhorar?</label>
              <textarea id="rewrite_${esc(post.post_id)}" placeholder="Ex: demasiado genérico; quero mais ponto de vista, menos corporate, abertura mais forte..."></textarea>
            </div>
            <div class="actions">
              <button class="good" onclick="saveFinalPostCopy('${esc(post.post_id)}')">Guardar edição</button>
              <button class="primary" onclick="saveFinalPostCopy('${esc(post.post_id)}', true)">Guardar e alinhar pacote</button>
              <button onclick="copyFinalPost('${esc(post.post_id)}')">Copiar texto</button>
              <button onclick="polishFinalPost('${esc(post.post_id)}')">Polir PT-PT</button>
              <button class="primary" onclick="rewriteFinalPost('${esc(post.post_id)}')">Reescrever este canal</button>
              <button class="primary" onclick="rewriteFinalPackage('${esc(post.post_id)}')">Reescrever pacote</button>
              <button class="good" onclick="approveFinalPackage('${esc(post.post_id)}')">OK LinkedIn → Final OK</button>
              <button class="bad" onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'rejected'})">Rejeitar</button>
            </div>
          </div>
          <aside>
            <span class="label">Imagem final</span>
            ${image}
            <div class="field" style="margin-top:12px">
              <label>Feedback de imagem</label>
              <textarea id="image_feedback_${esc(post.post_id)}" placeholder="Ex: mais premium, menos texto, incluir simbolo Claude, mais contraste, sem pessoas..."></textarea>
            </div>
            <div class="actions">
              <button onclick="openImageGenerator()">Abrir ChatGPT Images</button>
              <button class="primary" onclick="generateFinalImage('${esc(post.post_id)}')">Copiar prompt imagem</button>
              <button class="good" onclick="approveFinalImage('${esc(post.post_id)}')">Aprovar imagem</button>
            </div>
            <div class="field" style="margin-top:12px">
              <label>Carregar imagem final gerada fora</label>
              <input type="file" accept="image/png,image/jpeg,image/webp" onchange="uploadFinalImage('${esc(post.post_id)}', this)">
            </div>
            <span class="label" style="margin-top:12px">Prompt</span>
            <textarea class="edit-copy" id="edit_image_prompt_${esc(post.post_id)}" style="min-height:130px">${esc(post.image_prompt)}</textarea>
            <span class="label" style="margin-top:12px">Fontes</span>
            <ul class="source-list">${(post.source_urls || []).map(url => `<li><a href="${esc(url)}" target="_blank">${esc(url)}</a></li>`).join('')}</ul>
            ${post.editor_notes ? `<span class="label" style="margin-top:12px">Notas de edição</span><div class="post-copy">${esc(post.editor_notes)}</div>` : ''}
          </aside>
        </div>`;
    }
    function summaryMini(label, post) {
      if (!post) return `<div class="panel"><h2>${esc(label)}</h2><p class="notice">Ainda sem draft final.</p></div>`;
      return `<div class="panel"><h2>${esc(label)}</h2><div class="meta">${pill(post.status)}</div><p class="text">${esc(short(post.title + '\\n\\n' + post.body, 220))}</p></div>`;
    }
    function renderReview() {
      const items = state.review_items || [];
      document.getElementById('review').innerHTML = `
        <div class="panel"><h2>Check 1: artigo para processar</h2><p class="notice">Aqui decides se a noticia merece passar para o motor de drafts. A aprovacao aqui ainda nao cria schedule nem publicacao.</p></div>
        ${items.map(item => card(
          item.title_original,
          `${pill(item.section)}${pill(item.source_name)}${pill(`rel ${item.relevance_score}/10`)}${pill(`PT ${item.portugal_relevance_score}/10`)}`,
          `${item.reason}\n\n${item.risk_notes}`,
          `<div class="actions">
            <button class="good" onclick="api('/api/item-status',{item_id:'${esc(item.item_id)}',status:'approved_for_draft',notes:'Aprovado na dashboard'})">Aprovar</button>
            <button onclick="api('/api/item-status',{item_id:'${esc(item.item_id)}',status:'needs_source_check',notes:'Precisa validar fonte/claim'})">Source check</button>
            <button class="bad" onclick="api('/api/item-status',{item_id:'${esc(item.item_id)}',status:'rejected',notes:'Rejeitado na dashboard'})">Rejeitar</button>
            <a href="${esc(item.source_url)}" target="_blank">Fonte</a>
          </div>`
        )).join('') || '<div class="panel"><p class="notice">Sem items para rever.</p></div>'}
      `;
    }
    function renderTrends() {
      const trends = state.trends || [];
      document.getElementById('trends').innerHTML = `
        <div class="panel"><h2>Trend Radar</h2><p class="notice">Sinais de engagement fora de Portugal. Isto serve para aprender formato, dor e curiosidade, nao para copiar.</p></div>
        ${trends.map(signal => card(
          signal.title,
          `${pill(signal.platform)}${pill(signal.topic)}${pill(`score ${signal.score}`)}${pill(`${signal.comments} comments`)}`,
          `Porque funcionou: ${signal.why_it_worked}\n\nAngulo PTIA: ${signal.ptia_angle}\n\nRisco: ${signal.risk_notes}`,
          `<div class="actions">
            <a href="${esc(signal.url)}" target="_blank">Link</a>
            <a href="${esc(signal.discussion_url)}" target="_blank">Discussao</a>
          </div>`
        )).join('') || '<div class="panel"><p class="notice">Sem trends ainda. Corre trend-radar no CLI.</p></div>'}
      `;
    }
    function renderDrafts() {
      const drafts = state.draft_queue || [];
      document.getElementById('drafts').innerHTML = `
        <div class="panel"><h2>Check 2: pacote final para postar</h2><p class="notice">Reve texto final, hashtags, fonte e imagem. So depois deste OK entra em Final OK.</p></div>
        ${drafts.map(finalDraftCard).join('') || '<div class="panel"><p class="notice">Sem drafts pendentes.</p></div>'}
      `;
    }
    function assetUrl(asset) { return `/asset?path=${encodeURIComponent(asset.file_path)}`; }
    function finalText(draft) {
      const hashtags = draft.hashtags ? `\n\n${draft.hashtags}` : '';
      const source = draft.source_url ? `\n\nFonte: ${draft.source_url}` : '';
      return `${draft.text || ''}${hashtags}${source}`.trim();
    }
    function findDraft(draftId) {
      const allDrafts = [
        ...(state.draft_queue || []),
        ...(state.ready_to_schedule || []),
        ...(state.scheduled || []),
        ...(state.published || [])
      ];
      return allDrafts.find(draft => draft.draft_id === draftId);
    }
    function copyFinalText(draftId) {
      const draft = findDraft(draftId);
      if (!draft) return;
      navigator.clipboard.writeText(finalText(draft));
    }
    function assetPreviews(draft) {
      const assets = draft.assets || [];
      if (!assets.length) return '<p class="notice">Sem imagem gerada. Corre assets para este draft.</p>';
      return `<div class="asset-strip">${assets.slice(0, 6).map(asset => `<a href="${assetUrl(asset)}" target="_blank"><img class="asset-preview" src="${assetUrl(asset)}" alt=""></a>`).join('')}</div>`;
    }
    function finalDraftCard(draft) {
      return `<article class="card">
        <h3>${esc(draft.title)}</h3>
        <div class="meta">${pill(draft.channel)}${pill(draft.format)}${pill(draft.status)}${pill(draft.section || 'sem section')}</div>
        <div class="final-box">
          <div>
            <span class="label">Texto final</span>
            <div class="post-copy">${esc(finalText(draft))}</div>
          </div>
          <div>
            <span class="label">Imagem final</span>
            ${assetPreviews(draft)}
          </div>
        </div>
        <div class="actions">
          <button onclick="copyFinalText('${esc(draft.draft_id)}')">Copiar texto</button>
          <button class="good" onclick="api('/api/draft-status',{draft_id:'${esc(draft.draft_id)}',status:'approved'})">Submeter para Final OK</button>
          <button onclick="api('/api/draft-status',{draft_id:'${esc(draft.draft_id)}',status:'needs_edit'})">Needs edit</button>
          <button class="bad" onclick="api('/api/draft-status',{draft_id:'${esc(draft.draft_id)}',status:'rejected'})">Rejeitar</button>
          <a href="${esc(draft.source_url)}" target="_blank">Fonte</a>
        </div>
      </article>`;
    }
    function renderAssets() {
      const assets = state.assets || [];
      document.getElementById('assets').innerHTML = `
        <div class="panel"><h2>Asset Factory</h2><p class="notice">SVGs PTIA gerados localmente. Podem ser abertos no browser ou importados no Canva/Figma para exportar PNG.</p></div>
        ${assets.map(asset => card(
          asset.title,
          `${pill(asset.channel)}${pill(asset.asset_type)}${pill(asset.format)}${pill(asset.status)}`,
          asset.notes || asset.file_path,
          `<div class="actions"><a href="/asset?path=${encodeURIComponent(asset.file_path)}" target="_blank">Abrir SVG</a></div>`
        )).join('') || '<div class="panel"><p class="notice">Sem assets ainda. Corre assets no CLI.</p></div>'}
      `;
    }
    function renderSchedule() {
      const approved = state.final_ready_to_schedule || [];
      const slots = ['09:00', '13:00', '16:00', '21:00'];
      const selectedDate = scheduleDate();
      const bufferState = state.buffer_available
        ? 'Buffer API detectada. LinkedIn vai para Buffer. Instagram precisa de imagem/media validada; Site fica marcado localmente ate ligarmos CMS.'
        : 'Buffer API ainda nao detectada. Cola BUFFER_API_KEY no .env.local e carrega Atualizar Buffer.';
      document.getElementById('schedule').innerHTML = `
        <div class="panel">
          <h2>Final OK: plano a 4 dias</h2>
          <p class="notice">Escolhe o dia, depois dá OK nos slots 09:00, 13:00, 16:00, 21:00. O Buffer recebe a data/hora PT correta.</p>
        </div>
        <div class="actions">
          <button onclick="discoverBuffer()">Atualizar Buffer</button>
          ${scheduleDayPills(selectedDate)}
          <label class="schedule-date-inline">Data <input id="schedule_date" type="date" value="${selectedDate}" onchange="setScheduleDate(this.value)"></label>
          <span class="pill">${esc(bufferState)}</span>
        </div>
        ${renderScheduleBoard(approved, slots)}
      `;
    }
    function postsByChannel(posts) {
      return {
        instagram: posts.filter(post => post.channel === 'instagram'),
        linkedin: posts.filter(post => post.channel === 'linkedin'),
        site: posts.filter(post => post.channel === 'site')
      };
    }
    function packageRows(posts) {
      const byTopic = {};
      posts.forEach(post => {
        const key = post.topic_id || post.post_id;
        if (!byTopic[key]) byTopic[key] = {topic_id: key, posts: {}, title: post.title || 'Pacote'};
        byTopic[key].posts[post.channel] = post;
        if (post.channel === 'linkedin') byTopic[key].title = post.title || byTopic[key].title;
      });
      return Object.values(byTopic);
    }
    function localDateOffset(daysAhead) {
      const now = new Date();
      now.setDate(now.getDate() + daysAhead);
      return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    }
    function defaultScheduleDate() {
      return localDateOffset(1);
    }
    let selectedScheduleDate = defaultScheduleDate();
    function scheduleDayOptions() {
      return [
        ['Amanha', localDateOffset(1)],
        ['Depois de amanha', localDateOffset(2)],
        ['Daqui a 4 dias', localDateOffset(4)],
        ['Daqui a 5 dias', localDateOffset(5)]
      ];
    }
    function setScheduleDate(dateValue) {
      selectedScheduleDate = dateValue || defaultScheduleDate();
      renderSchedule();
      renderScheduled();
    }
    function scheduleDayPills(selectedDate) {
      return `<div class="schedule-day-pills">${scheduleDayOptions().map(([label, dateValue]) =>
        `<button type="button" class="day-pill ${dateValue === selectedDate ? 'active' : ''}" onclick="setScheduleDate('${esc(dateValue)}')">${esc(label)}</button>`
      ).join('')}</div>`;
    }
    function timezoneOffsetFor(date) {
      const minutes = -date.getTimezoneOffset();
      const sign = minutes >= 0 ? '+' : '-';
      const absMinutes = Math.abs(minutes);
      return `${sign}${String(Math.floor(absMinutes / 60)).padStart(2, '0')}:${String(absMinutes % 60).padStart(2, '0')}`;
    }
    function scheduleDate() {
      const input = document.getElementById('schedule_date');
      return input?.value || selectedScheduleDate || defaultScheduleDate();
    }
    function scheduleIso(time) {
      const dateValue = scheduleDate();
      const localDate = new Date(`${dateValue}T${time}:00`);
      return `${dateValue}T${time}:00${timezoneOffsetFor(localDate)}`;
    }
    async function discoverBuffer() {
      showToast('A procurar canais Buffer...');
      await api('/api/buffer-discover', {});
      showToast('Buffer atualizado');
      showTab('schedule');
    }
    async function scheduleBufferPost(postId, scheduledTime) {
      showToast('A enviar para Buffer...');
      await api('/api/schedule-buffer', {post_id: postId, scheduled_time: scheduledTime});
      showToast('Agendado');
      showTab('scheduled_tab');
    }
    async function schedulePackage(topicId, scheduledTime) {
      showToast('A agendar os 3 canais deste tema...');
      await api('/api/schedule-package', {topic_id: topicId, scheduled_time: scheduledTime});
      showToast('Pacote agendado');
      showTab('scheduled_tab');
    }
    function renderScheduleBoard(posts, slots) {
      const channels = [
        ['instagram', 'Instagram'],
        ['linkedin', 'LinkedIn'],
        ['site', 'Site']
      ];
      const packages = packageRows(posts);
      const rows = slots.map((time, index) => `
        <div class="slot-row">
          <div class="slot-time">${time}</div>
          ${channels.map(([key, label]) => scheduleSlotCard(packages[index]?.posts?.[key], label, time, 'final_ok', key, packages[index]?.topic_id)).join('')}
        </div>
      `).join('');
      return `<div class="schedule-board">${rows}</div>`;
    }
    function renderScheduledBoard(posts, slots) {
      const channels = [
        ['instagram', 'Instagram'],
        ['linkedin', 'LinkedIn'],
        ['site', 'Site']
      ];
      const selectedDate = scheduleDate();
      const dayPosts = posts.filter(post => (post.scheduled_time || '').slice(0, 10) === selectedDate);
      const packages = packageRows(dayPosts);
      const rows = slots.map((time, index) => `
        <div class="slot-row">
          <div class="slot-time">${time}</div>
          ${channels.map(([key, label]) => scheduleSlotCard(packages[index]?.posts?.[key], label, time, 'scheduled', key, packages[index]?.topic_id)).join('')}
        </div>
      `).join('');
      return `<div class="schedule-board">${rows}</div>`;
    }
    function scheduleSlotCard(post, label, time, mode = 'final_ok', channelKey = 'generic', topicId = '') {
      const scheduledTime = scheduleIso(time);
      const channelPill = `<span class="channel-pill ${esc(channelKey)}">${esc(label)}</span>`;
      if (!post) {
        return `<article class="card slot-card empty">
          <div>
            ${channelPill}
            <div class="slot-headline">${mode === 'scheduled' ? 'Sem post agendado neste slot' : 'Sem post aprovado para este slot'}</div>
            <p class="notice">${mode === 'scheduled' ? 'Quando agendares o pacote, aparece aqui.' : 'Aprova um LinkedIn em A Rever para preencher esta hora com os 3 canais.'}</p>
          </div>
        </article>`;
      }
      if (mode === 'scheduled') {
        const urlId = `url_${post.post_id}`;
        return `<article class="card slot-card">
          <div>
            ${channelPill}
            <div class="slot-headline">${esc(post.title)}</div>
            <div class="meta">${pill(post.scheduled_time || scheduledTime)}${post.buffer_post_id ? pill(post.buffer_post_id === 'manual_buffer_media_required' ? 'Buffer manual media' : 'Buffer ' + post.buffer_post_id) : ''}</div>
          </div>
          <div>
            <div class="field"><label>URL publicado</label><input id="${urlId}" placeholder="https://..."></div>
            <div class="actions">
              <button onclick="openSocialPreview('${esc(post.post_id)}')">Preview</button>
              <button onclick="copyFinalPost('${esc(post.post_id)}')">Copiar</button>
              <button onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'needs_final_review'})">Voltar a Rever</button>
              <button class="good" onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'published',published_url:document.getElementById('${urlId}').value})">Marcar published</button>
            </div>
          </div>
        </article>`;
      }
      return `<article class="card slot-card">
        <div>
          ${channelPill}
          <div class="slot-headline">${esc(post.title)}</div>
          <div class="meta">${pill(scheduledTime)}</div>
        </div>
        <div class="actions">
          <button onclick="openSocialPreview('${esc(post.post_id)}')">Preview</button>
          <button onclick="copyFinalPost('${esc(post.post_id)}')">Copiar</button>
          <button onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'needs_final_review'})">Voltar a Rever</button>
          ${topicId ? `<button class="primary" onclick="schedulePackage('${esc(topicId)}','${esc(scheduledTime)}')">OK slot</button>` : ''}
        </div>
      </article>`;
    }
    function renderScheduled() {
      const scheduled = state.final_scheduled_posts || [];
      const slots = ['09:00', '13:00', '16:00', '21:00'];
      const selectedDate = scheduleDate();
      const dayCount = scheduled.filter(post => (post.scheduled_time || '').slice(0, 10) === selectedDate).length;
      document.getElementById('scheduled_tab').innerHTML = `
        <div class="panel">
          <h2>Scheduled: plano a 4 dias</h2>
          <p class="notice">Escolhe o dia para veres apenas os posts agendados nessa data. Quando publicares, cola o URL e marca como published.</p>
          <div class="actions">
            ${scheduleDayPills(selectedDate)}
            <label class="schedule-date-inline">Data <input id="schedule_date" type="date" value="${selectedDate}" onchange="setScheduleDate(this.value)"></label>
            <span class="pill">${dayCount} posts neste dia</span>
          </div>
        </div>
        ${renderScheduledBoard(scheduled, slots)}
      `;
    }
    function renderPublished() {
      const published = state.final_published_posts || [];
      const recommendations = state.learnings?.recommendations || [];
      if (!published.length) {
        document.getElementById('published_tab').innerHTML = `
          <section class="published-layout">
            <div class="panel empty-workflow">
              <div class="empty-workflow-inner">
                <h2>Ainda nao ha posts publicados</h2>
                <p class="notice">Quando marcares um post como published em Scheduled, ele aparece aqui para registares metricas e alimentar o learning loop.</p>
                <div class="steps-row">
                  <div class="step-chip"><strong>1</strong><br>Agenda em Final OK</div>
                  <div class="step-chip"><strong>2</strong><br>Marca published em Scheduled</div>
                  <div class="step-chip"><strong>3</strong><br>Regista resultados aqui</div>
                </div>
                <div class="actions">
                  <button class="primary" onclick="showTab('scheduled_tab')">Ir para Scheduled</button>
                  <button onclick="showTab('schedule')">Ver Final OK</button>
                </div>
              </div>
            </div>
            <aside class="panel">
              <h2>Learning loop</h2>
              <p class="notice">O motor so aprende depois de ter resultados reais: saves, shares, comentarios, clicks e notas tuas.</p>
              <div class="metric-grid">
                <div class="metric-card"><strong>0</strong><span>posts</span></div>
                <div class="metric-card"><strong>0</strong><span>metricas</span></div>
                <div class="metric-card"><strong>0</strong><span>aprendizagens</span></div>
              </div>
              ${recommendations.map(x => `<p class="text" style="margin-top:16px">${esc(x)}</p>`).join('')}
            </aside>
          </section>
        `;
        return;
      }
      document.getElementById('published_tab').innerHTML = `
        <div class="panel"><h2>Published</h2><p class="notice">Regista resultados para alimentar o learning loop.</p></div>
        <div class="published-layout">
          <div>${published.map(finalPublishedCard).join('') || '<div class="empty-state">Ainda não há posts publicados.</div>'}</div>
          <div class="panel"><h2>Learning loop</h2><p class="notice">Depois de publicar, mete métricas. O engine usa isto para aprender que temas, fontes e ângulos funcionam.</p>${(state.learnings?.recommendations || []).map(x => `<p class="text">${esc(x)}</p>`).join('')}</div>
        </div>
      `;
    }
    function finalScheduleCard(post) {
      const inputId = `time_${post.post_id}`;
      const urlId = `url_${post.post_id}`;
      return `<article class="card">
        <h3>${esc(post.title)}</h3>
        <div class="meta">${pill(post.channel)}${pill(post.scheduled_time || 'sem hora')}</div>
        <div class="post-copy">${esc(finalPostText(post))}</div>
        <div class="schedule-row">
          <button onclick="copyFinalPost('${esc(post.post_id)}')">Copiar texto</button>
          <div class="field"><label>Hora</label><input id="${inputId}" value="${esc(post.scheduled_time || '')}" placeholder="2026-05-15T08:30:00+01:00"></div>
          <button class="primary" onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'scheduled',scheduled_time:document.getElementById('${inputId}').value})">Schedule</button>
        </div>
        <div class="schedule-row">
          <span></span>
          <div class="field"><label>URL publicado</label><input id="${urlId}" placeholder="https://..."></div>
          <button class="good" onclick="api('/api/final-post-status',{post_id:'${esc(post.post_id)}',status:'published',published_url:document.getElementById('${urlId}').value})">Marcar published</button>
        </div>
      </article>`;
    }
    function finalPublishedCard(post) {
      const id = post.post_id;
      return `<article class="card">
        <h3>${esc(post.title)}</h3>
        <div class="meta">${pill(post.channel)}${pill(post.published_url || 'sem URL')}</div>
        <div class="actions">
          <button onclick="copyFinalPost('${esc(post.post_id)}')">Copiar texto</button>
          ${post.published_url ? `<a href="${esc(post.published_url)}" target="_blank">Abrir post</a>` : ''}
        </div>
        <div class="form-row">
          <input id="imp_${id}" type="number" placeholder="impressions">
          <input id="likes_${id}" type="number" placeholder="likes">
          <input id="comments_${id}" type="number" placeholder="comments">
          <input id="shares_${id}" type="number" placeholder="shares">
          <input id="saves_${id}" type="number" placeholder="saves">
          <input id="clicks_${id}" type="number" placeholder="clicks">
          <input id="followers_${id}" type="number" placeholder="followers">
          <input id="post_${id}" value="${esc(post.published_url || post.post_id)}" placeholder="post id/url">
        </div>
        <textarea id="notes_${id}" placeholder="Notas: o que funcionou / nao funcionou"></textarea>
        <div class="actions"><button class="primary" onclick="saveFinalPerformance('${esc(id)}')">Guardar métricas</button></div>
      </article>`;
    }
    function scheduleCard(draft, isScheduled = false) {
      const inputId = `time_${draft.draft_id}`;
      const urlId = `url_${draft.draft_id}`;
      return `<article class="card">
        <h3>${esc(draft.title)}</h3>
        <div class="meta">${pill(draft.channel)}${pill(draft.format)}${pill(draft.scheduled_time || 'sem hora')}</div>
        <div class="final-box">
          <div>
            <span class="label">Texto final aprovado</span>
            <div class="post-copy">${esc(finalText(draft))}</div>
          </div>
          <div>
            <span class="label">Imagem final</span>
            ${assetPreviews(draft)}
          </div>
        </div>
        <div class="actions">
          <button onclick="copyFinalText('${esc(draft.draft_id)}')">Copiar texto</button>
          <input id="${inputId}" value="${esc(draft.scheduled_time || '')}" placeholder="2026-05-15T08:30:00+01:00">
          <button onclick="api('/api/draft-status',{draft_id:'${esc(draft.draft_id)}',status:'scheduled',scheduled_time:document.getElementById('${inputId}').value})">Marcar scheduled</button>
          <input id="${urlId}" placeholder="published URL">
          <button class="good" onclick="api('/api/draft-status',{draft_id:'${esc(draft.draft_id)}',status:'published',published_url:document.getElementById('${urlId}').value})">Marcar posted</button>
        </div>
      </article>`;
    }
    function renderPerformance() {
      const published = state.final_published_posts || [];
      const perf = state.performance || [];
      document.getElementById('performance').innerHTML = `
        <div class="two">
          <div class="panel">
            <h2>Posts posted</h2>
            ${published.map(performanceForm).join('') || '<p class="notice">Sem drafts marcados como published.</p>'}
          </div>
          <div class="panel">
            <h2>Metricas registadas</h2>
            ${perf.map(row => card(row.topic || row.draft_id, `${pill(row.channel)}${pill(row.section)}${pill(`score ${row.likes + row.clicks + row.comments * 2 + row.shares * 3 + row.saves * 3 + row.followers_gained * 4}`)}`, `Impressions: ${row.impressions}\nLikes: ${row.likes}\nComments: ${row.comments}\nShares: ${row.shares}\nSaves: ${row.saves}\nClicks: ${row.clicks}\nNotas: ${row.notes}`)).join('') || '<p class="notice">Ainda sem metricas.</p>'}
          </div>
        </div>
      `;
    }
    function performanceForm(draft) {
      return `<article class="card">
        <h3>${esc(draft.title)}</h3>
        <div class="meta">${pill(draft.channel)}${pill(draft.section || '')}</div>
        <div class="form-row">
          <input id="imp_${draft.draft_id}" type="number" placeholder="impressions">
          <input id="likes_${draft.draft_id}" type="number" placeholder="likes">
          <input id="comments_${draft.draft_id}" type="number" placeholder="comments">
          <input id="shares_${draft.draft_id}" type="number" placeholder="shares">
          <input id="saves_${draft.draft_id}" type="number" placeholder="saves">
          <input id="clicks_${draft.draft_id}" type="number" placeholder="clicks">
          <input id="followers_${draft.draft_id}" type="number" placeholder="followers">
          <input id="post_${draft.draft_id}" placeholder="post id/url">
        </div>
        <textarea id="notes_${draft.draft_id}" placeholder="Notas: o que funcionou / nao funcionou"></textarea>
        <div class="actions">
          <button class="primary" onclick="savePerformance('${esc(draft.draft_id)}')">Guardar metricas</button>
        </div>
      </article>`;
    }
    function value(id) { return document.getElementById(id)?.value || ''; }
    function num(id) { return Number(value(id) || 0); }
    function savePerformance(draftId) {
      api('/api/performance', {
        draft_id: draftId,
        post_id: value(`post_${draftId}`),
        impressions: num(`imp_${draftId}`),
        likes: num(`likes_${draftId}`),
        comments: num(`comments_${draftId}`),
        shares: num(`shares_${draftId}`),
        saves: num(`saves_${draftId}`),
        clicks: num(`clicks_${draftId}`),
        followers_gained: num(`followers_${draftId}`),
        notes: value(`notes_${draftId}`)
      });
    }
    function saveFinalPerformance(postId) {
      const post = findFinalPost(postId) || {};
      api('/api/performance', {
        draft_id: postId,
        post_id: value(`post_${postId}`),
        channel: post.channel || '',
        topic: post.title || '',
        impressions: num(`imp_${postId}`),
        likes: num(`likes_${postId}`),
        comments: num(`comments_${postId}`),
        shares: num(`shares_${postId}`),
        saves: num(`saves_${postId}`),
        clicks: num(`clicks_${postId}`),
        followers_gained: num(`followers_${postId}`),
        notes: value(`notes_${postId}`)
      });
    }
    function growthRow(row) {
      const actionClass = row.action === 'Boost 3-5 EUR' ? 'good' : row.action === 'Reaproveitar' ? 'primary' : '';
      return `<article class="card">
        <h3>${esc(row.title || 'Post PTIA')}</h3>
        <div class="meta">
          ${pill(row.channel || 'canal')}
          ${pill(`score ${row.score || 0}`)}
          ${pill(`${row.engagement_rate || 0}% ER ponderado`)}
          ${pill(row.impressions ? `${row.impressions} impressions` : 'sem impressions')}
        </div>
        <p class="text">${esc(row.reason || '')}</p>
        <div class="metric-grid compact">
          <div class="metric-card"><strong>${esc(row.saves || 0)}</strong><span>saves</span></div>
          <div class="metric-card"><strong>${esc(row.shares || 0)}</strong><span>shares</span></div>
          <div class="metric-card"><strong>${esc(row.comments || 0)}</strong><span>comments</span></div>
          <div class="metric-card"><strong>${esc(row.clicks || 0)}</strong><span>clicks</span></div>
        </div>
        <div class="actions">
          <button class="${actionClass}">${esc(row.action || 'Avaliar')}</button>
          ${row.published_url ? `<a href="${esc(row.published_url)}" target="_blank">Abrir post</a>` : ''}
        </div>
      </article>`;
    }
    function renderGrowth() {
      const growth = state.growth || {};
      const candidates = growth.boost_candidates || [];
      const ranked = growth.all_ranked || [];
      const rules = growth.rules || [];
      document.getElementById('growth_tab').innerHTML = `
        <div class="panel">
          <h2>Growth: boost só para vencedores</h2>
          <p class="notice">Esta área transforma métricas reais em decisões de distribuição. Não gastamos dinheiro em posts medianos.</p>
          <div class="metric-grid">
            <div class="metric-card"><strong>${esc(candidates.length)}</strong><span>candidatos boost</span></div>
            <div class="metric-card"><strong>${esc(growth.recommended_spend_eur || 0)}€</strong><span>gasto sugerido</span></div>
            <div class="metric-card"><strong>${esc(growth.weekly_budget_eur || 8)}€</strong><span>limite semanal</span></div>
          </div>
        </div>
        <section class="published-layout">
          <div>
            <div class="panel">
              <h2>Promover esta semana</h2>
              ${candidates.map(growthRow).join('') || '<p class="notice">Ainda sem candidatos. Regista métricas em Published primeiro.</p>'}
            </div>
            <div class="panel">
              <h2>Ranking editorial</h2>
              ${ranked.map(growthRow).join('') || '<p class="notice">Sem métricas suficientes.</p>'}
            </div>
          </div>
          <aside class="panel">
            <h2>Regras CMO</h2>
            ${rules.map(rule => `<p class="text">• ${esc(rule)}</p>`).join('')}
            <hr>
            <p class="notice">Workflow: publicar → esperar 6-12h → registar métricas → Growth decide se vale boost ou reaproveitamento.</p>
          </aside>
        </section>
      `;
    }
    async function generateNewsletter() {
      showToast('A gerar PTIA Weekly...');
      await api('/api/newsletter-generate', {limit: 5});
      showToast('Newsletter gerada');
      showTab('newsletter_tab');
    }
    function findNewsletter(issueId) {
      return (state.newsletter_issues || []).find(issue => issue.issue_id === issueId);
    }
    function copyNewsletterText(issueId) {
      const issue = findNewsletter(issueId);
      if (!issue) return;
      navigator.clipboard.writeText(`Subject: ${issue.subject}\nPreheader: ${issue.preheader}\n\n${issue.text}`);
      showToast('Texto da newsletter copiado');
    }
    function copyNewsletterHtml(issueId) {
      const issue = findNewsletter(issueId);
      if (!issue) return;
      navigator.clipboard.writeText(issue.html);
      showToast('HTML da newsletter copiado');
    }
    async function updateNewsletter(issueId, status) {
      const sendAt = value(`newsletter_send_${issueId}`);
      await api('/api/newsletter-status', {issue_id: issueId, status, send_at: sendAt});
      showToast('Newsletter atualizada');
      showTab('newsletter_tab');
    }
    function newsletterCard(issue, index) {
      return `<article class="card">
        <h3>${esc(issue.title)}</h3>
        <div class="meta">${pill(issue.status)}${pill(`5 news`)}${pill(issue.created_at || '')}</div>
        <div class="field"><label>Subject</label><input value="${esc(issue.subject)}" readonly></div>
        <div class="field"><label>Preheader</label><input value="${esc(issue.preheader)}" readonly></div>
        <div class="actions">
          <button onclick="copyNewsletterText('${esc(issue.issue_id)}')">Copiar texto</button>
          <button onclick="copyNewsletterHtml('${esc(issue.issue_id)}')">Copiar HTML</button>
          <button class="good" onclick="updateNewsletter('${esc(issue.issue_id)}','approved')">Aprovar</button>
          <button class="bad" onclick="updateNewsletter('${esc(issue.issue_id)}','rejected')">Rejeitar</button>
        </div>
        <div class="field" style="margin-top:14px">
          <label>Hora de envio</label>
          <input id="newsletter_send_${esc(issue.issue_id)}" value="${esc(issue.send_at || '')}" placeholder="2026-05-22T08:00:00+01:00">
        </div>
        <div class="actions">
          <button class="primary" onclick="updateNewsletter('${esc(issue.issue_id)}','scheduled')">Marcar scheduled</button>
          <button class="good" onclick="updateNewsletter('${esc(issue.issue_id)}','sent')">Marcar sent</button>
        </div>
        <textarea class="newsletter-textarea" readonly>${esc(issue.text)}</textarea>
      </article>`;
    }
    function renderNewsletter() {
      const issues = state.newsletter_issues || [];
      const sample = state.newsletter_sample;
      const latest = issues[0] || sample;
      document.getElementById('newsletter_tab').innerHTML = `
        <div class="panel">
          <h2>PTIA Weekly</h2>
          <p class="notice">Produto separado do feed diário. O motor escolhe os 5 posts PTIA da semana com melhor tracking real: saves, shares, comentários, clicks, likes e followers. Depois transforma isso em email curto com ranking, contexto e próxima ação editorial.</p>
          <div class="actions">
            <button class="primary" onclick="generateNewsletter()">Gerar newsletter semanal</button>
            <span class="pill">Ranking: nossos posts por engagement semanal</span>
          </div>
        </div>
        <section class="newsletter-layout">
          <div class="newsletter-list">
            ${issues.map(newsletterCard).join('') || `<div class="panel newsletter-empty"><h2>Ainda sem ranking real</h2><p class="notice">Quando marcares posts como published e registares métricas, a newsletter real aparece aqui. À direita já tens um exemplo de preview com dados de demonstração.</p></div>`}
          </div>
          <aside class="panel">
            <h2>${issues.length ? 'Preview email' : 'Preview exemplo'}</h2>
            <p class="notice">Este é o mockup pronto para enviar. A base são os nossos posts com melhor performance, por ordem de engagement. Para já, copiar para Substack/Beehiiv/Ghost; depois ligamos envio por API.</p>
            ${latest ? `<div class="actions" style="margin-top:0"><button onclick="navigator.clipboard.writeText(\`${esc(latest.text).replace(/`/g, '&#96;')}\`); showToast('Texto do exemplo copiado')">Copiar texto preview</button><button onclick="navigator.clipboard.writeText(\`${esc(latest.html).replace(/`/g, '&#96;')}\`); showToast('HTML do exemplo copiado')">Copiar HTML preview</button></div><div class="newsletter-preview"><iframe title="Preview newsletter" srcdoc="${esc(latest.html)}"></iframe></div>` : '<p class="notice">Sem preview ainda.</p>'}
          </aside>
        </section>
      `;
    }
    function renderLearnings() {
      const l = state.learnings || {};
      document.getElementById('learnings').innerHTML = `
        <div class="grid">
          <div class="panel"><h2>Aplicar no inicio do fluxo</h2><div class="learning-list">${(l.recommendations || []).map(x => `<p class="text">${esc(x)}</p>`).join('')}</div></div>
          <div class="panel"><h2>Melhores posts</h2>${(l.best_posts || []).map(row => card(row.title, `${pill(row.channel)}${pill(row.section)}${pill(`score ${row.score}`)}`, `Fonte: ${row.source}\nLikes ${row.likes}, comments ${row.comments}, shares ${row.shares}, saves ${row.saves}, clicks ${row.clicks}\n${row.notes}`)).join('') || '<p class="notice">Sem dados.</p>'}</div>
          <div class="panel"><h2>Mais fracos</h2>${(l.weak_posts || []).map(row => card(row.title, `${pill(row.channel)}${pill(row.section)}${pill(`score ${row.score}`)}`, `Fonte: ${row.source}\nImpressions ${row.impressions}\n${row.notes}`)).join('') || '<p class="notice">Sem dados.</p>'}</div>
        </div>
      `;
    }
    function render() {
      renderStats();
      renderFlow();
      renderVerifying();
      renderVerified();
      renderTopicsV2();
      renderFinalDraftPack();
      renderFinalPostsV2();
      renderReview();
      renderTrends();
      renderDrafts();
      renderAssets();
      renderSchedule();
      renderScheduled();
      renderPublished();
      renderNewsletter();
      renderPerformance();
      renderGrowth();
      renderLearnings();
    }
    loadState();
  </script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    state: DashboardState

    def log_message(self, format, *args):  # noqa: A002 - matches BaseHTTPRequestHandler API.
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(body or "{}")

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self) -> None:
        data = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_site_file(self, relative_path: str) -> None:
        site_root = self.state.site_dir.resolve()
        target = (site_root / relative_path).resolve()
        if site_root not in target.parents and target != site_root:
            self._send_json({"error": "invalid site path"}, HTTPStatus.BAD_REQUEST)
            return
        if not target.exists() or not target.is_file():
            self._send_json({"error": "site file not found"}, HTTPStatus.NOT_FOUND)
            return
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API.
        path = urlparse(self.path).path
        if path == "/":
            self._send_html()
            return
        if path == "/api/state":
            self._send_json(self.state.snapshot())
            return
        if path == "/api/site-feed":
            self._send_json(_site_feed(self.state))
            return
        if path in {"/site", "/site/"}:
            self._send_site_file("index.html")
            return
        if path == "/admin":
            self._send_site_file("admin.html")
            return
        if path.startswith("/site/"):
            self._send_site_file(path.removeprefix("/site/"))
            return
        if path == "/asset":
            query = urlparse(self.path).query
            params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
            raw_path = params.get("path", "")
            from urllib.parse import unquote

            asset_path = Path(unquote(raw_path)).resolve()
            data_root = self.state.data_dir.resolve()
            if data_root not in asset_path.parents and asset_path != data_root:
                self._send_json({"error": "invalid asset path"}, HTTPStatus.BAD_REQUEST)
                return
            if not asset_path.exists():
                self._send_json({"error": "asset not found"}, HTTPStatus.NOT_FOUND)
                return
            data = asset_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            content_type = guess_type(str(asset_path))[0] or "application/octet-stream"
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API.
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/item-status":
                item = update_item_status(
                    self.state.processed_path,
                    item_id=str(payload["item_id"]),
                    status=str(payload["status"]),
                    editor_notes=str(payload.get("notes", "")),
                )
                self._send_json({"ok": True, "item": _to_dict(item)})
                return
            if path == "/api/draft-status":
                draft = update_draft_status(
                    self.state.drafts_path,
                    draft_id=str(payload["draft_id"]),
                    status=str(payload["status"]),
                    scheduled_time=str(payload.get("scheduled_time", "")),
                    published_url=str(payload.get("published_url", "")),
                    buffer_post_id=str(payload.get("buffer_post_id", "")),
                )
                self._send_json({"ok": True, "draft": _to_dict(draft)})
                return
            if path == "/api/performance":
                draft_id = str(payload["draft_id"])
                drafts = {draft.draft_id: draft for draft in load_content_drafts(self.state.drafts_path)}
                items = {item.item_id: item for item in load_processed_items(self.state.processed_path)}
                draft = drafts.get(draft_id)
                item = items.get(draft.item_id) if draft else None
                record = ContentPerformance(
                    performance_id=f"perf_{stable_hash(draft_id + utc_now_iso(), 18)}",
                    draft_id=draft_id,
                    post_id=str(payload.get("post_id", "")),
                    channel=draft.channel if draft else str(payload.get("channel", "")),
                    published_at=utc_now_iso(),
                    topic=draft.title if draft else str(payload.get("topic", "")),
                    section=item.section if item else str(payload.get("section", "")),
                    impressions=int(payload.get("impressions", 0) or 0),
                    likes=int(payload.get("likes", 0) or 0),
                    comments=int(payload.get("comments", 0) or 0),
                    shares=int(payload.get("shares", 0) or 0),
                    saves=int(payload.get("saves", 0) or 0),
                    clicks=int(payload.get("clicks", 0) or 0),
                    followers_gained=int(payload.get("followers_gained", 0) or 0),
                    notes=str(payload.get("notes", "")),
                )
                add_performance_record(self.state.performance_path, record)
                self._send_json({"ok": True, "performance": _to_dict(record)})
                return
            if path == "/api/signal-status":
                signal = update_signal_status(
                    self.state.radar_signals_path,
                    signal_id=str(payload["signal_id"]),
                    status=str(payload["status"]),
                    notes=str(payload.get("notes", "")),
                )
                self._send_json({"ok": True, "signal": _to_dict(signal)})
                return
            if path == "/api/topic-status":
                topic = update_topic_status(
                    self.state.editorial_topics_path,
                    topic_id=str(payload["topic_id"]),
                    status=str(payload["status"]),
                    notes=str(payload.get("notes", "")),
                )
                self._send_json({"ok": True, "topic": _to_dict(topic)})
                return
            if path == "/api/final-post-status":
                status = str(payload["status"])
                if status == "rejected":
                    post = _reject_final_post(self.state, str(payload["post_id"]))
                else:
                    post = update_final_post_status(
                        self.state.final_posts_path,
                        post_id=str(payload["post_id"]),
                        status=status,
                        scheduled_time=str(payload.get("scheduled_time", "")),
                        buffer_post_id=str(payload["buffer_post_id"]) if "buffer_post_id" in payload else None,
                        published_url=str(payload.get("published_url", "")),
                        image_path=str(payload.get("image_path", "")),
                        image_status=str(payload.get("image_status", "")),
                    )
                self._send_json({"ok": True, "post": _to_dict(post)})
                return
            if path == "/api/approve-final-package":
                posts = _approve_final_package(
                    self.state,
                    reference_post_id=str(payload["post_id"]),
                )
                self._send_json({"ok": True, "posts": [_to_dict(post) for post in posts]})
                return
            if path == "/api/final-image":
                post = _generate_final_image(
                    self.state,
                    post_id=str(payload["post_id"]),
                    feedback=str(payload.get("feedback", "")),
                )
                self._send_json({"ok": True, "post": _to_dict(post)})
                return
            if path == "/api/upload-final-image":
                post = _upload_final_image(
                    self.state,
                    post_id=str(payload["post_id"]),
                    filename=str(payload.get("filename", "")),
                    data_url=str(payload.get("data_url", "")),
                )
                self._send_json({"ok": True, "post": _to_dict(post)})
                return
            if path == "/api/final-image-status":
                posts = {post.post_id: post for post in load_final_posts(self.state.final_posts_path)}
                post_id = str(payload["post_id"])
                current = posts.get(post_id)
                if not current:
                    raise ValueError(f"Final post not found: {post_id}")
                post = update_final_post_status(
                    self.state.final_posts_path,
                    post_id=post_id,
                    status=current.status,
                    image_status=str(payload["image_status"]),
                )
                self._send_json({"ok": True, "post": _to_dict(post)})
                return
            if path == "/api/buffer-discover":
                config = _discover_buffer_channels(self.state.buffer_channels_path)
                self._send_json({"ok": True, "buffer_channels": config})
                return
            if path == "/api/schedule-buffer":
                post = _schedule_post_in_buffer(
                    self.state,
                    post_id=str(payload["post_id"]),
                    scheduled_time=str(payload["scheduled_time"]),
                )
                self._send_json({"ok": True, "post": _to_dict(post)})
                return
            if path == "/api/schedule-package":
                posts = _schedule_final_package(
                    self.state,
                    topic_id=str(payload["topic_id"]),
                    scheduled_time=str(payload["scheduled_time"]),
                )
                self._send_json({"ok": True, "posts": [_to_dict(post) for post in posts]})
                return
            if path == "/api/rewrite-final-post":
                post_id = str(payload["post_id"])
                feedback = str(payload.get("feedback", "")).strip()
                if not feedback:
                    raise ValueError("Escreve o que queres melhorar.")
                posts = {post.post_id: post for post in load_final_posts(self.state.final_posts_path)}
                post = posts.get(post_id)
                if not post:
                    raise ValueError(f"Final post not found: {post_id}")
                provider = GeminiGroundedSearchProvider()
                rewrite = provider.rewrite_final_post(
                    channel=post.channel,
                    title=post.title,
                    body=post.body,
                    hashtags=post.hashtags,
                    source_urls=post.source_urls,
                    feedback=feedback,
                )
                updated = update_final_post_copy(
                    self.state.final_posts_path,
                    post_id,
                    title=rewrite.title or post.title,
                    body=rewrite.body or post.body,
                    hashtags=_normalise_hashtags(rewrite.hashtags or post.hashtags, post.channel),
                    notes=f"Feedback: {feedback}\nRewrite: {rewrite.rationale}",
                )
                self._send_json({"ok": True, "post": _to_dict(updated)})
                return
            if path == "/api/rewrite-final-package":
                post_id = str(payload["post_id"])
                feedback = str(payload.get("feedback", "")).strip()
                if not feedback:
                    raise ValueError("Escreve o que queres melhorar.")
                updated = _sync_topic_posts_from_reference(self.state, post_id, feedback)
                self._send_json({"ok": True, "posts": [_to_dict(post) for post in updated]})
                return
            if path == "/api/polish-final-post":
                post_id = str(payload["post_id"])
                posts = {post.post_id: post for post in load_final_posts(self.state.final_posts_path)}
                post = posts.get(post_id)
                if not post:
                    raise ValueError(f"Final post not found: {post_id}")
                polished = _polish_final_post_copy(
                    channel=post.channel,
                    title=post.title,
                    body=post.body,
                    hashtags=post.hashtags,
                    source_urls=post.source_urls,
                )
                updated = update_final_post_copy(
                    self.state.final_posts_path,
                    post_id,
                    title=polished["title"],
                    body=polished["body"],
                    hashtags=_normalise_hashtags(polished["hashtags"], post.channel),
                    notes=polished["editor_notes"],
                )
                self._send_json({"ok": True, "post": _to_dict(updated)})
                return
            if path == "/api/update-final-post-copy":
                post_id = str(payload["post_id"])
                updated = update_final_post_copy(
                    self.state.final_posts_path,
                    post_id,
                    title=str(payload.get("title", "")),
                    body=str(payload.get("body", "")),
                    hashtags=_normalise_hashtags(str(payload.get("hashtags", ""))),
                    image_prompt=str(payload.get("image_prompt", "")),
                    notes="Editor manual update.",
                )
                if bool(payload.get("sync_topic", False)):
                    posts = _sync_topic_posts_from_reference(
                        self.state,
                        post_id,
                        "O editor alterou manualmente este canal. Alinha os restantes canais com a mesma tese, tom e decisão editorial.",
                    )
                    self._send_json({"ok": True, "post": _to_dict(updated), "posts": [_to_dict(post) for post in posts]})
                    return
                self._send_json({"ok": True, "post": _to_dict(updated)})
                return
            if path == "/api/add-signal":
                signal = add_radar_signal(
                    self.state.radar_signals_path,
                    source_type=str(payload["source_type"]),
                    source_name=str(payload["source_name"]),
                    title=str(payload["title"]),
                    url=str(payload["url"]),
                    published_at=str(payload["published_at"]),
                    engagement_score=int(payload.get("engagement_score", 0) or 0),
                    summary=str(payload.get("summary", "")),
                    topic_hint=str(payload.get("topic_hint", "")),
                    why_it_matters=str(payload.get("why_it_matters", "")),
                    why_engaged=str(payload.get("why_engaged", "")),
                    notes=str(payload.get("notes", "")),
                )
                self._send_json({"ok": True, "signal": _to_dict(signal)})
                return
            if path == "/api/add-topic":
                raw_signal_ids = str(payload.get("signal_ids", ""))
                topic = add_editorial_topic(
                    self.state.editorial_topics_path,
                    title=str(payload["title"]),
                    thesis=str(payload["thesis"]),
                    portugal_angle=str(payload["portugal_angle"]),
                    audience=str(payload.get("audience", "")),
                    source_signal_ids=[
                        value.strip() for value in raw_signal_ids.split(",") if value.strip()
                    ],
                    urgency_score=int(payload.get("urgency_score", 0) or 0),
                )
                self._send_json({"ok": True, "topic": _to_dict(topic)})
                return
            if path == "/api/quick-capture":
                link = str(payload.get("link", "")).strip()
                thought = str(payload.get("thought", "")).strip()
                results = {}
                if link:
                    verification = resolve_submitted_link(link, thought=thought)
                    signal = add_radar_signal(
                        self.state.radar_signals_path,
                        source_type="news",
                        source_name=verification.source_name,
                        title=verification.title,
                        url=verification.verified_url or link,
                        published_at=verification.published_at,
                        engagement_score=60 if verification.status == "verified" else 10,
                        summary=verification.summary or thought,
                        topic_hint=thought,
                        why_it_matters=thought,
                        why_engaged="",
                        notes=verification.notes,
                        status=verification.status,
                        require_recent=verification.status == "verified",
                    )
                    results["signal"] = _to_dict(signal)
                if thought and not link:
                    topic = add_editorial_topic(
                        self.state.editorial_topics_path,
                        title=thought[:90],
                        thesis=thought,
                        portugal_angle="A desenvolver pelo editor a partir deste pensamento.",
                        audience="PTIA",
                        source_signal_ids=[],
                        urgency_score=5,
                    )
                    results["topic"] = _to_dict(topic)
                if not link and not thought:
                    raise ValueError("Cola um link ou escreve um pensamento.")
                self._send_json({"ok": True, **results})
                return
            if path == "/api/gemini-scout":
                provider = GeminiGroundedSearchProvider()
                candidates = provider.scout_today_ai_news(limit=int(payload.get("limit", 8) or 8))
                written = []
                rejected = []
                for candidate in candidates:
                    verification = verify_search_candidate(candidate)
                    if verification.status != "verified":
                        rejected.append({"url": candidate.url, "status": verification.status})
                        continue
                    signal = add_radar_signal(
                        self.state.radar_signals_path,
                        source_type="gemini_scout",
                        source_name=verification.source_name,
                        title=verification.title or candidate.title,
                        url=verification.verified_url or candidate.url,
                        published_at=verification.published_at,
                        engagement_score=55,
                        summary=verification.summary or candidate.summary,
                        topic_hint=candidate.title,
                        why_it_matters=candidate.why_it_matters,
                        why_engaged="",
                        notes="Gemini Scout diário; fonte e data verificadas localmente.",
                        status="verified",
                        require_recent=True,
                    )
                    written.append(_to_dict(signal))
                self._send_json({"ok": True, "written": written, "rejected": rejected})
                return
            if path == "/api/source-scout":
                source = str(payload.get("source", "")).strip()
                limit = int(payload.get("limit", 8) or 8)
                if source == "rss":
                    result = _run_rss_scout(self.state, limit=limit)
                else:
                    result = _run_discovery_scout(self.state, source=source, limit=limit)
                self._send_json({"ok": True, **result})
                return
            if path == "/api/newsletter-generate":
                issue = generate_weekly_issue(
                    self.state.newsletter_issues_path,
                    radar_signals=load_radar_signals(self.state.radar_signals_path),
                    trend_signals=load_trend_signals(self.state.trends_path),
                    final_posts=load_final_posts(self.state.final_posts_path),
                    performance=load_content_performance(self.state.performance_path),
                    limit=int(payload.get("limit", 5) or 5),
                )
                self._send_json({"ok": True, "issue": _to_dict(issue)})
                return
            if path == "/api/newsletter-status":
                issue = update_newsletter_status(
                    self.state.newsletter_issues_path,
                    issue_id=str(payload["issue_id"]),
                    status=str(payload["status"]),
                    send_at=str(payload.get("send_at", "")),
                )
                self._send_json({"ok": True, "issue": _to_dict(issue)})
                return
            if path == "/api/build-final-pack":
                result = _build_final_pack_from_signal(
                    self.state,
                    signal_id=str(payload["signal_id"]),
                )
                self._send_json({"ok": True, **result})
                return
            if path == "/api/reverify-signal":
                signal = _find_signal(self.state.radar_signals_path, str(payload["signal_id"]))
                verification = resolve_submitted_link(signal.url, thought=signal.topic_hint or signal.notes)
                if verification.status == "verified":
                    new_signal = add_radar_signal(
                        self.state.radar_signals_path,
                        source_type="news",
                        source_name=verification.source_name,
                        title=verification.title,
                        url=verification.verified_url or signal.url,
                        published_at=verification.published_at,
                        engagement_score=max(signal.engagement_score, 60),
                        summary=verification.summary or signal.summary,
                        topic_hint=signal.topic_hint,
                        why_it_matters=signal.why_it_matters,
                        why_engaged=signal.why_engaged,
                        notes=verification.notes,
                        status="verified",
                        require_recent=True,
                    )
                    if new_signal.signal_id == signal.signal_id:
                        verified_signal = _update_signal_verification_fields(
                            self.state.radar_signals_path,
                            signal.signal_id,
                            source_name=verification.source_name,
                            title=verification.title,
                            url=verification.verified_url or signal.url,
                            published_at=verification.published_at,
                            summary=verification.summary or signal.summary,
                            notes="Fonte credivel e data encontradas; sinal reposto em Verified Selection.",
                        )
                        self._send_json({"ok": True, "signal": _to_dict(verified_signal)})
                        return
                    update_signal_status(
                        self.state.radar_signals_path,
                        signal.signal_id,
                        "used",
                        "Fonte credível encontrada; novo sinal verificado criado.",
                    )
                    self._send_json({"ok": True, "signal": _to_dict(new_signal)})
                    return
                update_signal_status(
                    self.state.radar_signals_path,
                    signal.signal_id,
                    "verifying",
                    verification.notes,
                )
                self._send_json({"ok": True, "status": verification.status, "notes": verification.notes})
                return
        except Exception as exc:  # noqa: BLE001 - surface errors to local dashboard client.
            message = str(exc) or repr(exc) or exc.__class__.__name__
            self._send_json({"error": message}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def serve_dashboard(data_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    DashboardHandler.state = DashboardState(data_dir)
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"PTIA dashboard running at http://{host}:{port}")
    server.serve_forever()
