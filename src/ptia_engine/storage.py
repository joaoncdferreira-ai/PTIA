from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, TypeVar

from ptia_engine.models import (
    ContentDraft,
    ContentAsset,
    ContentPerformance,
    EditorialTopic,
    FinalPost,
    NewsletterIssue,
    ProcessedItem,
    RawArticle,
    RadarSignal,
    TrendSignal,
)


class JSONRecord(Protocol):
    def to_record(self) -> dict: ...


T = TypeVar("T")


def load_jsonl(path: Path, factory: type[T]) -> list[T]:
    if not path.exists():
        return []
    records: list[T] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(factory.from_record(json.loads(line)))  # type: ignore[attr-defined]
    return records


def append_jsonl(path: Path, records: list[JSONRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        try:
            with path.open("rb") as f:
                f.seek(-1, 2)
                if f.read(1) != b"\n":
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write("\n")
        except Exception:
            pass
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_record(), ensure_ascii=False) + "\n")


def write_jsonl(path: Path, records: list[JSONRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.to_record(), ensure_ascii=False) + "\n")
        import os
        os.replace(str(tmp_path), str(path))
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise e


def load_raw_articles(path: Path) -> list[RawArticle]:
    return load_jsonl(path, RawArticle)


def load_processed_items(path: Path) -> list[ProcessedItem]:
    return load_jsonl(path, ProcessedItem)


def load_content_drafts(path: Path) -> list[ContentDraft]:
    return load_jsonl(path, ContentDraft)


def load_content_performance(path: Path) -> list[ContentPerformance]:
    return load_jsonl(path, ContentPerformance)


def load_trend_signals(path: Path) -> list[TrendSignal]:
    return load_jsonl(path, TrendSignal)


def load_content_assets(path: Path) -> list[ContentAsset]:
    return load_jsonl(path, ContentAsset)


def load_radar_signals(path: Path) -> list[RadarSignal]:
    return load_jsonl(path, RadarSignal)


def load_editorial_topics(path: Path) -> list[EditorialTopic]:
    return load_jsonl(path, EditorialTopic)


def load_final_posts(path: Path) -> list[FinalPost]:
    return load_jsonl(path, FinalPost)


def load_newsletter_issues(path: Path) -> list[NewsletterIssue]:
    return load_jsonl(path, NewsletterIssue)
