from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ptia_engine.dedupe import stable_hash
from ptia_engine.models import EditorialTopic, FinalPost, RadarSignal, utc_now_iso
from ptia_engine.storage import (
    append_jsonl,
    load_editorial_topics,
    load_final_posts,
    load_radar_signals,
    write_jsonl,
)


VALID_SIGNAL_STATUSES = {
    "verifying",
    "verified",
    "verified_secondary",
    "selected",
    "new",
    "topic_candidate",
    "used",
    "rejected",
}
VALID_TOPIC_STATUSES = {"needs_review", "approved_for_final", "final_ready", "rejected", "published"}
VALID_POST_STATUSES = {"needs_final_review", "approved_for_schedule", "scheduled", "published", "rejected"}


def _parse_signal_date(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("Radar signals need an exact published_at date.")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    if len(raw) == 10:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ensure_recent_signal(published_at: str, max_age_days: int = 5) -> None:
    published = _parse_signal_date(published_at)
    now = datetime.now(timezone.utc)
    earliest = now - timedelta(days=max_age_days)
    if published < earliest:
        raise ValueError(
            f"Radar signal is too old: {published_at}. Max age is {max_age_days} days."
        )
    if published > now + timedelta(days=1):
        raise ValueError(f"Radar signal date is in the future: {published_at}.")


def add_radar_signal(
    path: Path,
    *,
    source_type: str,
    source_name: str,
    title: str,
    url: str,
    published_at: str = "",
    engagement_score: int = 0,
    summary: str = "",
    topic_hint: str = "",
    why_it_matters: str = "",
    why_engaged: str = "",
    notes: str = "",
    max_age_days: int = 5,
    status: str = "new",
    require_recent: bool = True,
) -> RadarSignal:
    if status not in VALID_SIGNAL_STATUSES:
        raise ValueError(f"Invalid signal status: {status}")
    if require_recent:
        ensure_recent_signal(published_at, max_age_days=max_age_days)
    signal = RadarSignal(
        signal_id=f"sig_{stable_hash(f'{source_type}:{url}:{title}', 18)}",
        source_type=source_type,
        source_name=source_name,
        title=title,
        url=url,
        published_at=published_at,
        engagement_score=engagement_score,
        summary=summary,
        topic_hint=topic_hint,
        why_it_matters=why_it_matters,
        why_engaged=why_engaged,
        status=status,
        notes=notes,
    )
    existing = {item.signal_id for item in load_radar_signals(path)}
    if signal.signal_id not in existing:
        append_jsonl(path, [signal])
    return signal


def update_signal_status(path: Path, signal_id: str, status: str, notes: str = "") -> RadarSignal:
    if status not in VALID_SIGNAL_STATUSES:
        raise ValueError(f"Invalid signal status: {status}")
    signals = load_radar_signals(path)
    for signal in signals:
        if signal.signal_id != signal_id:
            continue
        signal.status = status
        if notes:
            signal.notes = f"{signal.notes}\n[{utc_now_iso()}] {notes}".strip()
        write_jsonl(path, signals)
        return signal
    raise ValueError(f"Signal not found: {signal_id}")


def add_editorial_topic(
    path: Path,
    *,
    title: str,
    thesis: str,
    portugal_angle: str,
    audience: str,
    source_signal_ids: list[str],
    urgency_score: int = 0,
) -> EditorialTopic:
    topic = EditorialTopic(
        topic_id=f"topic_{stable_hash(f'{title}:{thesis}', 18)}",
        title=title,
        thesis=thesis,
        portugal_angle=portugal_angle,
        audience=audience,
        source_signal_ids=source_signal_ids,
        urgency_score=urgency_score,
    )
    existing = {item.topic_id for item in load_editorial_topics(path)}
    if topic.topic_id not in existing:
        append_jsonl(path, [topic])
    return topic


def update_topic_status(path: Path, topic_id: str, status: str, notes: str = "") -> EditorialTopic:
    if status not in VALID_TOPIC_STATUSES:
        raise ValueError(f"Invalid topic status: {status}")
    topics = load_editorial_topics(path)
    for topic in topics:
        if topic.topic_id != topic_id:
            continue
        topic.status = status
        if notes:
            topic.editor_notes = f"{topic.editor_notes}\n[{utc_now_iso()}] {notes}".strip()
        write_jsonl(path, topics)
        return topic
    raise ValueError(f"Topic not found: {topic_id}")


def add_final_post(
    path: Path,
    *,
    topic_id: str,
    channel: str,
    title: str,
    body: str,
    hashtags: str,
    image_prompt: str,
    source_urls: list[str],
    image_path: str = "",
    image_variants: dict[str, str] | None = None,
    editor_notes: str = "",
) -> FinalPost:
    post = FinalPost(
        post_id=f"post_{stable_hash(f'{topic_id}:{channel}:{title}', 18)}",
        topic_id=topic_id,
        channel=channel,
        title=title,
        body=body,
        hashtags=hashtags,
        image_prompt=image_prompt,
        source_urls=source_urls,
        image_path=image_path,
        image_variants=image_variants or {},
        editor_notes=editor_notes,
    )
    existing = {item.post_id for item in load_final_posts(path)}
    if post.post_id not in existing:
        append_jsonl(path, [post])
    return post


def update_final_post_status(
    path: Path,
    post_id: str,
    status: str,
    scheduled_time: str = "",
    buffer_post_id: str | None = None,
    published_url: str = "",
    image_path: str = "",
    image_variants: dict[str, str] | None = None,
    image_status: str = "",
) -> FinalPost:
    if status not in VALID_POST_STATUSES:
        raise ValueError(f"Invalid final post status: {status}")
    posts = load_final_posts(path)
    for post in posts:
        if post.post_id != post_id:
            continue
        post.status = status
        if scheduled_time:
            post.scheduled_time = scheduled_time
        if buffer_post_id is not None:
            post.buffer_post_id = buffer_post_id
        if published_url:
            post.published_url = published_url
        if image_path:
            post.image_path = image_path
        if image_variants is not None:
            post.image_variants = image_variants
        if image_status:
            post.image_status = image_status
        write_jsonl(path, posts)
        return post
    raise ValueError(f"Final post not found: {post_id}")


def update_final_post_copy(
    path: Path,
    post_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
    hashtags: str | None = None,
    image_prompt: str | None = None,
    notes: str = "",
) -> FinalPost:
    posts = load_final_posts(path)
    for post in posts:
        if post.post_id != post_id:
            continue
        if title is not None:
            post.title = title
        if body is not None:
            post.body = body
        if hashtags is not None:
            post.hashtags = hashtags
        if image_prompt is not None:
            post.image_prompt = image_prompt
        if notes:
            post.editor_notes = f"{post.editor_notes}\n[{utc_now_iso()}] {notes}".strip()
        write_jsonl(path, posts)
        return post
    raise ValueError(f"Final post not found: {post_id}")
