from __future__ import annotations

import argparse
import json
import sys
import tempfile

from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from ptia_engine.mailerlite import MailerLiteClient, MailerLiteConfig  # noqa: E402
from ptia_engine.newsletter_delivery import (  # noqa: E402
    next_friday_send_at,
    schedule_weekly_newsletter,
)


NEWSLETTER_DATASETS = {
    "content_performance.jsonl",
    "final_posts.jsonl",
    "linkedin_comments.jsonl",
    "newsletter_issues.jsonl",
    "radar_signals.jsonl",
    "trend_signals.jsonl",
}


def validate_production(data_dir: Path, *, create_delete_draft: bool) -> dict:
    config = MailerLiteConfig.from_env()
    client = MailerLiteClient(config)
    timezone_id = config.timezone_id or client.resolve_timezone_id("Europe/Lisbon")
    if config.timezone_id != timezone_id:
        config = replace(config, timezone_id=timezone_id)
        client = MailerLiteClient(config)
    groups = client.validate_groups()

    with tempfile.TemporaryDirectory(prefix="ptia-newsletter-validation-") as temp_dir:
        validation_dir = Path(temp_dir)
        for filename in NEWSLETTER_DATASETS:
            source = data_dir / filename
            target = validation_dir / filename
            target.write_bytes(source.read_bytes() if source.exists() else b"")

        send_at = next_friday_send_at()
        result = schedule_weekly_newsletter(
            validation_dir,
            send_at=send_at,
            dry_run=True,
        )
        if not create_delete_draft:
            return {
                "issue_id": result.issue.issue_id,
                "group_count": len(groups),
                "timezone_id": timezone_id,
                "send_at": send_at.isoformat(),
            }

        campaign_id = ""
        try:
            created = client.create_campaign(result.issue, send_at=send_at)
            campaign_id = str((created.get("data") or {}).get("id", ""))
            if not campaign_id:
                raise RuntimeError("MailerLite created a validation draft without an ID.")
        finally:
            if campaign_id:
                client.delete_campaign(campaign_id)
        return {
            "issue_id": result.issue.issue_id,
            "group_count": len(groups),
            "timezone_id": timezone_id,
            "send_at": send_at.isoformat(),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the PTIA newsletter compiler and MailerLite production contract."
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--create-delete-draft",
        action="store_true",
        help="Create and immediately delete a MailerLite draft to validate sender and HTML support.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
    result = validate_production(
        args.data_dir,
        create_delete_draft=args.create_delete_draft,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(
            "MailerLite validation passed: "
            f"issue={result['issue_id']}, groups={result['group_count']}, "
            f"timezone_id={result['timezone_id']}"
        )
    if args.create_delete_draft and not args.json_output:
        print("Validation draft created and deleted successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
