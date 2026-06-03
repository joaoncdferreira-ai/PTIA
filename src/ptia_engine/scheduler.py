from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ptia_engine.models import FinalPost, utc_now_iso
from ptia_engine.growth import tracked_article_url_for_social
from ptia_engine.services.channels import expected_schedule_channels, load_channel_config
from ptia_engine.services.editorial_hygiene import copy_quality_issues
from ptia_engine.services.media import image_path_for_channel, public_image_url
from ptia_engine.storage import load_final_posts


SOCIAL_CHANNELS = {"instagram", "linkedin", "x"}
SCHEDULABLE_STATUSES = {"approved_for_schedule", "scheduled"}


@dataclass(slots=True)
class SchedulePostCheck:
    post_id: str
    topic_id: str
    channel: str
    title: str
    status: str
    scheduled_time: str
    buffer_post_id: str = ""
    image_path: str = ""
    public_image_url: str = ""
    action: str = "noop"
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScheduleSlot:
    topic_id: str
    scheduled_time: str

    def to_record(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ScheduleTopicCheck:
    topic_id: str
    scheduled_time: str
    posts: list[SchedulePostCheck]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def channels(self) -> list[str]:
        return sorted({post.channel for post in self.posts})

    def to_record(self) -> dict:
        payload = asdict(self)
        payload["channels"] = self.channels
        return payload


@dataclass(slots=True)
class ScheduleDayPlan:
    date: str
    dry_run: bool
    topics: list[ScheduleTopicCheck]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def post_count(self) -> int:
        return sum(len(topic.posts) for topic in self.topics)

    @property
    def ready(self) -> bool:
        return not self.issues and all(not topic.issues for topic in self.topics)

    def to_record(self) -> dict:
        return {
            "date": self.date,
            "dry_run": self.dry_run,
            "ready": self.ready,
            "topic_count": len(self.topics),
            "post_count": self.post_count,
            "issues": self.issues,
            "warnings": self.warnings,
            "topics": [topic.to_record() for topic in self.topics],
        }


@dataclass(slots=True)
class ScheduleAction:
    action_id: str
    kind: str
    topic_id: str
    scheduled_time: str
    post_ids: list[str] = field(default_factory=list)
    channel: str = ""
    status: str = "pending"
    payload: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ScheduleExecutionPlan:
    date: str
    dry_run: bool
    actions: list[ScheduleAction]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.issues and all(not action.issues for action in self.actions)

    def to_record(self) -> dict:
        return {
            "date": self.date,
            "dry_run": self.dry_run,
            "ready": self.ready,
            "action_count": len(self.actions),
            "issues": self.issues,
            "warnings": self.warnings,
            "actions": [action.to_record() for action in self.actions],
        }


@dataclass(slots=True)
class ScheduleActionResult:
    action_id: str
    kind: str
    status: str
    external_id: str = ""
    message: str = ""

    def to_record(self) -> dict:
        return asdict(self)


class ScheduleBackend(Protocol):
    def prepare_public_assets(self, action: ScheduleAction) -> ScheduleActionResult: ...

    def schedule_buffer_post(self, action: ScheduleAction) -> ScheduleActionResult: ...

    def schedule_instagram_carousel(self, action: ScheduleAction) -> ScheduleActionResult: ...

    def schedule_site_post(self, action: ScheduleAction) -> ScheduleActionResult: ...

    def sync_site_feed(self, action: ScheduleAction) -> ScheduleActionResult: ...


class NoopScheduleBackend:
    """Execution backend for tests and CLI simulations; it never touches external services."""

    def __init__(self) -> None:
        self.calls: list[ScheduleAction] = []

    def _record(self, action: ScheduleAction) -> ScheduleActionResult:
        self.calls.append(action)
        return ScheduleActionResult(
            action_id=action.action_id,
            kind=action.kind,
            status="noop",
            external_id=f"noop_{action.action_id}",
            message="Noop backend: no external side effect.",
        )

    def prepare_public_assets(self, action: ScheduleAction) -> ScheduleActionResult:
        return self._record(action)

    def schedule_buffer_post(self, action: ScheduleAction) -> ScheduleActionResult:
        return self._record(action)

    def schedule_instagram_carousel(self, action: ScheduleAction) -> ScheduleActionResult:
        return self._record(action)

    def schedule_site_post(self, action: ScheduleAction) -> ScheduleActionResult:
        return self._record(action)

    def sync_site_feed(self, action: ScheduleAction) -> ScheduleActionResult:
        return self._record(action)


def parse_schedule_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def scheduled_date(value: str) -> str:
    if not value:
        return ""
    raw = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        return ""


def load_schedule_slots(path: Path) -> list[ScheduleSlot]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        raw_slots = payload.get("topics") or payload.get("slots") or []
    else:
        raw_slots = payload
    slots = []
    for record in raw_slots:
        topic_id = str(record.get("topic_id", "")).strip()
        scheduled_time = str(record.get("scheduled_time", record.get("time", ""))).strip()
        if not topic_id or not scheduled_time:
            raise ValueError("Each schedule slot needs topic_id and scheduled_time.")
        slots.append(ScheduleSlot(topic_id=topic_id, scheduled_time=scheduled_time))
    return slots


def _copy_issues(post: FinalPost) -> list[str]:
    return copy_quality_issues(post)


def _post_action(post: FinalPost) -> str:
    if post.status == "scheduled":
        return "already_scheduled"
    if post.channel == "site":
        return "would_schedule_site"
    return "would_schedule_buffer"


def check_post(post: FinalPost, *, repo_root: Path, scheduled_time: str = "") -> SchedulePostCheck:
    image_path = image_path_for_channel(post)
    issues = _copy_issues(post)
    warnings: list[str] = []
    effective_scheduled_time = scheduled_time or post.scheduled_time

    if not post.title.strip():
        issues.append("missing title")
    if not post.body.strip():
        issues.append("missing body")
    if not post.source_urls:
        issues.append("missing source_urls")
    if post.channel == "instagram" and not image_path:
        issues.append("instagram requires a final image")
    if post.channel == "x" and not image_path:
        issues.append("x should have a final image")
    if post.status == "scheduled" and post.channel in SOCIAL_CHANNELS and not post.buffer_post_id:
        warnings.append("scheduled social post has no buffer_post_id")
    if post.channel in SOCIAL_CHANNELS and image_path and not Path(image_path).exists() and not image_path.startswith(("http://", "https://")):
        warnings.append("local image path is not present on disk")

    return SchedulePostCheck(
        post_id=post.post_id,
        topic_id=post.topic_id,
        channel=post.channel,
        title=post.title,
        status=post.status,
        scheduled_time=effective_scheduled_time,
        buffer_post_id=post.buffer_post_id,
        image_path=image_path,
        public_image_url=public_image_url(post, repo_root),
        action=_post_action(post),
        issues=list(dict.fromkeys(issues)),
        warnings=list(dict.fromkeys(warnings)),
    )


def build_schedule_day_plan(
    *,
    repo_root: Path,
    date: str,
    final_posts_path: Path | None = None,
    buffer_channels_path: Path | None = None,
    slots: list[ScheduleSlot] | None = None,
    dry_run: bool = True,
) -> ScheduleDayPlan:
    target_date = parse_schedule_date(date)
    posts_path = final_posts_path or repo_root / "data" / "final_posts.jsonl"
    channels_path = buffer_channels_path or repo_root / "data" / "buffer_channels.json"
    channel_config = load_channel_config(channels_path)
    required_channels = expected_schedule_channels(channel_config)

    all_posts = load_final_posts(posts_path)
    slot_by_topic = {slot.topic_id: slot for slot in slots or []}
    if slot_by_topic:
        bad_slots = [
            f"{slot.topic_id}: {slot.scheduled_time}"
            for slot in slot_by_topic.values()
            if scheduled_date(slot.scheduled_time) != target_date
        ]
        if bad_slots:
            plan = ScheduleDayPlan(date=target_date, dry_run=dry_run, topics=[])
            plan.issues.append("plan contains slots outside target date: " + "; ".join(bad_slots))
            return plan
        matching_posts = [
            post
            for post in all_posts
            if post.status in SCHEDULABLE_STATUSES and post.topic_id in slot_by_topic
        ]
    else:
        matching_posts = [
            post
            for post in all_posts
            if post.status in SCHEDULABLE_STATUSES and scheduled_date(post.scheduled_time) == target_date
        ]
    matching_posts.sort(key=lambda post: (post.scheduled_time, post.topic_id, post.channel))

    topics_by_id: dict[str, list[FinalPost]] = {}
    for post in matching_posts:
        topics_by_id.setdefault(post.topic_id, []).append(post)
    missing_slot_topics = sorted(set(slot_by_topic) - set(topics_by_id))

    topic_checks: list[ScheduleTopicCheck] = []
    for topic_id, topic_posts in sorted(
        topics_by_id.items(),
        key=lambda item: min(post.scheduled_time for post in item[1]),
    ):
        slot = slot_by_topic.get(topic_id)
        effective_scheduled_time = slot.scheduled_time if slot else min(post.scheduled_time for post in topic_posts)
        checks = [
            check_post(post, repo_root=repo_root, scheduled_time=effective_scheduled_time)
            for post in topic_posts
        ]
        channels = [post.channel for post in topic_posts]
        issues: list[str] = []
        warnings: list[str] = []
        missing = sorted(required_channels - set(channels))
        if missing:
            issues.append("missing channels: " + ", ".join(missing))
        duplicates = sorted({channel for channel in channels if channels.count(channel) > 1})
        if duplicates:
            issues.append("duplicate channels: " + ", ".join(duplicates))
        if slot:
            drift = sorted(
                {
                    post.scheduled_time
                    for post in topic_posts
                    if post.scheduled_time and post.scheduled_time != slot.scheduled_time
                }
            )
            if drift:
                warnings.append("posts already carry different scheduled_time values: " + ", ".join(drift))
        elif len({post.scheduled_time for post in topic_posts}) > 1:
            warnings.append("topic package has mixed scheduled_time values")
        for check in checks:
            issues.extend(f"{check.channel}: {issue}" for issue in check.issues)
            warnings.extend(f"{check.channel}: {warning}" for warning in check.warnings)
        topic_checks.append(
            ScheduleTopicCheck(
                topic_id=topic_id,
                scheduled_time=effective_scheduled_time,
                posts=checks,
                issues=list(dict.fromkeys(issues)),
                warnings=list(dict.fromkeys(warnings)),
            )
        )

    plan = ScheduleDayPlan(date=target_date, dry_run=dry_run, topics=topic_checks)
    if missing_slot_topics:
        plan.issues.append("plan topics without schedulable posts: " + ", ".join(missing_slot_topics))
    if not matching_posts:
        plan.warnings.append("no schedulable posts found for date")
    return plan


def _post_by_id(posts: list[FinalPost]) -> dict[str, FinalPost]:
    return {post.post_id: post for post in posts}


def _first_paragraph(text: str) -> str:
    return str(text or "").strip().split("\n\n", 1)[0].strip()


def build_instagram_carousel_caption(posts: list[FinalPost]) -> str:
    paragraphs = []
    sources = []
    hashtags = "#InteligenciaArtificial #IA #Produtividade #Negocios #Gestao #Governanca #Portugal #PTIA"
    for index, post in enumerate(posts, start=1):
        first = _first_paragraph(post.body)
        if first:
            paragraphs.append(f"{index}. {first}")
        if post.source_urls:
            sources.append(f"- {post.source_urls[0]}")
    parts = ["\n\n".join(paragraphs).strip(), hashtags]
    if sources:
        parts.append("Fontes:\n" + "\n".join(sources))
    return "\n\n".join(part for part in parts if part).strip()


def _action_id(kind: str, post_ids: list[str], scheduled_time: str) -> str:
    compact_time = scheduled_time.replace(":", "").replace("-", "").replace("+", "_")
    return f"{kind}_{compact_time}_{'_'.join(post_ids)[:80]}"


def _action_from_post(check: SchedulePostCheck) -> ScheduleAction | None:
    if check.status == "scheduled":
        return ScheduleAction(
            action_id=_action_id("skip_already_scheduled", [check.post_id], check.scheduled_time),
            kind="skip_already_scheduled",
            topic_id=check.topic_id,
            scheduled_time=check.scheduled_time,
            post_ids=[check.post_id],
            channel=check.channel,
            status="skipped",
            payload={"buffer_post_id": check.buffer_post_id},
            warnings=check.warnings,
        )
    if check.channel == "site":
        return ScheduleAction(
            action_id=_action_id("schedule_site_post", [check.post_id], check.scheduled_time),
            kind="schedule_site_post",
            topic_id=check.topic_id,
            scheduled_time=check.scheduled_time,
            post_ids=[check.post_id],
            channel="site",
            payload={"post_id": check.post_id},
            issues=check.issues,
            warnings=check.warnings,
        )
    if check.channel in {"linkedin", "x"}:
        return ScheduleAction(
            action_id=_action_id("schedule_buffer_post", [check.post_id], check.scheduled_time),
            kind="schedule_buffer_post",
            topic_id=check.topic_id,
            scheduled_time=check.scheduled_time,
            post_ids=[check.post_id],
            channel=check.channel,
            payload={
                "post_id": check.post_id,
                "channel": check.channel,
                "image_url": check.public_image_url,
            },
            issues=check.issues,
            warnings=check.warnings,
        )
    return None


def build_schedule_execution_plan(
    day_plan: ScheduleDayPlan,
    *,
    final_posts: list[FinalPost],
    dry_run: bool = True,
) -> ScheduleExecutionPlan:
    posts_by_id = _post_by_id(final_posts)
    site_post_by_topic = {
        post.topic_id: post
        for post in final_posts
        if post.channel == "site"
    }
    actions: list[ScheduleAction] = []
    issues = list(day_plan.issues)
    warnings = list(day_plan.warnings)
    instagram_checks: list[SchedulePostCheck] = []
    site_posts_seen = False

    for topic in day_plan.topics:
        if topic.issues:
            issues.extend(f"{topic.topic_id}: {issue}" for issue in topic.issues)
        warnings.extend(f"{topic.topic_id}: {warning}" for warning in topic.warnings)
        for check in topic.posts:
            if check.channel == "instagram":
                instagram_checks.append(check)
                continue
            action = _action_from_post(check)
            if action:
                if action.channel in {"linkedin", "x"}:
                    site_post = site_post_by_topic.get(check.topic_id)
                    if site_post:
                        action.payload["article_url"] = tracked_article_url_for_social(
                            site_post,
                            channel=action.channel,
                            content=check.post_id,
                        )
                actions.append(action)
                site_posts_seen = site_posts_seen or action.kind == "schedule_site_post"

    if instagram_checks:
        instagram_posts = [
            posts_by_id[check.post_id]
            for check in instagram_checks
            if check.post_id in posts_by_id
        ]
        scheduled_times = [check.scheduled_time for check in instagram_checks if check.scheduled_time]
        carousel_time = max(scheduled_times) if scheduled_times else day_plan.date
        all_scheduled = all(check.status == "scheduled" for check in instagram_checks)
        buffer_ids = sorted({check.buffer_post_id for check in instagram_checks if check.buffer_post_id})
        post_ids = [check.post_id for check in instagram_checks]
        carousel_issues = [
            f"{check.post_id}: {issue}"
            for check in instagram_checks
            for issue in check.issues
        ]
        carousel_warnings = [
            f"{check.post_id}: {warning}"
            for check in instagram_checks
            for warning in check.warnings
        ]
        if all_scheduled:
            kind = "skip_instagram_carousel_already_scheduled"
            status = "skipped"
            if len(buffer_ids) > 1:
                carousel_warnings.append("scheduled instagram posts have multiple buffer_post_id values")
        else:
            kind = "schedule_instagram_carousel" if len(instagram_checks) > 1 else "schedule_buffer_post"
            status = "pending"
            if any(check.status == "scheduled" for check in instagram_checks):
                carousel_issues.append("mixed scheduled and unscheduled instagram posts require manual review")
        payload = {
            "post_ids": post_ids,
            "image_urls": [check.public_image_url for check in instagram_checks if check.public_image_url],
            "caption": build_instagram_carousel_caption(instagram_posts),
            "buffer_post_ids": buffer_ids,
        }
        actions.append(
            ScheduleAction(
                action_id=_action_id(kind, post_ids, carousel_time),
                kind=kind,
                topic_id=",".join(sorted({check.topic_id for check in instagram_checks})),
                scheduled_time=carousel_time,
                post_ids=post_ids,
                channel="instagram",
                status=status,
                payload=payload,
                issues=list(dict.fromkeys(carousel_issues)),
                warnings=list(dict.fromkeys(carousel_warnings)),
            )
        )

    asset_post_ids = []
    asset_paths = []
    for action in actions:
        if action.status == "skipped":
            continue
        if action.channel in SOCIAL_CHANNELS:
            asset_post_ids.extend(action.post_ids)
            asset_paths.extend(action.payload.get("image_urls", []))
            image_url = action.payload.get("image_url")
            if image_url:
                asset_paths.append(image_url)
    if asset_post_ids:
        actions.insert(
            0,
            ScheduleAction(
                action_id=_action_id("prepare_public_assets", sorted(set(asset_post_ids)), day_plan.date),
                kind="prepare_public_assets",
                topic_id="",
                scheduled_time=day_plan.date,
                post_ids=sorted(set(asset_post_ids)),
                payload={"asset_urls": sorted(set(asset_paths))},
            ),
        )
    if site_posts_seen:
        actions.append(
            ScheduleAction(
                action_id=_action_id("sync_site_feed", ["site"], day_plan.date),
                kind="sync_site_feed",
                topic_id="",
                scheduled_time=day_plan.date,
                post_ids=[],
                channel="site",
            )
        )
    execution_plan = ScheduleExecutionPlan(
        date=day_plan.date,
        dry_run=dry_run,
        actions=actions,
        issues=list(dict.fromkeys(issues)),
        warnings=list(dict.fromkeys(warnings)),
    )
    return execution_plan


def append_schedule_audit(path: Path, *, plan: ScheduleExecutionPlan, results: list[ScheduleActionResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": utc_now_iso(),
        "date": plan.date,
        "dry_run": plan.dry_run,
        "ready": plan.ready,
        "actions": [action.to_record() for action in plan.actions],
        "results": [result.to_record() for result in results],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def execute_schedule_plan(
    plan: ScheduleExecutionPlan,
    *,
    backend: ScheduleBackend,
    confirm_date: str,
    audit_path: Path | None = None,
) -> list[ScheduleActionResult]:
    if confirm_date != plan.date:
        raise ValueError(f"Confirmation mismatch. Expected --confirm {plan.date}.")
    if not plan.ready:
        raise ValueError("Schedule execution plan is blocked by preflight issues.")
    results: list[ScheduleActionResult] = []
    for action in plan.actions:
        if action.status == "skipped":
            results.append(
                ScheduleActionResult(
                    action_id=action.action_id,
                    kind=action.kind,
                    status="skipped",
                    external_id=action.payload.get("buffer_post_id", ""),
                    message="Already scheduled.",
                )
            )
            continue
        if action.kind == "prepare_public_assets":
            result = backend.prepare_public_assets(action)
        elif action.kind == "schedule_buffer_post":
            result = backend.schedule_buffer_post(action)
        elif action.kind == "schedule_instagram_carousel":
            result = backend.schedule_instagram_carousel(action)
        elif action.kind == "schedule_site_post":
            result = backend.schedule_site_post(action)
        elif action.kind == "sync_site_feed":
            result = backend.sync_site_feed(action)
        else:
            raise ValueError(f"Unknown schedule action kind: {action.kind}")
        results.append(result)
    if audit_path:
        append_schedule_audit(audit_path, plan=plan, results=results)
    return results


def format_execution_plan(plan: ScheduleExecutionPlan) -> str:
    status = "READY" if plan.ready else "BLOCKED"
    lines = [
        f"schedule_execution date={plan.date} mode={'dry-run' if plan.dry_run else 'execute'} status={status}",
        f"actions={len(plan.actions)}",
    ]
    if plan.issues:
        lines.append("issues:")
        lines.extend(f"- {issue}" for issue in plan.issues)
    if plan.warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in plan.warnings)
    for action in plan.actions:
        lines.append(
            f"- {action.kind:<42} {action.status:<8} {action.scheduled_time:<25} "
            f"{action.channel:<9} {','.join(action.post_ids)}"
        )
        for issue in action.issues:
            lines.append(f"  issue: {issue}")
        for warning in action.warnings:
            lines.append(f"  warning: {warning}")
    return "\n".join(lines)


def format_schedule_plan(plan: ScheduleDayPlan) -> str:
    status = "READY" if plan.ready else "BLOCKED"
    lines = [
        f"schedule_day date={plan.date} mode={'dry-run' if plan.dry_run else 'execute'} status={status}",
        f"topics={len(plan.topics)} posts={plan.post_count}",
    ]
    if plan.issues:
        lines.append("issues:")
        lines.extend(f"- {issue}" for issue in plan.issues)
    if plan.warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in plan.warnings)
    for topic in plan.topics:
        topic_status = "READY" if not topic.issues else "BLOCKED"
        lines.append("")
        lines.append(
            f"{topic.scheduled_time} {topic.topic_id} channels={','.join(topic.channels)} status={topic_status}"
        )
        for post in topic.posts:
            lines.append(
                f"- {post.channel:<9} {post.status:<21} {post.action:<22} {post.post_id} {post.title[:80]}"
            )
        for issue in topic.issues:
            lines.append(f"  issue: {issue}")
        for warning in topic.warnings:
            lines.append(f"  warning: {warning}")
    return "\n".join(lines)
