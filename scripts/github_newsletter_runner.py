from __future__ import annotations

import argparse
import json
import os
import sys

from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.brevo import BrevoClient, BrevoConfig  # noqa: E402
from ptia_engine.newsletter_delivery import (  # noqa: E402
    PTIA_TIMEZONE,
    next_friday_send_at,
    ptia_timezone,
    schedule_weekly_newsletter,
)


REQUIRED_DATASETS = {
    "content_performance.jsonl",
    "final_posts.jsonl",
    "linkedin_comments.jsonl",
    "newsletter_issues.jsonl",
    "radar_signals.jsonl",
    "trend_signals.jsonl",
}


def scheduled_window_is_open(now: datetime) -> bool:
    local = now.astimezone(ptia_timezone(PTIA_TIMEZONE))
    return local.weekday() == 4 and 8 <= local.hour <= 10


def ensure_runner_datasets(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED_DATASETS:
        path = data_dir / filename
        if not path.exists():
            path.write_text("", encoding="utf-8")


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
        help="Skip outside the Friday 08:00-10:59 Europe/Lisbon recovery window.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    args = build_parser().parse_args(argv)
    local_now = (now or datetime.now(ptia_timezone())).astimezone(ptia_timezone())
    if args.scheduled_trigger and not scheduled_window_is_open(local_now):
        payload = {
            "action": "skipped_outside_lisbon_window",
            "now": local_now.isoformat(),
        }
        print(json.dumps(payload) if args.json_output else f"SKIP: {payload}")
        append_step_summary(
            [
                "## PTIA newsletter",
                "",
                f"Skipped outside Lisbon execution window: `{local_now.isoformat()}`.",
            ]
        )
        return 0

    ensure_runner_datasets(args.data_dir)
    send_at = next_friday_send_at(local_now)
    client = None
    recipient_count = None
    if args.live:
        client = BrevoClient(BrevoConfig.from_env())
        client.validate_lists()
        client.validate_sender()
        recipient_count = client.validate_capacity()
        if recipient_count == 0:
            result = schedule_weekly_newsletter(
                args.data_dir,
                send_at=send_at,
                dry_run=True,
            )
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
        dry_run=not args.live,
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
