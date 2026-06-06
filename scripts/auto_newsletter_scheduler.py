from __future__ import annotations

import argparse
import sys

from datetime import datetime, time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from ptia_engine.brevo import BrevoAPIError, BrevoConfigError  # noqa: E402
from ptia_engine.newsletter_delivery import (  # noqa: E402
    PTIA_TIMEZONE,
    next_friday_send_at,
    ptia_timezone,
    schedule_weekly_newsletter,
)


def _load_env() -> None:
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")


def _target_send_at(value: str, *, hour: int, minute: int) -> datetime:
    tz = ptia_timezone(PTIA_TIMEZONE)
    raw = value.strip()
    if not raw:
        return next_friday_send_at(hour=hour, minute=minute)
    if "T" in raw:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(tz)
    parsed_date = datetime.fromisoformat(raw).date()
    return datetime.combine(parsed_date, time(hour, minute), tzinfo=tz)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and schedule the PTIA Weekly newsletter.")
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--target-date", default="", help="YYYY-MM-DD; defaults to the next Friday.")
    parser.add_argument("--hour", type=int, default=9)
    parser.add_argument("--minute", type=int, default=0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--force", action="store_true", help="Generate a fresh issue even if one exists.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Create and schedule the Brevo campaign. Without this flag, only local compilation runs.",
    )
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    return parser


def trigger_alert(title: str, message: str, *, dry_run: bool = False) -> None:
    import subprocess

    print(f"ALERT [{title}]: {message}")
    if dry_run:
        print("(Alert suppressed in dry-run mode)")
        return
    if sys.platform == "win32":
        toast_script = ROOT / "scripts" / "trigger_toast.ps1"
        if toast_script.exists():
            try:
                completed = subprocess.run(
                    [
                        "powershell.exe",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(toast_script),
                        "-Title",
                        title,
                        "-Message",
                        message,
                        "-SkipEmail",
                    ],
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0:
                    print(f"Warning: Windows toast failed: {completed.stderr.strip()}")
            except Exception as exc:
                print(f"Warning: Failed to run trigger_toast.ps1: {exc}")

    email_script = ROOT / "scripts" / "send_email_alert.py"
    if email_script.exists():
        try:
            completed = subprocess.run(
                [sys.executable, str(email_script), title, message],
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                details = completed.stdout.strip() or completed.stderr.strip()
                print(f"Warning: Email alert failed: {details}")
        except Exception as exc:
            print(f"Warning: Failed to run send_email_alert.py: {exc}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_env()
    live = args.live and not args.dry_run

    send_at = _target_send_at(args.target_date, hour=args.hour, minute=args.minute)
    print("=== PTIA Weekly Newsletter Scheduler ===")
    print(f"Target send time: {send_at.isoformat()}")
    print(f"Mode: {'Brevo schedule' if live else 'local compilation'}")

    # Detect recovery delivery if running on Friday after 9:00 with default target
    if not args.target_date:
        tz = ptia_timezone(PTIA_TIMEZONE)
        now_tz = datetime.now(tz)
        is_friday = now_tz.weekday() == 4
        limit_time = now_tz.replace(hour=9, minute=0, second=0, microsecond=0)
        if is_friday and now_tz > limit_time and send_at.date() == now_tz.date():
            msg = f"A newsletter semanal estava atrasada e foi reagendada para envio hoje às {send_at.strftime('%H:%M')}."
            trigger_alert("PTIA Newsletter Recovery", msg, dry_run=not live)

    try:
        result = schedule_weekly_newsletter(
            Path(args.data_dir),
            send_at=send_at,
            limit=args.limit,
            force=args.force,
            dry_run=not live,
        )
    except BrevoConfigError as exc:
        details = []
        if exc.missing:
            details.append("faltam: " + ", ".join(exc.missing))
        if exc.invalid:
            details.append("inválidos: " + ", ".join(exc.invalid))
        msg = "Configuração Brevo incompleta ou inválida. " + "; ".join(details)
        print(f"ERRO: {msg}")
        trigger_alert("PTIA Newsletter Failure", msg, dry_run=not live)
        return 2
    except BrevoAPIError as exc:
        msg = f"Erro API Brevo ({exc.status_code}): {exc.body[:200]}"
        print(f"ERRO: {msg}")
        trigger_alert("PTIA Newsletter Failure", msg, dry_run=not live)
        return 3
    except Exception as exc:
        msg = f"Erro inesperado: {exc}"
        print(f"ERRO: {msg}")
        trigger_alert("PTIA Newsletter Failure", msg, dry_run=not live)
        return 1

    print(f"Action: {result.action}")
    print(f"Issue: {result.issue.issue_id}")
    print(f"Status: {result.issue.status}")
    if result.campaign_id:
        print(f"Brevo campaign: {result.campaign_id}")
    print(result.message)
    if live and result.action == "scheduled":
        trigger_alert(
            "PTIA Newsletter Scheduled",
            f"A edição {result.issue.issue_id} ficou agendada na Brevo para {send_at.strftime('%d/%m/%Y %H:%M')}.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
