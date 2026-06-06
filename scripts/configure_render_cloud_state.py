from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from ptia_engine.cloud_state import DEFAULT_STATE_API_URL  # noqa: E402
from ptia_engine.http_client import urlopen_direct  # noqa: E402


RENDER_API_BASE = "https://api.render.com/v1"
TERMINAL_DEPLOY_STATES = {
    "live",
    "build_failed",
    "update_failed",
    "pre_deploy_failed",
    "canceled",
    "deactivated",
}


def _load_environment() -> None:
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")


def _render_request(
    path: str,
    *,
    api_key: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{RENDER_API_BASE}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "PTIA-Cloud-Activator/1.0",
        },
    )
    try:
        with urlopen_direct(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Render API HTTP {exc.code}: {raw[:500]}") from exc


def discover_service_id(*, api_key: str, service_name: str) -> str:
    query = urllib.parse.urlencode(
        {
            "name": service_name,
            "includePreviews": "false",
            "limit": "100",
        }
    )
    rows = _render_request(f"/services?{query}", api_key=api_key)
    matches = []
    for row in rows if isinstance(rows, list) else []:
        service = row.get("service", {}) if isinstance(row, dict) else {}
        if service.get("name") == service_name or service.get("slug") == service_name:
            matches.append(str(service.get("id", "")))
    matches = [service_id for service_id in matches if service_id]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one Render service named {service_name!r}; found {len(matches)}."
        )
    return matches[0]


def configure_render(
    *,
    api_key: str,
    service_id: str,
    state_token: str,
    state_api_url: str,
    enable: bool,
) -> None:
    variables = {
        "PTIA_STATE_TOKEN": state_token,
        "PTIA_STATE_API_URL": state_api_url,
        "PTIA_STATE_SYNC_TTL_SECONDS": "5",
        "PTIA_CLOUD_STATE_ENABLED": "true" if enable else "false",
    }
    for key, value in variables.items():
        _render_request(
            f"/services/{urllib.parse.quote(service_id)}/env-vars/{urllib.parse.quote(key)}",
            api_key=api_key,
            method="PUT",
            payload={"value": value},
        )
        print(f"Configured Render variable: {key}")


def deploy_render(*, api_key: str, service_id: str, timeout_seconds: int) -> str:
    deployment = _render_request(
        f"/services/{urllib.parse.quote(service_id)}/deploys",
        api_key=api_key,
        method="POST",
        payload={"clearCache": "do_not_clear"},
    )
    deploy_id = str(deployment.get("id", ""))
    if not deploy_id:
        raise RuntimeError("Render did not return a deploy ID.")
    print(f"Render deploy started: {deploy_id}")
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        current = _render_request(
            (
                f"/services/{urllib.parse.quote(service_id)}"
                f"/deploys/{urllib.parse.quote(deploy_id)}"
            ),
            api_key=api_key,
        )
        status = str(current.get("status", "unknown"))
        if status != last_status:
            print(f"Render deploy status: {status}")
            last_status = status
        if status in TERMINAL_DEPLOY_STATES:
            if status != "live":
                raise RuntimeError(f"Render deploy ended with status: {status}")
            return deploy_id
        time.sleep(10)
    raise TimeoutError(f"Render deploy {deploy_id} did not finish within {timeout_seconds}s.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configure PTIA cloud state on Render.")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--service-id", default="")
    parser.add_argument("--service-name", default="ptia-dashboard")
    parser.add_argument("--state-token", default="")
    parser.add_argument("--state-api-url", default=DEFAULT_STATE_API_URL)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_environment()
    api_key = args.api_key or os.environ.get("RENDER_API_KEY", "").strip()
    service_id = args.service_id or os.environ.get("RENDER_SERVICE_ID", "").strip()
    state_token = args.state_token or os.environ.get("PTIA_STATE_TOKEN", "").strip()
    missing = [
        name
        for name, value in {
            "RENDER_API_KEY": api_key,
            "PTIA_STATE_TOKEN": state_token,
        }.items()
        if not value
    ]
    if missing:
        print("Missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    if not service_id:
        service_id = discover_service_id(api_key=api_key, service_name=args.service_name)
        print(f"Discovered Render service: {service_id}")

    configure_render(
        api_key=api_key,
        service_id=service_id,
        state_token=state_token,
        state_api_url=args.state_api_url,
        enable=args.enable,
    )
    if not args.skip_deploy:
        deploy_render(
            api_key=api_key,
            service_id=service_id,
            timeout_seconds=max(args.timeout_seconds, 60),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
