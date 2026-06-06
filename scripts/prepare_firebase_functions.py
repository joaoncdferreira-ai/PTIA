from __future__ import annotations

import shutil

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_DIR = ROOT / "firebase_functions"
PACKAGE_SOURCE = ROOT / "src" / "ptia_engine"
PACKAGE_TARGET = FUNCTIONS_DIR / "ptia_engine"
SEED_DIR = FUNCTIONS_DIR / "seed_data"
STATE_FILES = {
    "content_assets.jsonl",
    "content_drafts.jsonl",
    "content_performance.jsonl",
    "editorial_topics.jsonl",
    "final_posts.jsonl",
    "linkedin_comments.jsonl",
    "newsletter_issues.jsonl",
    "processed_items.jsonl",
    "radar_signals.jsonl",
    "raw_articles.jsonl",
    "trend_signals.jsonl",
    "usage_ledger.jsonl",
}


def main() -> int:
    if PACKAGE_TARGET.exists():
        shutil.rmtree(PACKAGE_TARGET)
    shutil.copytree(
        PACKAGE_SOURCE,
        PACKAGE_TARGET,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    for filename in sorted(STATE_FILES):
        source = ROOT / "data" / filename
        (SEED_DIR / filename).write_text(
            source.read_text(encoding="utf-8") if source.exists() else "",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
