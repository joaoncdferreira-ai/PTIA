from __future__ import annotations

import os
import sys

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from ptia_engine.mailerlite import MailerLiteClient, MailerLiteConfig  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("MAILERLITE_API_KEY", "").strip()
    if not api_key:
        print("MAILERLITE_API_KEY is missing.", file=sys.stderr)
        return 2
    config = MailerLiteConfig(
        api_key=api_key,
        group_ids=(),
        from_email="preflight@ptia.invalid",
    )
    groups = MailerLiteClient(config).list_groups()
    for group in groups:
        print(
            f"{group.get('id', '')}\t{group.get('name', '')}\t"
            f"active={group.get('active_count', 0)}"
        )
    return 0 if groups else 3


if __name__ == "__main__":
    raise SystemExit(main())
