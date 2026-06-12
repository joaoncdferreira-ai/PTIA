from __future__ import annotations

from ptia_engine.knowledge_automation import (
    update_review_status_remote,
)
from ptia_engine.knowledge_remote import dispatch_knowledge_workflow, sync_knowledge_state
from ptia_engine.routes.common import send_ok


def handle_knowledge_review(handler, payload) -> None:
    record = update_review_status_remote(
        handler.state.data_dir.parent,
        proposal_id=str(payload["proposal_id"]),
        status=str(payload["status"]),
        notes=str(payload.get("notes") or ""),
    )
    send_ok(handler, review=record)


def handle_knowledge_run(handler, payload) -> None:
    send_ok(handler, run=dispatch_knowledge_workflow())


def handle_knowledge_sync(handler, payload) -> None:
    send_ok(handler, sync=sync_knowledge_state(handler.state.data_dir.parent))
