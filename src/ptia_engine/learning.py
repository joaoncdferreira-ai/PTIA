from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from ptia_engine.editorial import draft_text
from ptia_engine.models import ContentPerformance
from ptia_engine.storage import load_content_drafts, load_content_performance, load_processed_items


def engagement_score(perf: ContentPerformance) -> int:
    return (
        perf.likes
        + perf.clicks
        + perf.comments * 2
        + perf.shares * 3
        + perf.saves * 3
        + perf.followers_gained * 4
    )


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


def generate_learning_weights(
    processed_path: Path,
    drafts_path: Path,
    performance_path: Path,
    min_samples: int = 3,
) -> dict:
    items = {item.item_id: item for item in load_processed_items(processed_path)}
    drafts = {draft.draft_id: draft for draft in load_content_drafts(drafts_path)}
    performance = load_content_performance(performance_path)
    rows = []

    for perf in performance:
        draft = drafts.get(perf.draft_id)
        item = items.get(draft.item_id) if draft else None
        if not draft or not item:
            continue
        rows.append(
            {
                "score": engagement_score(perf),
                "source_id": item.source_id,
                "source_name": item.source_name,
                "section": item.section,
                "channel": draft.channel,
                "format": draft.format,
                "title": draft.title,
                "text_length": len(draft_text(draft)),
            }
        )

    baseline = mean([row["score"] for row in rows]) if rows else 0.0
    weights = {
        "version": 1,
        "min_samples": min_samples,
        "baseline_score": round(baseline, 2),
        "sample_count": len(rows),
        "source_boosts": {},
        "section_boosts": {},
        "channel_notes": {},
        "recommendations": [],
    }

    if len(rows) < min_samples:
        weights["recommendations"].append(
            "Amostra insuficiente para alterar a classificacao. Continuar a recolher metricas."
        )
        return weights

    grouped = {
        "source_boosts": defaultdict(list),
        "section_boosts": defaultdict(list),
        "channel_notes": defaultdict(list),
    }
    source_names = {}
    for row in rows:
        grouped["source_boosts"][row["source_id"]].append(row["score"])
        grouped["section_boosts"][row["section"]].append(row["score"])
        grouped["channel_notes"][row["channel"]].append(row["score"])
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
