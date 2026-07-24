from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.brevo import BrevoClient, BrevoConfig  # noqa: E402
from ptia_engine.cloud_state import CloudStateConfig, hydrate_cloud_state  # noqa: E402
from ptia_engine.http_client import urlopen_direct  # noqa: E402
from ptia_engine.models import FinalPost, NewsletterIssue  # noqa: E402
from ptia_engine.newsletter_delivery import (  # noqa: E402
    PTIA_TIMEZONE,
    next_friday_send_at,
    ptia_timezone,
    schedule_weekly_newsletter,
)
from ptia_engine.services.media import public_image_url  # noqa: E402
from ptia_engine.storage import load_final_posts, write_jsonl  # noqa: E402


REQUIRED_DATASETS = {
    "content_performance.jsonl",
    "final_posts.jsonl",
    "linkedin_comments.jsonl",
    "newsletter_issues.jsonl",
    "radar_signals.jsonl",
    "trend_signals.jsonl",
}

PREPARE_SCHEDULE = "35 18 * * 4"
RECOVERY_SCHEDULE = "5 2 * * 5"
CLOUD_STATE_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})
MAX_PUBLIC_FEED_AGE = timedelta(days=8)


def scheduled_window_is_open(now: datetime, scheduled_cron: str) -> bool:
    local = now.astimezone(ptia_timezone(PTIA_TIMEZONE))
    if scheduled_cron == PREPARE_SCHEDULE:
        return local.weekday() == 3
    if scheduled_cron == RECOVERY_SCHEDULE:
        return local.weekday() == 4 and local.hour < 9
    return False


