from __future__ import annotations


def to_dict(record):
    if hasattr(record, "to_record"):
        return record.to_record()
    return record


def send_ok(handler, **payload) -> None:
    handler._send_json({"ok": True, **payload})
