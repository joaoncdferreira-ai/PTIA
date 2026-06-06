from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ptia_engine.models import TrendSignal, utc_now_iso
from ptia_engine.storage import append_jsonl, load_trend_signals

HN_BASE = "https://hacker-news.firebaseio.com/v0"
AI_KEYWORDS = [
    "ai",
    "artificial intelligence",
    "llm",
    "language model",
    "openai",
    "anthropic",
    "claude",
    "chatgpt",
    "gemini",
    "agent",
    "agents",
    "copilot",
    "machine learning",
    "deep learning",
    "neural",
    "inference",
    "rag",
    "mcp",
]


def _get_json(url: str, timeout: int = 20):
    request = urllib.request.Request(url, headers={"User-Agent": "PTIAContentEngine/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _hn_item(item_id: int) -> dict:
    return _get_json(f"{HN_BASE}/item/{item_id}.json")


def _hn_story_ids(kind: str) -> list[int]:
    if kind not in {"topstories", "beststories", "newstories"}:
        raise ValueError(f"Unsupported HN story kind: {kind}")
    return _get_json(f"{HN_BASE}/{kind}.json")


def _published_at(timestamp: int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def _matches_ai(title: str, url: str) -> bool:
    haystack = f"{title} {url}".casefold()
    return any(keyword in haystack for keyword in AI_KEYWORDS)


def _topic(title: str) -> str:
    lowered = title.casefold()
    if any(token in lowered for token in ["agent", "agents", "mcp"]):
        return "agents"
    if any(token in lowered for token in ["model", "llm", "inference", "neural"]):
        return "models"
    if any(token in lowered for token in ["open source", "github"]):
        return "open_source"
    if any(token in lowered for token in ["regulation", "copyright", "privacy"]):
        return "regulation"
    if any(token in lowered for token in ["startup", "enterprise", "business"]):
        return "business"
    return "ai_general"


def _why_it_worked(signal: TrendSignal) -> str:
    reasons = []
    if signal.score >= 300:
        reasons.append("forte validacao da comunidade HN")
    if signal.comments >= 100:
        reasons.append("tema controverso ou com muita discussao")
    if signal.topic in {"agents", "models", "open_source"}:
        reasons.append("tema tecnico com apelo para builders")
    if not reasons:
        reasons.append("sinal moderado de interesse numa comunidade tecnica")
    return "; ".join(reasons)


def _ptia_angle(signal: TrendSignal) -> str:
    if signal.topic == "agents":
        return "O que isto muda para equipas portuguesas que querem automatizar trabalho com agentes?"
    if signal.topic == "models":
        return "Que impacto pode ter em custo, performance ou escolha de modelos para empresas portuguesas?"
    if signal.topic == "open_source":
        return "Vale a pena builders em Portugal testarem isto antes de escolher ferramentas fechadas?"
    if signal.topic == "regulation":
        return "Que implicacoes pode ter para compliance, dados e governanca em Portugal?"
    if signal.topic == "business":
        return "Que sinal isto da sobre adocao real de IA em empresas?"
    return "Porque e que este tema interessou uma comunidade tecnica e o que e transferivel para Portugal?"


def fetch_hacker_news_trends(
    out_path: Path,
    kinds: list[str] | None = None,
    max_ids_per_kind: int = 80,
    min_score: int = 80,
    min_comments: int = 20,
) -> list[TrendSignal]:
    kinds = kinds or ["topstories", "beststories"]
    existing = load_trend_signals(out_path)
    existing_ids = {signal.signal_id for signal in existing}
    signals: list[TrendSignal] = []

    for kind in kinds:
        for item_id in _hn_story_ids(kind)[:max_ids_per_kind]:
            item = _hn_item(item_id)
            if not item or item.get("type") != "story":
                continue
            title = str(item.get("title", ""))
            url = str(item.get("url", ""))
            if not _matches_ai(title, url):
                continue
            score = int(item.get("score", 0) or 0)
            comments = int(item.get("descendants", 0) or 0)
            if score < min_score and comments < min_comments:
                continue
            signal_id = f"hn_{item_id}"
            if signal_id in existing_ids:
                continue
            discussion_url = f"https://news.ycombinator.com/item?id={item_id}"
            signal = TrendSignal(
                signal_id=signal_id,
                platform="hacker_news",
                title=title,
                url=url or discussion_url,
                discussion_url=discussion_url,
                author=str(item.get("by", "")),
                published_at=_published_at(item.get("time")),
                fetched_at=utc_now_iso(),
                score=score,
                comments=comments,
                engagement_score=score + comments * 2,
                topic=_topic(title),
                risk_notes="HN e uma comunidade tecnica, nao representa o mercado portugues.",
            )
            signal.why_it_worked = _why_it_worked(signal)
            signal.ptia_angle = _ptia_angle(signal)
            signals.append(signal)
            existing_ids.add(signal_id)

    signals.sort(key=lambda signal: signal.engagement_score, reverse=True)
    append_jsonl(out_path, signals)
    return signals


def trend_to_markdown(signals: list[TrendSignal], limit: int = 20) -> str:
    lines = [
        "# PTIA Trend Radar",
        "",
        "Sinais de engagement fora de Portugal. Isto nao e uma lista de posts a copiar; e input para curadoria.",
        "",
    ]
    for index, signal in enumerate(signals[:limit], start=1):
        lines.extend(
            [
                f"## {index}. {signal.title}",
                "",
                f"- Plataforma: {signal.platform}",
                f"- Topic: {signal.topic}",
                f"- Score: {signal.score}",
                f"- Comentarios: {signal.comments}",
                f"- Engagement score: {signal.engagement_score}",
                f"- Link: {signal.url}",
                f"- Discussao: {signal.discussion_url}",
                f"- Porque funcionou: {signal.why_it_worked}",
                f"- Angulo PTIA: {signal.ptia_angle}",
                f"- Risco: {signal.risk_notes}",
                "",
            ]
        )
    return "\n".join(lines)
