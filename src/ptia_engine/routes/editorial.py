from __future__ import annotations

from ptia_engine.dedupe import stable_hash
from ptia_engine.editorial import add_performance_record, update_draft_status, update_item_status
from ptia_engine.models import ContentPerformance, utc_now_iso
from ptia_engine.routes.common import send_ok, to_dict
from ptia_engine.storage import load_content_drafts, load_processed_items


def handle_item_status(handler, payload) -> None:
    item = update_item_status(
        handler.state.processed_path,
        item_id=str(payload["item_id"]),
        status=str(payload["status"]),
        editor_notes=str(payload.get("notes", "")),
    )
    send_ok(handler, item=to_dict(item))


def handle_draft_status(handler, payload) -> None:
    draft = update_draft_status(
        handler.state.drafts_path,
        draft_id=str(payload["draft_id"]),
        status=str(payload["status"]),
        scheduled_time=str(payload.get("scheduled_time", "")),
        published_url=str(payload.get("published_url", "")),
        buffer_post_id=str(payload.get("buffer_post_id", "")),
    )
    send_ok(handler, draft=to_dict(draft))


def handle_performance(handler, payload) -> None:
    draft_id = str(payload["draft_id"])
    drafts = {draft.draft_id: draft for draft in load_content_drafts(handler.state.drafts_path)}
    items = {item.item_id: item for item in load_processed_items(handler.state.processed_path)}
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
    add_performance_record(handler.state.performance_path, record)
    send_ok(handler, performance=to_dict(record))
