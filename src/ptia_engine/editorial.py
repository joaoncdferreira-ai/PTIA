from __future__ import annotations

import csv
from pathlib import Path

from ptia_engine.models import ContentDraft, ContentPerformance, ProcessedItem, utc_now_iso
from ptia_engine.storage import (
    append_jsonl,
    load_content_assets,
    load_content_drafts,
    load_processed_items,
    write_jsonl,
)

VALID_ITEM_STATUSES = {
    "needs_review",
    "needs_source_check",
    "approved_for_draft",
    "draft_ready",
    "approved_for_schedule",
    "scheduled",
    "published",
    "rejected",
}

VALID_DRAFT_STATUSES = {
    "draft",
    "needs_edit",
    "approved",
    "scheduled",
    "published",
    "rejected",
}


def update_item_status(
    processed_path: Path,
    item_id: str,
    status: str,
    editor_notes: str = "",
) -> ProcessedItem:
    if status not in VALID_ITEM_STATUSES:
        raise ValueError(f"Invalid item status: {status}")
    items = load_processed_items(processed_path)
    for item in items:
        if item.item_id != item_id:
            continue
        item.editorial_status = status
        if editor_notes:
            timestamp = utc_now_iso()
            note = f"[{timestamp}] {editor_notes}"
            item.editor_notes = f"{item.editor_notes}\n{note}".strip()
        write_jsonl(processed_path, items)
        return item
    raise ValueError(f"Item not found: {item_id}")


def update_draft_status(
    drafts_path: Path,
    draft_id: str,
    status: str,
    scheduled_time: str = "",
    published_url: str = "",
    buffer_post_id: str = "",
) -> ContentDraft:
    if status not in VALID_DRAFT_STATUSES:
        raise ValueError(f"Invalid draft status: {status}")
    drafts = load_content_drafts(drafts_path)
    for draft in drafts:
        if draft.draft_id != draft_id:
            continue
        draft.status = status
        if scheduled_time:
            draft.scheduled_time = scheduled_time
        if published_url:
            draft.published_url = published_url
        if buffer_post_id:
            draft.buffer_post_id = buffer_post_id
        write_jsonl(drafts_path, drafts)
        return draft
    raise ValueError(f"Draft not found: {draft_id}")


def draft_text(draft: ContentDraft) -> str:
    return draft.body or draft.caption or draft.carousel_outline


def export_scheduling_queue(
    drafts_path: Path,
    out_path: Path,
    statuses: set[str] | None = None,
    channels: set[str] | None = None,
) -> int:
    statuses = statuses or {"approved"}
    channels = channels or {"linkedin", "instagram"}
    drafts = [
        draft
        for draft in load_content_drafts(drafts_path)
        if draft.status in statuses and draft.channel in channels
    ]
    assets_path = drafts_path.parent / "content_assets.jsonl"
    assets_by_draft = {}
    if assets_path.exists():
        for asset in load_content_assets(assets_path):
            assets_by_draft.setdefault(asset.draft_id, []).append(asset.file_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "draft_id",
        "item_id",
        "channel",
        "format",
        "title",
        "text",
        "hashtags",
        "image_paths",
        "scheduled_time",
        "status",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for draft in drafts:
            writer.writerow(
                {
                    "draft_id": draft.draft_id,
                    "item_id": draft.item_id,
                    "channel": draft.channel,
                    "format": draft.format,
                    "title": draft.title,
                    "text": draft_text(draft),
                    "hashtags": draft.hashtags,
                    "image_paths": " | ".join(assets_by_draft.get(draft.draft_id, [])),
                    "scheduled_time": draft.scheduled_time,
                    "status": draft.status,
                }
            )
    return len(drafts)


def add_performance_record(performance_path: Path, record: ContentPerformance) -> ContentPerformance:
    append_jsonl(performance_path, [record])
    return record
