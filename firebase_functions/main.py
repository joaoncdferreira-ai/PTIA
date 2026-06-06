from __future__ import annotations

import hmac
import hashlib
import json
import os
import re
import tempfile

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import firestore
from firebase_functions import https_fn, logger, scheduler_fn

from ptia_engine.cloud_state import MANAGED_STATE_FILES
from ptia_engine.brevo import BrevoClient, BrevoConfig
from ptia_engine.newsletter_delivery import next_friday_send_at, schedule_weekly_newsletter
from ptia_engine.state_documents import (
    content_sha256,
    decode_content_chunks,
    encode_content_chunks,
)


firebase_admin.initialize_app()
REGION = "europe-west1"
SEED_DIR = Path(__file__).resolve().parent / "seed_data"


def _db():
    return firestore.client()


def _json_response(
    payload: dict[str, Any],
    status: int = 200,
    *,
    headers: dict[str, str] | None = None,
) -> https_fn.Response:
    response_headers = {"Content-Type": "application/json; charset=utf-8"}
    response_headers.update(headers or {})
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        headers=response_headers,
    )


def _secret_json(name: str) -> dict[str, str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        raise RuntimeError(f"Missing required secret: {name}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in secret: {name}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Secret {name} must contain a JSON object.")
    return {str(key): str(value) for key, value in payload.items()}


def _dataset_name(value: str) -> str:
    dataset = Path(value).name
    if dataset != value or dataset not in MANAGED_STATE_FILES:
        raise ValueError("Unsupported state dataset.")
    return dataset


def _authorized(request: https_fn.Request) -> bool:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    token = header.removeprefix("Bearer ").strip()
    expected = os.environ.get("PTIA_STATE_TOKEN", "").strip()
    return bool(token and expected) and hmac.compare_digest(token, expected)


def _metadata_ref(dataset: str):
    return _db().collection("state_files").document(dataset)


def _read_dataset(dataset: str) -> dict[str, Any] | None:
    snapshot = _metadata_ref(dataset).get()
    if not snapshot.exists:
        return None
    metadata = snapshot.to_dict() or {}
    chunks = []
    chunks_ref = _metadata_ref(dataset).collection("chunks")
    for index in range(int(metadata.get("chunk_count", 0))):
        chunk_snapshot = chunks_ref.document(f"{index:05d}").get()
        if not chunk_snapshot.exists:
            raise RuntimeError(f"Missing chunk {index} for {dataset}.")
        chunks.append(str((chunk_snapshot.to_dict() or {}).get("data", "")))
    content = decode_content_chunks(chunks)
    expected_sha = str(metadata.get("sha256", ""))
    if content_sha256(content) != expected_sha:
        raise RuntimeError(f"Checksum mismatch for {dataset}.")
    return {
        "dataset": dataset,
        "content": content,
        "sha256": expected_sha,
        "updated_at": str(metadata.get("updated_at", "")),
    }


def _write_dataset(
    dataset: str,
    content: str,
    *,
    expected_sha256: str | None,
) -> dict[str, Any]:
    chunks = encode_content_chunks(content)
    new_sha = content_sha256(content)
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata_ref = _metadata_ref(dataset)
    transaction = _db().transaction()

    @firestore.transactional
    def update_state(txn):
        snapshot = metadata_ref.get(transaction=txn)
        current = snapshot.to_dict() if snapshot.exists else {}
        current_sha = str(current.get("sha256", "")) if snapshot.exists else None
        if current_sha != expected_sha256:
            raise ValueError("VERSION_CONFLICT")
        old_count = int(current.get("chunk_count", 0))
        txn.set(
            metadata_ref,
            {
                "dataset": dataset,
                "sha256": new_sha,
                "size_bytes": len(content.encode("utf-8")),
                "chunk_count": len(chunks),
                "updated_at": updated_at,
            },
        )
        chunks_ref = metadata_ref.collection("chunks")
        for index, chunk in enumerate(chunks):
            txn.set(chunks_ref.document(f"{index:05d}"), {"data": chunk})
        for index in range(len(chunks), old_count):
            txn.delete(chunks_ref.document(f"{index:05d}"))

    update_state(transaction)
    return {"dataset": dataset, "sha256": new_sha, "updated_at": updated_at}


def _ensure_seeded() -> None:
    marker_ref = _db().collection("system").document("initial_state_v1")
    if marker_ref.get().exists:
        return
    seeded = []
    for dataset in sorted(MANAGED_STATE_FILES):
        path = SEED_DIR / dataset
        if not path.exists() or _metadata_ref(dataset).get().exists:
            continue
        try:
            _write_dataset(
                dataset,
                path.read_text(encoding="utf-8"),
                expected_sha256=None,
            )
            seeded.append(dataset)
        except ValueError as exc:
            if str(exc) != "VERSION_CONFLICT":
                raise
    marker_ref.set(
        {
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "datasets": seeded,
        }
    )
    logger.info("Initial PTIA state seeded.", datasets=seeded)


@https_fn.on_request(region=REGION, timeout_sec=60, secrets=["PTIA_STATE_TOKEN"])
def state_api(request: https_fn.Request) -> https_fn.Response:
    if not _authorized(request):
        return _json_response({"error": "Unauthorized"}, 401)
    try:
        _ensure_seeded()
        dataset = _dataset_name(str(request.args.get("dataset", "")))
        if request.method == "GET":
            document = _read_dataset(dataset)
            return _json_response(document or {"dataset": dataset, "missing": True})
        if request.method != "PUT":
            return _json_response({"error": "Method not allowed"}, 405)
        payload = request.get_json(silent=True) or {}
        content = payload.get("content")
        if not isinstance(content, str):
            return _json_response({"error": "content must be a string"}, 400)
        result = _write_dataset(
            dataset,
            content,
            expected_sha256=payload.get("expected_sha256"),
        )
        return _json_response(result)
    except ValueError as exc:
        if str(exc) == "VERSION_CONFLICT":
            return _json_response({"error": "Version conflict"}, 409)
        return _json_response({"error": str(exc)}, 400)
    except Exception as exc:
        logger.error("State API failure.", error=str(exc))
        return _json_response({"error": "Internal state service error"}, 500)


def _materialize_state(data_dir: Path, datasets: set[str]) -> None:
    _ensure_seeded()
    data_dir.mkdir(parents=True, exist_ok=True)
    for dataset in datasets:
        document = _read_dataset(dataset)
        (data_dir / dataset).write_text(
            str(document.get("content", "")) if document else "",
            encoding="utf-8",
        )


def _persist_local_dataset(data_dir: Path, dataset: str) -> None:
    path = data_dir / dataset
    current = _read_dataset(dataset)
    _write_dataset(
        dataset,
        path.read_text(encoding="utf-8") if path.exists() else "",
        expected_sha256=str(current.get("sha256", "")) if current else None,
    )


def _record_automation_run(job: str, status: str, **details: Any) -> None:
    _db().collection("automation_runs").add(
        {
            "job": job,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **details,
        }
    )


NEWSLETTER_DATASETS = {
    "content_performance.jsonl",
    "final_posts.jsonl",
    "linkedin_comments.jsonl",
    "newsletter_issues.jsonl",
    "radar_signals.jsonl",
    "trend_signals.jsonl",
}


def _newsletter_secret_values() -> dict[str, str]:
    return _secret_json("PTIA_BREVO_CONFIG")


def _newsletter_client(values: dict[str, str] | None = None) -> BrevoClient:
    return BrevoClient(BrevoConfig.from_env(values or _newsletter_secret_values()))


ALLOWED_SUBSCRIBE_ORIGINS = {"https://ptia.pt", "https://www.ptia.pt"}
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}$")


