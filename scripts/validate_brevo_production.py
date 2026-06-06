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

from ptia_engine.brevo import BrevoClient, BrevoConfig  # noqa: E402
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


def validate_production(
    data_dir: Path,
    *,
    create_delete_draft: bool,
    ensure_doi_template: bool,
) -> dict:
    config = BrevoConfig.from_env()
    client = BrevoClient(config)
    account = client.get_account()
    lists = client.validate_lists()
    sender = client.validate_sender()
    recipient_count = client.validate_capacity()
    doi_template_id = config.doi_template_id
    if not doi_template_id and ensure_doi_template:
        doi_template_id = client.create_doi_template()
        config = replace(config, doi_template_id=doi_template_id)
        client = BrevoClient(config)
    doi_template = client.validate_doi_template(doi_template_id)

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
        campaign_id = ""
        if create_delete_draft:
            try:
                created = client.create_campaign(result.issue, send_at=send_at)
                campaign_id = str((created.get("data") or {}).get("id", ""))
                if not campaign_id:
                    raise RuntimeError("Brevo created a validation draft without an ID.")
            finally:
                if campaign_id:
                    client.delete_campaign(campaign_id)
        return {
            "issue_id": result.issue.issue_id,
            "list_count": len(lists),
            "recipient_count": recipient_count,
            "sender": str(sender.get("email", "")),
            "account_email": str(account.get("email", "")),
            "doi_template_id": int(doi_template.get("id", doi_template_id)),
            "send_at": send_at.isoformat(),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the PTIA newsletter compiler and Brevo production contract."
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--create-delete-draft",
        action="store_true",
        help="Create and immediately delete a Brevo draft to validate sender and HTML support.",
    )
    parser.add_argument(
        "--ensure-doi-template",
        action="store_true",
        help="Create the active PTIA double opt-in template when no ID is configured.",
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
        ensure_doi_template=args.ensure_doi_template,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(
            "Brevo validation passed: "
            f"issue={result['issue_id']}, lists={result['list_count']}, "
            f"recipients={result['recipient_count']}, sender={result['sender']}, "
            f"doi_template={result['doi_template_id']}"
        )
    if args.create_delete_draft and not args.json_output:
        print("Validation draft created and deleted successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
