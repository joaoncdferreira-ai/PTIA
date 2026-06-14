from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from ptia_engine.editorial import draft_text
from ptia_engine.models import ContentPerformance
from ptia_engine.storage import (
    load_content_drafts,
    load_content_performance,
    load_final_posts,
    load_processed_items,
)


def engagement_score(perf: ContentPerformance) -> int:
    return (
        perf.likes
        + perf.clicks * 2
        + perf.comments * 2
        + perf.shares * 3
        + perf.saves * 3
        + perf.followers_gained * 4
        + perf.site_views
        + perf.unique_visitors * 2
        + perf.newsletter_signups * 8
    )


def learning_score(perf: ContentPerformance) -> int:
    """Weighted engagement per 1,000 impressions, shrunk below 100 impressions."""
    raw_score = engagement_score(perf)
    if perf.impressions <= 0:
        return raw_score
    return min(100, round(raw_score * 1000 / max(100, perf.impressions)))


def _boost(avg_score: float, baseline: float) -> int:
    if baseline <= 0:
        return 0
    ratio = avg_score / baseline
    if ratio >= 1.6:
        return 2
    if ratio >= 1.2:
        return 1
    if ratio <= 0.45:
        return -2
    if ratio <= 0.75:
        return -1
    return 0


def _length_bucket(length: int) -> str:
    if length < 500:
        return "short"
    if length < 1100:
        return "medium"
    return "long"


def _pattern_adjustment(scores: list[int], baseline: float, min_samples: int) -> dict:
    average = mean(scores) if scores else 0.0
    adjustment = 0
    if len(scores) >= min_samples and baseline > 0:
        adjustment = max(-6, min(6, round((average / baseline - 1.0) * 10)))
    return {
        "avg_score": round(average, 2),
        "sample_count": len(scores),
        "adjustment": adjustment,
    }


def _editorial_patterns(rows: list[dict], baseline: float, min_samples: int) -> dict:
    groups = {
        "question": {"present": [], "absent": []},
        "local_relevance": {"present": [], "absent": []},
        "length": {"short": [], "medium": [], "long": []},
    }
    for row in rows:
        score = row["score"]
        groups["question"]["present" if row["has_question"] else "absent"].append(score)
        groups["local_relevance"]["present" if row["local_relevance"] else "absent"].append(score)
        groups["length"][row["length_bucket"]].append(score)
    return {
        name: {
            value: _pattern_adjustment(scores, baseline, min_samples)
            for value, scores in values.items()
        }
        for name, values in groups.items()
    }


