from __future__ import annotations

import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.buffer_api import BufferClient  # noqa: E402
from ptia_engine.dashboard import (  # noqa: E402
    PTIA_INSTAGRAM_OVERLAY_VERSION,
    _copy_quality_issues,
    _final_post_text,
    _public_image_url_for_buffer,
)
from ptia_engine.storage import load_final_posts  # noqa: E402
from ptia_engine.performance_import import import_instagram_insights  # noqa: E402


mcp = FastMCP("ptia-ops")


def _load_local_env() -> None:
    for filename in (".env", ".env.local"):
        path = ROOT / filename
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _posts():
    return load_final_posts(ROOT / "data" / "final_posts.jsonl")


def _post_summary(post) -> dict[str, Any]:
    image_url = _public_image_url_for_buffer(post) or ""
    return {
        "post_id": post.post_id,
        "topic_id": post.topic_id,
        "channel": post.channel,
        "title": post.title,
        "status": post.status,
        "scheduled_time": post.scheduled_time,
        "buffer_post_id": post.buffer_post_id,
        "copy_issues": _copy_quality_issues(post),
        "image_url": image_url,
        "instagram_current_overlay": (
            post.channel != "instagram"
            or f"_{PTIA_INSTAGRAM_OVERLAY_VERSION}_" in image_url
        ),
        "text_preview": _final_post_text(post)[:280],
    }


def _normalise_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in (value or "").strip().splitlines()).strip()


def _local_due_as_buffer_utc(value: str) -> str:
    from ptia_engine.buffer_api import _buffer_due_at

    return _buffer_due_at(value)


@mcp.tool()
def validate_schedule(date: str, future_only: bool = True) -> dict[str, Any]:
    """Validate scheduled PTIA posts for a given YYYY-MM-DD date."""
    now = datetime.now().astimezone()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for post in _posts():
        scheduled = post.scheduled_time or ""
        if post.status != "scheduled" or not scheduled.startswith(date):
            continue
        try:
            scheduled_dt = datetime.fromisoformat(scheduled)
        except ValueError:
            scheduled_dt = None
        if future_only and scheduled_dt and scheduled_dt <= now:
            continue

        summary = _post_summary(post)
        issues = list(summary["copy_issues"])
        if post.channel == "instagram" and not summary["instagram_current_overlay"]:
            issues.append("instagram image is not current overlay version")
        summary["issues"] = issues
        rows.append(summary)
        if issues:
            failures.append(summary)

    return {
        "ok": not failures,
        "date": date,
        "future_only": future_only,
        "count": len(rows),
        "failures": failures,
        "posts": rows,
    }


@mcp.tool()
def list_scheduled_posts(date: str, future_only: bool = False) -> list[dict[str, Any]]:
    """List scheduled PTIA posts for a given YYYY-MM-DD date."""
    now = datetime.now().astimezone()
    rows = []
    for post in _posts():
        scheduled = post.scheduled_time or ""
        if post.status != "scheduled" or not scheduled.startswith(date):
            continue
        try:
            scheduled_dt = datetime.fromisoformat(scheduled)
        except ValueError:
            scheduled_dt = None
        if future_only and scheduled_dt and scheduled_dt <= now:
            continue
        rows.append(_post_summary(post))
    return sorted(rows, key=lambda item: (item["scheduled_time"], item["channel"]))


@mcp.tool()
def get_final_post(post_id: str) -> dict[str, Any]:
    """Return a final post with full text and validation issues."""
    for post in _posts():
        if post.post_id == post_id:
            summary = _post_summary(post)
            summary["text"] = _final_post_text(post)
            summary["source_urls"] = post.source_urls
            return summary
    raise ValueError(f"Final post not found: {post_id}")


@mcp.tool()
def get_buffer_post(buffer_post_id: str) -> dict[str, Any]:
    """Read the real current state of one Buffer post."""
    _load_local_env()
    post = BufferClient().get_post(buffer_post_id)
    return {
        "id": post.id,
        "status": post.status,
        "due_at": post.due_at,
        "channel_id": post.channel_id,
        "channel_service": post.channel_service,
        "external_link": post.external_link,
        "asset_sources": post.asset_sources or [],
        "text": post.text,
        "text_preview": post.text[:280],
    }


