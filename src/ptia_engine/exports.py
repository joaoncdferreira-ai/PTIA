from __future__ import annotations

import csv
import json
from pathlib import Path

from ptia_engine.storage import load_content_drafts, load_processed_items, load_raw_articles


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_sources_csv(sources_json: Path, out_path: Path) -> None:
    rows = json.loads(sources_json.read_text(encoding="utf-8"))
    _write_csv(out_path, rows)


def export_raw_articles_csv(raw_articles_jsonl: Path, out_path: Path) -> None:
    rows = [article.to_record() for article in load_raw_articles(raw_articles_jsonl)]
    _write_csv(out_path, rows)


def export_processed_items_csv(processed_items_jsonl: Path, out_path: Path) -> None:
    rows = [item.to_record() for item in load_processed_items(processed_items_jsonl)]
    _write_csv(out_path, rows)


def export_content_drafts_csv(content_drafts_jsonl: Path, out_path: Path) -> None:
    rows = [draft.to_record() for draft in load_content_drafts(content_drafts_jsonl)]
    _write_csv(out_path, rows)
