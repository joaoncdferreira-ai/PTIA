from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.dashboard import (  # noqa: E402
    PTIA_INSTAGRAM_OVERLAY_VERSION,
    _copy_quality_issues,
    _public_image_url_for_buffer,
)
from ptia_engine.storage import load_final_posts  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate PTIA scheduled posts for a day.")
    parser.add_argument("--date", required=True, help="Date to validate, YYYY-MM-DD.")
    parser.add_argument(
        "--future-only",
        action="store_true",
        help="Only validate posts after the current local time.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    day = args.date.strip()
    now = datetime.now().astimezone()
    posts = load_final_posts(ROOT / "data" / "final_posts.jsonl")
    rows = []
    failures = []

    for post in posts:
        scheduled = post.scheduled_time or ""
        if post.status != "scheduled" or not scheduled.startswith(day):
            continue
        try:
            scheduled_dt = datetime.fromisoformat(scheduled)
        except ValueError:
            scheduled_dt = None
        if args.future_only and scheduled_dt and scheduled_dt <= now:
            continue

        issues = _copy_quality_issues(post)
        image_url = _public_image_url_for_buffer(post) or ""
        expected_overlay = post.channel == "instagram"
        has_current_overlay = f"_{PTIA_INSTAGRAM_OVERLAY_VERSION}_" in image_url
        image_issue = (
            ["instagram image is not current overlay version"]
            if expected_overlay and not has_current_overlay
            else []
        )
        all_issues = issues + image_issue
        rows.append(
            (
                scheduled[11:16],
                post.channel,
                post.post_id,
                post.title,
                all_issues,
                image_url,
            )
        )
        if all_issues:
            failures.append((scheduled, post.channel, post.post_id, all_issues))

    print(f"validated_date={day}")
    print(f"post_count={len(rows)}")
    for time, channel, post_id, title, issues, image_url in sorted(rows):
        print(f"{time} | {channel} | {post_id}")
        print(f"  title={title}")
        print(f"  issues={issues or 'OK'}")
        if channel == "instagram":
            print(f"  image={Path(image_url).name if image_url else ''}")

    if failures:
        print("FAILURES")
        for failure in failures:
            print(failure)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
