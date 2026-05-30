from __future__ import annotations

from pathlib import Path

from ptia_engine.dedupe import stable_hash
from ptia_engine.editorial import add_performance_record
from ptia_engine.meta_insights import InstagramMediaInsights, MetaGraphClient
from ptia_engine.models import ContentPerformance, FinalPost, utc_now_iso
from ptia_engine.storage import load_content_performance, load_final_posts, write_jsonl


def _normalise(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _match_instagram_post(row: InstagramMediaInsights, final_posts: list[FinalPost]) -> FinalPost | None:
    caption = _normalise(row.caption)
    for post in final_posts:
        if post.channel != "instagram":
            continue
        if row.permalink and row.permalink == post.published_url:
            return post
        title = _normalise(post.title)
        body = _normalise(post.body)
        if title and title in caption:
            return post
        first_sentence = body.split(".")[0].strip()
        if first_sentence and first_sentence in caption:
            return post
    return None


def _upsert_performance(path: Path, record: ContentPerformance) -> ContentPerformance:
    existing = load_content_performance(path)
    for index, item in enumerate(existing):
        if item.performance_id == record.performance_id:
            existing[index] = record
            write_jsonl(path, existing)
            return record
    add_performance_record(path, record)
    return record


def import_instagram_insights(
    *,
    final_posts_path: Path,
    performance_path: Path,
    limit: int = 25,
    client: MetaGraphClient | None = None,
) -> list[ContentPerformance]:
    client = client or MetaGraphClient()
    final_posts = load_final_posts(final_posts_path)
    records: list[ContentPerformance] = []
    for row in client.recent_media_insights(limit=limit):
        post = _match_instagram_post(row, final_posts)
        post_id = post.post_id if post else row.permalink or row.media_id
        title = post.title if post else (row.caption[:90] or "Instagram post")
        section = "Instagram"
        performance_id = f"meta_ig_{stable_hash(row.media_id, 18)}"
        record = ContentPerformance(
            performance_id=performance_id,
            draft_id=post.post_id if post else "",
            post_id=post_id,
            channel="instagram",
            published_at=row.timestamp,
            topic=title,
            section=section,
            impressions=row.impressions,
            likes=row.likes,
            comments=row.comments,
            shares=row.shares,
            saves=row.saves,
            clicks=0,
            followers_gained=0,
            notes=(
                f"Meta media_id={row.media_id}; reach={row.reach}; "
                f"total_interactions={row.total_interactions}; permalink={row.permalink}"
            ),
            created_at=utc_now_iso(),
        )
        records.append(_upsert_performance(performance_path, record))
    return records
