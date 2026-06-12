from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ptia_engine.http_client import urlopen_direct


DEFAULT_REPOSITORY = "joaoncdferreira-ai/PTIA"
DEFAULT_BRANCH = "main"
STATE_PATHS = (
    "data/knowledge_review.jsonl",
    "data/knowledge_runs.jsonl",
)


class KnowledgeRemoteError(RuntimeError):
    pass


def _repository() -> str:
    return os.getenv("PTIA_GITHUB_REPOSITORY", DEFAULT_REPOSITORY).strip()


def _branch() -> str:
    return os.getenv("PTIA_GITHUB_BRANCH", DEFAULT_BRANCH).strip()


def _github_token() -> str:
    token = (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    if token:
        return token
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creationflags,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise KnowledgeRemoteError(
            "GitHub CLI não autenticado. Executa `gh auth login` para gerir Recursos."
        ) from exc
    token = result.stdout.strip()
    if not token:
        raise KnowledgeRemoteError("GitHub CLI não devolveu uma credencial válida.")
    return token


def _request(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    authenticated: bool = False,
) -> tuple[int, dict[str, Any]]:
    url = f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ptia-content-engine",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if authenticated:
        headers["Authorization"] = f"Bearer {_github_token()}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen_direct(request, timeout=10) as response:
            raw = response.read()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404:
            return exc.code, {}
        try:
            detail = json.loads(raw).get("message", raw)
        except json.JSONDecodeError:
            detail = raw
        raise KnowledgeRemoteError(f"GitHub API {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise KnowledgeRemoteError(f"Não foi possível contactar o GitHub: {exc.reason}") from exc


def _content_path(relative_path: str) -> str:
    return f"/repos/{_repository()}/contents/{relative_path}?ref={_branch()}"


def read_remote_text(relative_path: str) -> tuple[str, str]:
    status, body = _request(_content_path(relative_path))
    if status == 404:
        return "", ""
    try:
        content = base64.b64decode(str(body["content"])).decode("utf-8")
        return content, str(body["sha"])
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise KnowledgeRemoteError(f"Resposta inválida para {relative_path}.") from exc


def write_remote_text(relative_path: str, text: str, *, message: str) -> None:
    _, sha = read_remote_text(relative_path)
    payload = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": _branch(),
    }
    if sha:
        payload["sha"] = sha
    path = f"/repos/{_repository()}/contents/{relative_path}"
    _request(path, method="PUT", payload=payload, authenticated=True)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def sync_knowledge_state(root: Path) -> dict[str, Any]:
    synced: list[str] = []
    for relative_path in STATE_PATHS:
        text, _ = read_remote_text(relative_path)
        if not text:
            continue
        _atomic_write(root / relative_path, text)
        synced.append(relative_path)
    return {
        "status": "ok",
        "repository": _repository(),
        "branch": _branch(),
        "files": synced,
    }


def publish_review_state(root: Path, text: str) -> None:
    relative_path = "data/knowledge_review.jsonl"
    write_remote_text(
        relative_path,
        text,
        message="Update PTIA knowledge review decision",
    )
    _atomic_write(root / relative_path, text)


def dispatch_knowledge_workflow() -> dict[str, Any]:
    path = f"/repos/{_repository()}/actions/workflows/weekly-knowledge.yml/dispatches"
    status, _ = _request(
        path,
        method="POST",
        payload={"ref": _branch()},
        authenticated=True,
    )
    return {
        "status": "dispatched" if status in {201, 204} else "unknown",
        "repository": _repository(),
        "branch": _branch(),
    }
