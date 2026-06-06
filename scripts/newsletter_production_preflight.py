from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from ptia_engine.cloud_state import DEFAULT_STATE_API_URL  # noqa: E402
from ptia_engine.http_client import urlopen_direct  # noqa: E402


NEWSLETTER_DATASETS = {
    "content_performance.jsonl",
    "final_posts.jsonl",
    "linkedin_comments.jsonl",
    "newsletter_issues.jsonl",
    "radar_signals.jsonl",
    "trend_signals.jsonl",
}
CRITICAL_DATASETS = {"final_posts.jsonl", "radar_signals.jsonl"}
DEFAULT_DASHBOARD_URL = "https://ptia-dashboard.onrender.com"
DEFAULT_NEWSLETTER_PREFLIGHT_URL = (
    "https://europe-west1-ptia-content-engine-prod.cloudfunctions.net/newsletter_preflight"
)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def _load_environment() -> None:
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")


def _jsonl_summary(path: Path) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            digest.update(raw_line)
            if not raw_line.strip():
                continue
            try:
                json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path.name}:{line_number}: {exc}") from exc
            count += 1
    return count, digest.hexdigest()


def local_checks(data_dir: Path) -> list[Check]:
    checks: list[Check] = []
    required_files = [
        ROOT / "firebase.json",
        ROOT / ".firebaserc",
        ROOT / "firestore.rules",
        ROOT / "firebase_functions" / "main.py",
    ]
    for path in required_files:
        checks.append(Check(f"file:{path.name}", path.exists(), str(path)))

    seed_dir = ROOT / "firebase_functions" / "seed_data"
    for dataset in sorted(NEWSLETTER_DATASETS):
        source = data_dir / dataset
        try:
            count, digest = _jsonl_summary(source)
            valid = dataset not in CRITICAL_DATASETS or count > 0
            detail = f"{count} records, sha256={digest[:12]}"
        except (FileNotFoundError, ValueError) as exc:
            valid = False
            detail = str(exc)
        checks.append(Check(f"data:{dataset}", valid, detail))

        seed = seed_dir / dataset
        seed_matches = seed.exists() and source.exists() and seed.read_bytes() == source.read_bytes()
        checks.append(
            Check(
                f"seed:{dataset}",
                seed_matches,
                "matches current data" if seed_matches else "run prepare_firebase_functions.py",
            )
        )

    values = os.environ
    required_values = {
        "mailer_api": bool(values.get("MAILERLITE_API_KEY", "").strip()),
        "mailer_group": bool(
            values.get("MAILERLITE_GROUP_IDS", "").strip()
            or values.get("MAILERLITE_GROUP_ID", "").strip()
        ),
        "mailer_sender": bool(
            values.get("PTIA_NEWSLETTER_FROM_EMAIL", "").strip()
            or values.get("MAILERLITE_FROM_EMAIL", "").strip()
        ),
        "state_token": len(values.get("PTIA_STATE_TOKEN", "").strip()) >= 32,
    }
    for name, present in required_values.items():
        checks.append(Check(f"secret:{name}", present, "configured" if present else "missing"))
    return checks


def _request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urlopen_direct(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _authenticated_json(url: str, state_token: str) -> tuple[int, dict]:
    status, body = _request(
        url,
        headers={"Authorization": f"Bearer {state_token}", "Accept": "application/json"},
    )
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    return status, payload


def online_checks(
    *,
    state_api_url: str,
    newsletter_preflight_url: str,
    dashboard_url: str,
    state_token: str,
    check_render: bool = True,
) -> list[Check]:
    checks: list[Check] = []
    state_url = f"{state_api_url}?{urllib.parse.urlencode({'dataset': 'final_posts.jsonl'})}"

    status, _ = _request(state_url)
    checks.append(Check("state:unauthorized", status == 401, f"HTTP {status}"))

    status, payload = _authenticated_json(state_url, state_token)
    content = str(payload.get("content", ""))
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    state_valid = bool(content.strip()) and digest == payload.get("sha256")
    checks.append(
        Check(
            "state:authenticated",
            status == 200 and state_valid,
            f"HTTP {status}, sha256={digest[:12]}",
        )
    )

    status, _ = _request(newsletter_preflight_url)
    checks.append(Check("newsletter:unauthorized", status == 401, f"HTTP {status}"))

    status, payload = _authenticated_json(newsletter_preflight_url, state_token)
    ready = (
        status == 200
        and payload.get("status") == "ready"
        and int(payload.get("item_count", 0)) > 0
        and bool(payload.get("groups"))
    )
    checks.append(
        Check(
            "newsletter:cloud-preflight",
            ready,
            (
                f"HTTP {status}, issue={payload.get('issue_id', '')}, "
                f"items={payload.get('item_count', 0)}"
            ),
        )
    )

    if check_render:
        dashboard_health_url = dashboard_url.rstrip("/") + "/api/health"
        status, payload = _authenticated_json(dashboard_health_url, "")
        dashboard_ready = status == 200 and payload.get("cloud_state_enabled") is True
        checks.append(
            Check(
                "render:cloud-state",
                dashboard_ready,
                f"HTTP {status}, enabled={payload.get('cloud_state_enabled', False)}",
            )
        )
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate PTIA newsletter production readiness.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--state-api-url", default="")
    parser.add_argument("--newsletter-preflight-url", default=DEFAULT_NEWSLETTER_PREFLIGHT_URL)
    parser.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD_URL)
    parser.add_argument("--skip-render-check", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_environment()
    checks = local_checks(args.data_dir)
    if args.online:
        checks.extend(
            online_checks(
                state_api_url=(
                    args.state_api_url
                    or os.environ.get("PTIA_STATE_API_URL", "")
                    or DEFAULT_STATE_API_URL
                ),
                newsletter_preflight_url=args.newsletter_preflight_url,
                dashboard_url=args.dashboard_url,
                state_token=os.environ.get("PTIA_STATE_TOKEN", "").strip(),
                check_render=not args.skip_render_check,
            )
        )

    if args.json_output:
        print(json.dumps([asdict(check) for check in checks], ensure_ascii=False, indent=2))
    else:
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}")
        passed = sum(check.passed for check in checks)
        print(f"\nResult: {passed}/{len(checks)} checks passed.")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
