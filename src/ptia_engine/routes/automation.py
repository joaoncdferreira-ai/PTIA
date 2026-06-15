from __future__ import annotations

from ptia_engine.editorial_automation import EditorialAutomationService


def _service(handler) -> EditorialAutomationService:
    return EditorialAutomationService(
        repo_root=handler.state.data_dir.parent,
        data_dir=handler.state.data_dir,
    )


def handle_editorial_automation(handler, payload) -> None:
    run = _service(handler).run(
        limit=max(1, min(8, int(payload.get("limit", 4) or 4))),
        scout=bool(payload.get("scout", True)),
    )
    handler._send_json({"ok": run.status != "failed", "run": run.to_record()})


def handle_replace_editorial_package(handler, payload) -> None:
    run = _service(handler).replace_topic(str(payload["topic_id"]))
    handler._send_json({"ok": run.status != "failed", "run": run.to_record()})