def _subscribe_cors_headers(request: https_fn.Request) -> dict[str, str]:
    origin = request.headers.get("Origin", "")
    if origin not in ALLOWED_SUBSCRIBE_ORIGINS:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


def _signup_limit_key(kind: str, value: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{kind}:{value}".encode("utf-8")).hexdigest()
    return f"{kind}_{digest}"


def _consume_signup_limit(key: str, *, limit: int, window_seconds: int) -> bool:
    reference = _db().collection("newsletter_signup_limits").document(key)
    now = int(datetime.now(timezone.utc).timestamp())
    transaction = _db().transaction()

    @firestore.transactional
    def consume(txn):
        snapshot = reference.get(transaction=txn)
        record = snapshot.to_dict() if snapshot.exists else {}
        window_started = int(record.get("window_started", 0))
        count = int(record.get("count", 0))
        if now - window_started >= window_seconds:
            window_started = now
            count = 0
        if count >= limit:
            return False
        txn.set(
            reference,
            {
                "window_started": window_started,
                "count": count + 1,
                "expires_at": datetime.fromtimestamp(
                    window_started + window_seconds,
                    tz=timezone.utc,
                ),
            },
        )
        return True

    return bool(consume(transaction))


@https_fn.on_request(
    region=REGION,
    timeout_sec=60,
    secrets=["PTIA_BREVO_CONFIG"],
)
def newsletter_subscribe(request: https_fn.Request) -> https_fn.Response:
    headers = _subscribe_cors_headers(request)
    if request.method == "OPTIONS":
        return _json_response({}, 204, headers=headers)
    if request.method != "POST":
        return _json_response({"error": "Method not allowed"}, 405, headers=headers)
    if request.headers.get("Origin", "") not in ALLOWED_SUBSCRIBE_ORIGINS:
        return _json_response({"error": "Origin not allowed"}, 403, headers=headers)

    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().casefold()
    first_name = str(payload.get("name", "")).strip()[:100]
    honeypot = str(payload.get("company", "")).strip()
    if honeypot:
        return _json_response({"status": "accepted"}, 202, headers=headers)
    if len(email) > 320 or not EMAIL_PATTERN.fullmatch(email):
        return _json_response({"error": "Invalid email"}, 400, headers=headers)

    try:
        values = _newsletter_secret_values()
        salt = values.get("PTIA_SUBSCRIBE_SALT", "").strip()
        if len(salt) < 32:
            raise RuntimeError("Subscription rate-limit salt is not configured.")
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        source_ip = forwarded_for.split(",", 1)[0].strip() or str(request.remote_addr or "")
        ip_allowed = _consume_signup_limit(
            _signup_limit_key("ip", source_ip, salt),
            limit=5,
            window_seconds=3600,
        )
        email_allowed = _consume_signup_limit(
            _signup_limit_key("email", email, salt),
            limit=3,
            window_seconds=86400,
        )
        if not ip_allowed or not email_allowed:
            return _json_response({"error": "Too many requests"}, 429, headers=headers)
        _newsletter_client(values).create_doi_contact(email, first_name=first_name)
    except Exception as exc:
        logger.error("Newsletter subscription failed.", error=type(exc).__name__)
        return _json_response({"error": "Subscription unavailable"}, 503, headers=headers)
    return _json_response({"status": "confirmation_sent"}, 201, headers=headers)


def _newsletter_preflight_result(data_dir: Path) -> dict[str, Any]:
    client = _newsletter_client()
    lists = client.validate_lists()
    sender = client.validate_sender()
    recipient_count = client.validate_capacity()
    doi_template = client.validate_doi_template()
    account = client.get_account()
    send_at = next_friday_send_at()
    result = schedule_weekly_newsletter(
        data_dir,
        send_at=send_at,
        dry_run=True,
    )
    return {
        "status": "ready",
        "issue_id": result.issue.issue_id,
        "item_count": len(result.issue.item_ids),
        "send_at": send_at.isoformat(),
        "provider": "brevo",
        "recipient_count": recipient_count,
        "account_email": str(account.get("email", "")),
        "sender": {
            "id": str(sender.get("id", "")),
            "email": str(sender.get("email", "")),
            "active": sender.get("active") is True,
        },
        "doi_template_id": int(doi_template.get("id", 0)),
        "lists": [
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
            }
            for item in lists
        ],
    }


