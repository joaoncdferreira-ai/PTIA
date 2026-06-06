from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ptia_engine.http_client import urlopen_direct


MANAGED_STATE_FILES = frozenset(
    {
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
)
DEFAULT_STATE_API_URL = (
    "https://europe-west1-ptia-content-engine-prod.cloudfunctions.net/state_api"
)


class CloudStateError(RuntimeError):
    pass


class CloudStateConflictError(CloudStateError):
    pass


@dataclass(frozen=True, slots=True)
class CloudStateConfig:
    api_url: str
    token: str
    sync_ttl_seconds: float = 5.0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "CloudStateConfig | None":
        values = env if env is not None else os.environ
        enabled = values.get("PTIA_CLOUD_STATE_ENABLED", "").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return None
        token = values.get("PTIA_STATE_TOKEN", "").strip()
        api_url = values.get("PTIA_STATE_API_URL", "").strip()
        if not api_url:
            api_url = DEFAULT_STATE_API_URL
        if not api_url or not token:
            return None
        try:
            ttl = float(values.get("PTIA_STATE_SYNC_TTL_SECONDS", "5"))
        except ValueError:
            ttl = 5.0
        return cls(api_url=api_url.rstrip("/"), token=token, sync_ttl_seconds=max(ttl, 0.0))


@dataclass(frozen=True, slots=True)
class CloudStateDocument:
    dataset: str
    content: str
    sha256: str
    updated_at: str = ""


Transport = Callable[..., Any]


class CloudStateClient:
    def __init__(
        self,
        config: CloudStateConfig,
        *,
        transport: Transport = urlopen_direct,
        timeout: int | float = 30,
    ) -> None:
        self.config = config
        self.transport = transport
        self.timeout = timeout

    def get(self, dataset: str) -> CloudStateDocument | None:
        payload = self._request("GET", dataset=dataset)
        if payload.get("missing"):
            return None
        return CloudStateDocument(
            dataset=dataset,
            content=str(payload.get("content", "")),
            sha256=str(payload.get("sha256", "")),
            updated_at=str(payload.get("updated_at", "")),
        )

    def put(
        self,
        dataset: str,
        content: str,
        *,
        expected_sha256: str | None,
    ) -> CloudStateDocument:
        payload = self._request(
            "PUT",
            dataset=dataset,
            body={
                "content": content,
                "expected_sha256": expected_sha256,
            },
        )
        return CloudStateDocument(
            dataset=dataset,
            content=content,
            sha256=str(payload.get("sha256", "")),
            updated_at=str(payload.get("updated_at", "")),
        )

    def _request(
        self,
        method: str,
        *,
        dataset: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode({"dataset": dataset})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.config.api_url}?{query}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "PTIA-Engine/1.0",
            },
        )
        try:
            with self.transport(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code == 409:
                raise CloudStateConflictError(raw or "Cloud state version conflict") from exc
            raise CloudStateError(f"Cloud state HTTP {exc.code}: {raw[:500]}") from exc
        except urllib.error.URLError as exc:
            raise CloudStateError(f"Cloud state unavailable: {exc.reason}") from exc


class CloudStateMirror:
    def __init__(self, client: CloudStateClient) -> None:
        self.client = client
        self._lock = threading.RLock()
        self._sha_by_path: dict[Path, str | None] = {}
        self._last_sync_by_path: dict[Path, float] = {}

    def manages(self, path: Path) -> bool:
        return path.name in MANAGED_STATE_FILES

    def sync(self, path: Path, *, force: bool = False) -> None:
        path = path.resolve()
        if not self.manages(path):
            return
        with self._lock:
            last_sync = self._last_sync_by_path.get(path, 0.0)
            if not force and time.monotonic() - last_sync < self.client.config.sync_ttl_seconds:
                return
            remote = self.client.get(path.name)
            if remote is None:
                self._sha_by_path[path] = None
                self._last_sync_by_path[path] = time.monotonic()
                return
            local_content = path.read_text(encoding="utf-8") if path.exists() else ""
            if _sha256(local_content) != remote.sha256:
                _atomic_write_text(path, remote.content)
            self._sha_by_path[path] = remote.sha256
            self._last_sync_by_path[path] = time.monotonic()

    def persist(self, path: Path) -> None:
        path = path.resolve()
        if not self.manages(path):
            return
        with self._lock:
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            expected_sha = self._sha_by_path.get(path)
            try:
                remote = self.client.put(
                    path.name,
                    content,
                    expected_sha256=expected_sha,
                )
            except CloudStateConflictError as exc:
                conflict_dir = path.parent / ".cloud_conflicts"
                conflict_path = conflict_dir / f"{path.name}.{time.time_ns()}"
                _atomic_write_text(conflict_path, content)
                self.sync(path, force=True)
                raise CloudStateConflictError(
                    f"{exc}; local version preserved at {conflict_path}"
                ) from exc
            self._sha_by_path[path] = remote.sha256
            self._last_sync_by_path[path] = time.monotonic()

    def hydrate_directory(self, data_dir: Path) -> None:
        for filename in sorted(MANAGED_STATE_FILES):
            self.sync(data_dir / filename, force=True)


_MIRROR: CloudStateMirror | None | bool = False
_MIRROR_LOCK = threading.Lock()


def configured_cloud_state_mirror() -> CloudStateMirror | None:
    global _MIRROR
    if _MIRROR is not False:
        return _MIRROR
    with _MIRROR_LOCK:
        if _MIRROR is False:
            config = CloudStateConfig.from_env()
            _MIRROR = CloudStateMirror(CloudStateClient(config)) if config else None
    return _MIRROR


def reset_cloud_state_mirror() -> None:
    global _MIRROR
    with _MIRROR_LOCK:
        _MIRROR = False


def sync_cloud_state_file(path: Path, *, force: bool = False) -> None:
    mirror = configured_cloud_state_mirror()
    if mirror:
        mirror.sync(path, force=force)


def persist_cloud_state_file(path: Path) -> None:
    mirror = configured_cloud_state_mirror()
    if mirror:
        mirror.persist(path)


def hydrate_cloud_state(data_dir: Path) -> None:
    mirror = configured_cloud_state_mirror()
    if mirror:
        mirror.hydrate_directory(data_dir)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".cloud.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)