def resolve_send_at(value: str, now: datetime) -> datetime:
    if not value.strip():
        return next_friday_send_at(now)
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("--send-at must be a valid ISO-8601 datetime") from exc
    timezone = ptia_timezone(PTIA_TIMEZONE)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def ensure_runner_datasets(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED_DATASETS:
        path = data_dir / filename
        if not path.exists():
            path.write_text("", encoding="utf-8")


def _site_feed_posts(payload: object, feed_url: str) -> list[FinalPost]:
    if not isinstance(payload, dict) or not isinstance(payload.get("posts"), list):
        raise RuntimeError("PTIA public site feed must contain a posts list.")
    posts = []
    for index, record in enumerate(payload["posts"]):
        if not isinstance(record, dict):
            raise RuntimeError(f"PTIA public site feed post {index} must be an object.")
        required = ("id", "title", "body", "published_at", "image_url", "article_url")
        missing = [key for key in required if not str(record.get(key, "")).strip()]
        if missing:
            raise RuntimeError(
                f"PTIA public site feed post {index} is missing: {', '.join(missing)}."
            )
        source_urls = record.get("source_urls", [])
        if not isinstance(source_urls, list):
            raise RuntimeError(f"PTIA public site feed post {index} has invalid source_urls.")
        post_id = str(record["id"]).strip()
        published_at = str(record["published_at"]).strip()
        image_url = urljoin(feed_url, str(record["image_url"]).strip())
        posts.append(
            FinalPost(
                post_id=post_id,
                topic_id=post_id,
                channel="site",
                title=str(record["title"]).strip(),
                body=str(record["body"]).strip(),
                hashtags="",
                image_prompt="",
                source_urls=[str(value) for value in source_urls if str(value).strip()],
                image_path=image_url,
                image_variants={"site": image_url},
                image_status="approved",
                status="published",
                scheduled_time=published_at,
                published_url=urljoin(feed_url, str(record["article_url"]).strip()),
                created_at=published_at,
            )
        )
    if not posts:
        raise RuntimeError("PTIA public site feed does not contain any posts.")
    return posts


def hydrate_public_site_feed(data_dir: Path, feed_url: str) -> None:
    separator = "&" if "?" in feed_url else "?"
    request = Request(
        f"{feed_url}{separator}_ptia_newsletter={int(datetime.now().timestamp())}",
        headers={"Accept": "application/json", "User-Agent": "PTIA-Newsletter/1.0"},
    )
    with urlopen_direct(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    updated_at = str(payload.get("updated_at", "")).strip()
    try:
        feed_updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("PTIA public site feed has an invalid updated_at value.") from exc
    if feed_updated_at.tzinfo is None:
        feed_updated_at = feed_updated_at.replace(tzinfo=timezone.utc)
    feed_age = datetime.now(timezone.utc) - feed_updated_at.astimezone(timezone.utc)
    if feed_age > MAX_PUBLIC_FEED_AGE:
        raise RuntimeError("PTIA public site feed is stale; newsletter creation was blocked.")

    current_posts = load_final_posts(data_dir / "final_posts.jsonl")
    posts_by_id = {
        post.post_id: post for post in current_posts if post.channel != "site"
    }
    posts_by_id.update({post.post_id: post for post in _site_feed_posts(payload, feed_url)})
    write_jsonl(data_dir / "final_posts.jsonl", list(posts_by_id.values()))


def validate_public_feed_issue(
    issue: NewsletterIssue,
    data_dir: Path,
    feed_url: str,
) -> None:
    site_posts = {
        post.post_id: post
        for post in load_final_posts(data_dir / "final_posts.jsonl")
        if post.channel == "site"
    }
    missing_ids = [item_id for item_id in issue.item_ids if item_id not in site_posts]
    if missing_ids:
        raise RuntimeError(
            "Newsletter selected items outside the current PTIA site feed: "
            + ", ".join(missing_ids)
        )

    image_tags = re.findall(
        r'<img[^>]*class="ptia-story-image"[^>]*>',
        issue.html,
        flags=re.IGNORECASE,
    )
    if len(image_tags) != len(issue.item_ids):
        raise RuntimeError("Newsletter story image count does not match selected items.")

    public_base_url = urljoin(feed_url, "/")
    for item_id, image_tag in zip(issue.item_ids, image_tags, strict=True):
        attributes = {
            key.casefold(): html.unescape(value)
            for key, value in re.findall(r'([a-zA-Z:-]+)="([^"]*)"', image_tag)
        }
        post = site_posts[item_id]
        expected_image_url = public_image_url(
            post,
            base_url=public_base_url,
            channel="site",
        )
        if attributes.get("alt") != post.title:
            raise RuntimeError(f"Newsletter image title mismatch for {item_id}.")
        if attributes.get("src") != expected_image_url:
            raise RuntimeError(f"Newsletter image URL mismatch for {item_id}.")


def prepare_runner_state(data_dir: Path) -> None:
    ensure_runner_datasets(data_dir)
    is_cloud_state_enabled = (
        os.environ.get("PTIA_CLOUD_STATE_ENABLED", "").strip().lower()
        in CLOUD_STATE_ENABLED_VALUES
    )
    if is_cloud_state_enabled:
        if CloudStateConfig.from_env() is None:
            raise RuntimeError(
                "Cloud state is enabled but PTIA_STATE_TOKEN is missing or invalid."
            )
        hydrate_cloud_state(data_dir)

    feed_url = os.environ.get("PTIA_PUBLIC_SITE_FEED_URL", "").strip()
    if feed_url:
        hydrate_public_site_feed(data_dir, feed_url)


def append_step_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the PTIA newsletter from GitHub Actions.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--scheduled-trigger",
        action="store_true",
        help="Apply the PTIA weekly automation schedule guard.",
    )
    parser.add_argument(
        "--scheduled-cron",
        default="",
        help="GitHub schedule expression that triggered the workflow.",
    )
    parser.add_argument(
        "--send-at",
        default="",
        help="Optional ISO-8601 delivery time; defaults to Friday at 09:00 Lisbon.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    args = build_parser().parse_args(argv)
    local_now = (now or datetime.now(ptia_timezone())).astimezone(ptia_timezone())
    if args.scheduled_trigger and not scheduled_window_is_open(
        local_now,
        args.scheduled_cron,
    ):
        payload = {
            "action": "skipped_inactive_lisbon_schedule",
            "now": local_now.isoformat(),
            "scheduled_cron": args.scheduled_cron,
        }
        print(json.dumps(payload) if args.json_output else f"SKIP: {payload}")
        append_step_summary(
            [
                "## PTIA newsletter",
                "",
                (
                    "Skipped inactive Lisbon schedule: "
                    f"`{args.scheduled_cron or 'missing'}` at `{local_now.isoformat()}`."
                ),
            ]
        )
        return 0

    prepare_runner_state(args.data_dir)
    send_at = resolve_send_at(args.send_at, local_now)
    preflight_result = schedule_weekly_newsletter(
        args.data_dir,
        send_at=send_at,
        dry_run=True,
    )
    feed_url = os.environ.get("PTIA_PUBLIC_SITE_FEED_URL", "").strip()
    if feed_url:
        validate_public_feed_issue(preflight_result.issue, args.data_dir, feed_url)

    client = None
    recipient_count = None
    if not args.live:
        result = preflight_result
    else:
        client = BrevoClient(BrevoConfig.from_env())
        client.validate_lists()
        client.validate_sender()
        recipient_count = client.validate_capacity()
        if recipient_count == 0:
            result = preflight_result
            payload = {
                "action": "skipped_no_recipients",
                "campaign_id": "",
                "issue_id": result.issue.issue_id,
                "item_count": len(result.issue.item_ids),
                "recipient_count": 0,
                "send_at": result.send_at.isoformat(),
                "status": result.issue.status,
            }
            print(json.dumps(payload, ensure_ascii=False) if args.json_output else payload)
            append_step_summary(
                [
                    "## PTIA newsletter",
                    "",
                    "- Action: `skipped_no_recipients`",
                    f"- Issue: `{result.issue.issue_id}`",
                    f"- Items: `{len(result.issue.item_ids)}`",
                    "- Recipients: `0`",
                    "- No Brevo campaign was created.",
                ]
            )
            return 0
        result = schedule_weekly_newsletter(
            args.data_dir,
            send_at=send_at,
            dry_run=False,
            client=client,
        )
    payload = {
        "action": result.action,
        "campaign_id": result.campaign_id,
        "issue_id": result.issue.issue_id,
        "item_count": len(result.issue.item_ids),
        "recipient_count": recipient_count,
        "send_at": result.send_at.isoformat(),
        "status": result.issue.status,
    }
    print(json.dumps(payload, ensure_ascii=False) if args.json_output else payload)
    append_step_summary(
        [
            "## PTIA newsletter",
            "",
            f"- Action: `{result.action}`",
            f"- Issue: `{result.issue.issue_id}`",
            f"- Items: `{len(result.issue.item_ids)}`",
            f"- Delivery: `{result.send_at.isoformat()}`",
            f"- Campaign: `{result.campaign_id or 'dry-run'}`",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
