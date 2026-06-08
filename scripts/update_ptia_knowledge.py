from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ptia_engine.knowledge import KnowledgeValidationError, build_knowledge_site  # noqa: E402


def main() -> int:
    try:
        payload = build_knowledge_site(root=ROOT)
    except KnowledgeValidationError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "updated",
                "edition": payload["edition"],
                "signal_articles": payload["signal_articles"],
                "companies": len(payload["companies"]),
                "people": len(payload["people"]),
                "tools": len(payload["tools"]),
                "prompts": len(payload["prompts"]),
                "glossary": len(payload["glossary"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
