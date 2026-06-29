from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ptia_engine.resources_posts import (  # noqa: E402
    build_saturday_resource_posts,
    load_resource_index,
    next_saturday,
    upsert_saturday_resource_posts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the weekly PTIA Resources LinkedIn posts for review."
    )
    parser.add_argument(
        "--index",
        default=str(ROOT / "site" / "assets" / "ptia-index" / "latest.json"),
        help="Path to the PTIA resources index JSON.",
    )
    parser.add_argument(
        "--posts",
        default=str(ROOT / "data" / "final_posts.jsonl"),
        help="Path to final_posts.jsonl.",
    )
    parser.add_argument(
        "--date",
        default="",
        help="Target Saturday date in YYYY-MM-DD. Defaults to the next Saturday in Lisbon.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned posts without writing final_posts.jsonl.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date) if args.date else next_saturday()
    index = load_resource_index(Path(args.index))

    if args.dry_run:
        posts = build_saturday_resource_posts(index, target_date=target_date)
        payload = {
            "target_date": target_date.isoformat(),
            "dry_run": True,
            "posts": [
                {
                    "slot": post.slot,
                    "title": post.title,
                    "body": post.body,
                    "image_prompt": post.image_prompt,
                    "visual_brief": post.visual_brief,
                }
                for post in posts
            ],
        }
    else:
        created = upsert_saturday_resource_posts(
            Path(args.posts),
            index,
            target_date=target_date,
        )
        payload = {
            "target_date": target_date.isoformat(),
            "dry_run": False,
            "posts": [
                {
                    "post_id": post.post_id,
                    "topic_id": post.topic_id,
                    "channel": post.channel,
                    "title": post.title,
                    "status": post.status,
                    "scheduled_time": post.scheduled_time,
                    "image_status": post.image_status,
                }
                for post in created
            ],
        }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"PTIA Saturday Resources prepared for {payload['target_date']}")
        for post in payload["posts"]:
            print(f"- {post.get('scheduled_time', post.get('slot'))}: {post['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