@mcp.tool()
def compare_local_post_to_buffer(post_id: str) -> dict[str, Any]:
    """Compare one local final post with the real Buffer post."""
    _load_local_env()
    for local in _posts():
        if local.post_id != post_id:
            continue
        if not local.buffer_post_id:
            raise ValueError(f"Local post has no buffer_post_id: {post_id}")
        remote = BufferClient().get_post(local.buffer_post_id)
        local_text = _normalise_text(_final_post_text(local))
        remote_text = _normalise_text(remote.text)
        local_due = _local_due_as_buffer_utc(local.scheduled_time)
        local_image = _public_image_url_for_buffer(local) or ""
        remote_assets = remote.asset_sources or []
        checks = {
            "text_matches": local_text == remote_text,
            "due_at_matches": local_due == remote.due_at,
            "image_present": bool(remote_assets),
            "image_matches": not local_image or local_image in remote_assets,
            "copy_valid": not _copy_quality_issues(local),
        }
        return {
            "ok": all(checks.values()),
            "checks": checks,
            "local": {
                "post_id": local.post_id,
                "channel": local.channel,
                "scheduled_time": local.scheduled_time,
                "buffer_due_at_expected": local_due,
                "image_url": local_image,
                "copy_issues": _copy_quality_issues(local),
                "text_preview": local_text[:280],
            },
            "buffer": {
                "buffer_post_id": remote.id,
                "status": remote.status,
                "due_at": remote.due_at,
                "channel_service": remote.channel_service,
                "asset_sources": remote_assets,
                "text_preview": remote_text[:280],
            },
        }
    raise ValueError(f"Final post not found: {post_id}")


@mcp.tool()
def audit_buffer_against_local(date: str, future_only: bool = True) -> dict[str, Any]:
    """Compare all local scheduled posts for a date against real Buffer state."""
    _load_local_env()
    now = datetime.now().astimezone()
    rows = []
    failures = []
    for post in _posts():
        scheduled = post.scheduled_time or ""
        if post.status != "scheduled" or not scheduled.startswith(date) or not post.buffer_post_id:
            continue
        try:
            scheduled_dt = datetime.fromisoformat(scheduled)
        except ValueError:
            scheduled_dt = None
        if future_only and scheduled_dt and scheduled_dt <= now:
            continue
        try:
            comparison = compare_local_post_to_buffer(post.post_id)
        except Exception as exc:
            comparison = {
                "ok": False,
                "local": {"post_id": post.post_id, "channel": post.channel},
                "error": str(exc),
            }
        rows.append(comparison)
        if not comparison.get("ok"):
            failures.append(comparison)
    return {
        "ok": not failures,
        "date": date,
        "future_only": future_only,
        "count": len(rows),
        "failures": failures,
        "posts": rows,
    }


@mcp.tool()
def update_buffer_post_from_local(post_id: str) -> dict[str, Any]:
    """Update one Buffer scheduled post from the validated local final post."""
    _load_local_env()
    for post in _posts():
        if post.post_id != post_id:
            continue
        issues = _copy_quality_issues(post)
        if issues:
            raise ValueError(f"Copy validation failed: {issues}")
        if not post.buffer_post_id:
            raise ValueError(f"Post has no buffer_post_id: {post_id}")
        result = BufferClient().edit_scheduled_post(
            post_id=post.buffer_post_id,
            text=_final_post_text(post),
            due_at=post.scheduled_time,
            image_url=_public_image_url_for_buffer(post) or "",
        )
        return {
            "ok": True,
            "post_id": post.post_id,
            "buffer_post_id": result.id,
            "due_at": result.due_at,
            "text_preview": result.text[:280],
        }
    raise ValueError(f"Final post not found: {post_id}")


