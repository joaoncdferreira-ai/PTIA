from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
SCRIPT_TAG = '<script src="/analytics.js?v=20260606-1"></script>'


def main() -> int:
    updated = 0
    for path in SITE_DIR.rglob("*.html"):
        if path.name == "admin.html":
            continue
        content = path.read_text(encoding="utf-8")
        if "analytics.js" in content or "</body>" not in content:
            continue
        path.write_text(
            content.replace("</body>", f"{SCRIPT_TAG}\n</body>", 1),
            encoding="utf-8",
        )
        updated += 1
    print(f"Updated {updated} public HTML files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
