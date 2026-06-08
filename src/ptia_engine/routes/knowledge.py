from __future__ import annotations

from ptia_engine.knowledge import build_knowledge_site
from ptia_engine.knowledge_automation import (
    apply_approved_reviews,
    run_knowledge_automation,
    update_review_status,
)
from ptia_engine.routes.common import send_ok


def handle_knowledge_review(handler, payload) -> None:
    record = update_review_status(
        handler.state.data_dir.parent,
        proposal_id=str(payload["proposal_id"]),
        status=str(payload["status"]),
        notes=str(payload.get("notes") or ""),
    )
    send_ok(handler, review=record)


def handle_knowledge_run(handler, payload) -> None:
    root = handler.state.data_dir.parent
    approved = apply_approved_reviews(root)
    run = run_knowledge_automation(root)
    edition = build_knowledge_site(root=root)
    send_ok(
        handler,
        run=run,
        approved_reviews=approved,
        edition=edition["edition"],
    )