@mcp.tool()
def validate_site_feed_no_future(now_iso: str | None = None) -> dict[str, Any]:
    """Check whether future feed posts are either absent or gated by the client."""
    import json

    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now().astimezone()
    feed_path = ROOT / "site" / "site-feed.json"
    data = json.loads(feed_path.read_text(encoding="utf-8"))
    items = data.get("items") or data.get("posts") or []
    future_items = []
    for item in items:
        raw = str(item.get("published_at") or item.get("scheduled_time") or "")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if dt > now:
            future_items.append(
                {
                    "title": item.get("title", ""),
                    "published_at": raw,
                    "url": item.get("url", ""),
                }
            )
    app_js = (ROOT / "site" / "app.js").read_text(encoding="utf-8", errors="ignore")
    article_js = (ROOT / "site" / "article.js").read_text(encoding="utf-8", errors="ignore")
    client_filter_present = (
        "function isPublishedNow" in app_js
        and "visibleFeedPosts" in app_js
        and "isPublishedNow(item.published_at)" in article_js
    )
    return {
        "ok": not future_items or client_filter_present,
        "public_feed_contains_future": bool(future_items),
        "client_filter_present": client_filter_present,
        "future_items": future_items,
        "checked_at": now.isoformat(),
    }


@mcp.tool()
def check_public_site_status() -> dict[str, Any]:
    """Check public PTIA site HTTP status for apex and www."""
    results = []
    for url in ("https://ptia.pt", "https://www.ptia.pt"):
        try:
            request = Request(url, headers={"User-Agent": "PTIA-Ops/1.0"})
            with urlopen(request, timeout=15) as response:
                results.append({"url": url, "ok": 200 <= response.status < 400, "status": response.status})
        except Exception as exc:
            results.append({"url": url, "ok": False, "error": str(exc)})
    return {"ok": all(item["ok"] for item in results), "results": results}


def _nslookup(record_type: str, name: str) -> str:
    completed = subprocess.run(
        ["nslookup", f"-type={record_type}", name],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    return (completed.stdout + completed.stderr).strip()


@mcp.tool()
def check_ptia_dns_basics() -> dict[str, Any]:
    """Check basic PTIA DNS and MailerLite authentication records."""
    checks = {
        "apex_a": _nslookup("A", "ptia.pt"),
        "www_cname": _nslookup("CNAME", "www.ptia.pt"),
        "spf": _nslookup("TXT", "ptia.pt"),
        "dkim": _nslookup("CNAME", "litesrv._domainkey.ptia.pt"),
        "dmarc": _nslookup("TXT", "_dmarc.ptia.pt"),
    }
    expected = {
        "apex_a": "216.198.79.1",
        "www_cname": "2942f61d90c25503.vercel-dns-017.com",
        "spf": "include:_spf.mlsend.com",
        "dkim": "litesrv._domainkey.mlsend.com",
        "dmarc": "v=DMARC1",
    }
    status = {
        key: expected_value.lower() in checks[key].lower()
        for key, expected_value in expected.items()
    }
    return {"ok": all(status.values()), "status": status, "raw": checks}


@mcp.tool()
def resolve_ptia_hosts() -> dict[str, Any]:
    """Resolve ptia.pt and www.ptia.pt using the local resolver."""
    results = {}
    for host in ("ptia.pt", "www.ptia.pt"):
        try:
            results[host] = sorted({item[4][0] for item in socket.getaddrinfo(host, 443)})
        except Exception as exc:
            results[host] = {"error": str(exc)}
    return {"ok": all(isinstance(value, list) and value for value in results.values()), "results": results}


@mcp.tool()
def import_instagram_performance(limit: int = 25) -> dict[str, Any]:
    """Import Instagram metrics from Meta Graph API into content_performance.jsonl."""
    _load_local_env()
    records = import_instagram_insights(
        final_posts_path=ROOT / "data" / "final_posts.jsonl",
        performance_path=ROOT / "data" / "content_performance.jsonl",
        limit=limit,
    )
    return {
        "ok": True,
        "records": len(records),
        "performance_path": str(ROOT / "data" / "content_performance.jsonl"),
        "previews": [
            {
                "performance_id": record.performance_id,
                "post_id": record.post_id,
                "impressions": record.impressions,
                "likes": record.likes,
                "comments": record.comments,
                "saves": record.saves,
                "shares": record.shares,
            }
            for record in records[:10]
        ],
    }


if __name__ == "__main__":
    mcp.run()