@https_fn.on_request(
    region=REGION,
    timeout_sec=120,
    secrets=["PTIA_STATE_TOKEN", "PTIA_BREVO_CONFIG"],
)
def newsletter_preflight(request: https_fn.Request) -> https_fn.Response:
    if not _authorized(request):
        return _json_response({"error": "Unauthorized"}, 401)
    if request.method != "GET":
        return _json_response({"error": "Method not allowed"}, 405)
    try:
        with tempfile.TemporaryDirectory(prefix="ptia-newsletter-preflight-") as temp_dir:
            data_dir = Path(temp_dir)
            _materialize_state(data_dir, NEWSLETTER_DATASETS)
            return _json_response(_newsletter_preflight_result(data_dir))
    except Exception as exc:
        logger.error("Newsletter preflight failed.", error=str(exc))
        return _json_response({"error": str(exc)[:1000]}, 500)


@scheduler_fn.on_schedule(
    schedule="45 8 * * 5",
    timezone="Europe/Lisbon",
    region=REGION,
    timeout_sec=300,
    retry_count=3,
    min_backoff_seconds=60,
    max_backoff_seconds=600,
    secrets=["PTIA_BREVO_CONFIG"],
)
def schedule_weekly_newsletter_cloud(event: scheduler_fn.ScheduledEvent) -> None:
    with tempfile.TemporaryDirectory(prefix="ptia-newsletter-") as temp_dir:
        data_dir = Path(temp_dir)
        _materialize_state(data_dir, NEWSLETTER_DATASETS)
        try:
            client = _newsletter_client()
            client.validate_lists()
            client.validate_sender()
            client.validate_capacity()
            result = schedule_weekly_newsletter(
                data_dir,
                send_at=next_friday_send_at(),
                client=client,
            )
        except Exception as exc:
            _persist_local_dataset(data_dir, "newsletter_issues.jsonl")
            _record_automation_run(
                "weekly_newsletter",
                "failed",
                error=str(exc)[:1000],
            )
            logger.error("PTIA newsletter cloud scheduler failed.", error=str(exc))
            raise
        _persist_local_dataset(data_dir, "newsletter_issues.jsonl")
        _record_automation_run(
            "weekly_newsletter",
            "completed",
            action=result.action,
            issue_id=result.issue.issue_id,
            campaign_id=result.campaign_id,
        )
        logger.info(
            "PTIA newsletter cloud scheduler completed.",
            action=result.action,
            issue_id=result.issue.issue_id,
            campaign_id=result.campaign_id,
        )
