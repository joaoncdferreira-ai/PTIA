from __future__ import annotations

import os
import sys

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from ptia_engine.brevo import BrevoClient, BrevoConfig  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        print("BREVO_API_KEY is missing.", file=sys.stderr)
        return 2
    config = BrevoConfig(
        api_key=api_key,
        list_ids=(),
        from_email="preflight@ptia.invalid",
    )
    client = BrevoClient(config)
    lists = client.list_lists()
    senders = client.list_senders()
    print("Brevo lists:")
    for item in lists:
        print(f"{item.get('id', '')}\t{item.get('name', '')}")
    print("\nBrevo senders:")
    for sender in senders:
        print(
            f"{sender.get('email', '')}\t{sender.get('name', '')}\t"
            f"active={sender.get('active') is True}"
        )
    return 0 if lists and senders else 3


if __name__ == "__main__":
    raise SystemExit(main())