def generate_learning_weights(
    processed_path: Path,
    drafts_path: Path,
    performance_path: Path,
    min_samples: int = 3,
    final_posts_path: Path | None = None,
) -> dict:
    items = {item.item_id: item for item in load_processed_items(processed_path)}
    drafts = {draft.draft_id: draft for draft in load_content_drafts(drafts_path)}
    performance = load_content_performance(performance_path)
    final_posts = {
        post.post_id: post
        for post in load_final_posts(final_posts_path)
    } if final_posts_path else {}
    rows = []

    for perf in performance:
        draft = drafts.get(perf.draft_id)
        item = items.get(draft.item_id) if draft else None
        if draft and item:
            text = draft_text(draft)
            rows.append(
                {
                    "score": learning_score(perf),
                    "source_id": item.source_id,
                    "source_name": item.source_name,
                    "section": item.section,
                    "channel": draft.channel,
                    "format": draft.format,
                    "title": draft.title,
                    "text_length": len(text),
                    "length_bucket": _length_bucket(len(text)),
                    "has_question": "?" in text,
                    "local_relevance": any(
                        term in text.casefold()
                        for term in ("portugal", "português", "portuguesa", "lisboa", "porto")
                    ),
                }
            )
            continue
        final_post = final_posts.get(perf.post_id) or final_posts.get(perf.draft_id)
        if not final_post:
            continue
        text = f"{final_post.title}\n{final_post.body}"
        rows.append(
            {
                "score": learning_score(perf),
                "source_id": "",
                "source_name": "",
                "section": perf.section or "Editorial",
                "channel": final_post.channel,
                "format": "final_post",
                "title": final_post.title,
                "text_length": len(text),
                "length_bucket": _length_bucket(len(text)),
                "has_question": "?" in text,
                "local_relevance": any(
                    term in text.casefold()
                    for term in ("portugal", "português", "portuguesa", "lisboa", "porto")
                ),
            }
        )

    baseline = mean([row["score"] for row in rows]) if rows else 0.0
    weights = {
        "version": 2,
        "min_samples": min_samples,
        "baseline_score": round(baseline, 2),
        "sample_count": len(rows),
        "source_boosts": {},
        "section_boosts": {},
        "channel_notes": {},
        "editorial_patterns": {},
        "recommendations": [],
    }

    if len(rows) < min_samples:
        weights["recommendations"].append(
            "Amostra insuficiente para alterar a classificacao. Continuar a recolher metricas."
        )
        return weights

    pattern_min_samples = max(5, min_samples)
    weights["editorial_patterns"] = _editorial_patterns(rows, baseline, pattern_min_samples)

    grouped = {
        "source_boosts": defaultdict(list),
        "section_boosts": defaultdict(list),
        "channel_notes": defaultdict(list),
    }
    source_names = {}
    for row in rows:
        if row["source_id"]:
            grouped["source_boosts"][row["source_id"]].append(row["score"])
        grouped["section_boosts"][row["section"]].append(row["score"])
        grouped["channel_notes"][row["channel"]].append(row["score"])
        if row["source_id"]:
            source_names[row["source_id"]] = row["source_name"]

    for source_id, scores in grouped["source_boosts"].items():
        if len(scores) < min_samples:
            continue
        boost = _boost(mean(scores), baseline)
        if boost:
            weights["source_boosts"][source_id] = {
                "boost": boost,
                "avg_score": round(mean(scores), 2),
                "sample_count": len(scores),
                "source_name": source_names.get(source_id, source_id),
            }

    for section, scores in grouped["section_boosts"].items():
        if len(scores) < min_samples:
            continue
        boost = _boost(mean(scores), baseline)
        if boost:
            weights["section_boosts"][section] = {
                "boost": boost,
                "avg_score": round(mean(scores), 2),
                "sample_count": len(scores),
            }

    for channel, scores in grouped["channel_notes"].items():
        if len(scores) < min_samples:
            continue
        weights["channel_notes"][channel] = {
            "avg_score": round(mean(scores), 2),
            "sample_count": len(scores),
        }

    if weights["source_boosts"]:
        best_sources = sorted(
            weights["source_boosts"].items(),
            key=lambda item: item[1]["boost"],
            reverse=True,
        )
        weights["recommendations"].append(
            "Ajustar prioridade por fonte: "
            + ", ".join(f"{source} ({data['boost']:+d})" for source, data in best_sources)
            + "."
        )
    if weights["section_boosts"]:
        best_sections = sorted(
            weights["section_boosts"].items(),
            key=lambda item: item[1]["boost"],
            reverse=True,
        )
        weights["recommendations"].append(
            "Ajustar prioridade por seccao: "
            + ", ".join(f"{section} ({data['boost']:+d})" for section, data in best_sections)
            + "."
        )
    pattern_adjustments = [
        (f"{group}:{value}", data["adjustment"])
        for group, values in weights["editorial_patterns"].items()
        for value, data in values.items()
        if data["adjustment"]
    ]
    if pattern_adjustments:
        weights["recommendations"].append(
            "Aplicar sinais editoriais conservadores: "
            + ", ".join(
                f"{name} ({adjustment:+d})"
                for name, adjustment in pattern_adjustments
            )
            + "."
        )
    if not weights["recommendations"]:
        weights["recommendations"].append(
            "Performance ainda sem padroes fortes. Manter pesos neutros e continuar a medir."
        )

    return weights


def load_learning_weights(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_learning_weights(path: Path, weights: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")
