from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ptia_engine.http_client import urlopen_direct
from ptia_engine.models import NewsletterIssue


MAILERLITE_API_BASE_URL = "https://connect.mailerlite.com/api"
MAILERLITE_API_VERSION = "2026-06-06"


class MailerLiteConfigError(RuntimeError):
    def __init__(self, missing: list[str] | None = None, *, invalid: list[str] | None = None) -> None:
        self.missing = missing or []
        self.invalid = invalid or []
        details = []
        if self.missing:
            details.append("missing: " + ", ".join(self.missing))
        if self.invalid:
            details.append("invalid: " + ", ".join(self.invalid))
        super().__init__("MailerLite config error (" + "; ".join(details) + ")")


class MailerLiteAPIError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"MailerLite API error {status_code}: {body[:500]}")


@dataclass(frozen=True, slots=True)
class MailerLiteConfig:
    api_key: str
    group_ids: tuple[str, ...]
    from_email: str
    from_name: str = "PTIA"
    reply_to: str = ""
    timezone_id: int | None = None
    language_id: int | None = None
    base_url: str = MAILERLITE_API_BASE_URL

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "MailerLiteConfig":
        values = env if env is not None else os.environ
        api_key = values.get("MAILERLITE_API_KEY", "").strip()
        raw_group_ids = (
            values.get("MAILERLITE_GROUP_IDS", "").strip()
            or values.get("MAILERLITE_GROUP_ID", "").strip()
        )
        group_ids = tuple(part.strip() for part in raw_group_ids.replace(";", ",").split(",") if part.strip())
        from_email = (
            values.get("PTIA_NEWSLETTER_FROM_EMAIL", "").strip()
            or values.get("MAILERLITE_FROM_EMAIL", "").strip()
        )
        from_name = values.get("PTIA_NEWSLETTER_FROM_NAME", "PTIA").strip() or "PTIA"
        reply_to = (
            values.get("PTIA_NEWSLETTER_REPLY_TO", "").strip()
            or values.get("MAILERLITE_REPLY_TO", "").strip()
            or from_email
        )
        missing = []
        if not api_key:
            missing.append("MAILERLITE_API_KEY")
        if not group_ids:
            missing.append("MAILERLITE_GROUP_ID or MAILERLITE_GROUP_IDS")
        if not from_email:
            missing.append("PTIA_NEWSLETTER_FROM_EMAIL or MAILERLITE_FROM_EMAIL")
        invalid = []

        def optional_integer(name: str) -> int | None:
            raw = values.get(name, "").strip()
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                invalid.append(f"{name} must be an integer")
                return None

        timezone_id = optional_integer("MAILERLITE_TIMEZONE_ID")
        language_id = optional_integer("MAILERLITE_LANGUAGE_ID")
        if missing or invalid:
            raise MailerLiteConfigError(missing, invalid=invalid)
        return cls(
            api_key=api_key,
            group_ids=group_ids,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            timezone_id=timezone_id,
            language_id=language_id,
            base_url=values.get("MAILERLITE_BASE_URL", MAILERLITE_API_BASE_URL).rstrip("/"),
        )


Transport = Callable[..., Any]


def build_campaign_payload(
    issue: NewsletterIssue,
    config: MailerLiteConfig,
    *,
    send_at: datetime,
) -> dict[str, Any]:
    email: dict[str, Any] = {
        "subject": issue.subject,
        "from_name": config.from_name,
        "from": config.from_email,
        "reply_to": config.reply_to,
        "content": issue.html,
    }
    payload: dict[str, Any] = {
        "name": f"PTIA Weekly - {send_at.date().isoformat()}",
        "type": "regular",
        "emails": [email],
        "groups": list(config.group_ids),
    }
    if config.language_id:
        payload["language_id"] = config.language_id
    return payload


def build_schedule_payload(send_at: datetime, config: MailerLiteConfig) -> dict[str, Any]:
    schedule: dict[str, Any] = {
        "date": send_at.date().isoformat(),
        "hours": f"{send_at.hour:02d}",
        "minutes": f"{send_at.minute:02d}",
    }
    if config.timezone_id is not None:
        schedule["timezone_id"] = config.timezone_id
    return {"delivery": "scheduled", "schedule": schedule}


class MailerLiteClient:
    def __init__(
        self,
        config: MailerLiteConfig,
        *,
        transport: Transport = urlopen_direct,
        timeout: int | float = 30,
    ) -> None:
        self.config = config
        self.transport = transport
        self.timeout = timeout

    def create_campaign(self, issue: NewsletterIssue, *, send_at: datetime) -> dict[str, Any]:
        return self._request(
            "POST",
            "/campaigns",
            build_campaign_payload(issue, self.config, send_at=send_at),
        )

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def delete_campaign(self, campaign_id: str) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")

    def list_groups(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/groups?limit=1000")
        return [item for item in payload.get("data", []) if isinstance(item, dict)]

    def validate_groups(self) -> list[dict[str, Any]]:
        groups = self.list_groups()
        available_ids = {str(group.get("id", "")) for group in groups}
        missing = [group_id for group_id in self.config.group_ids if group_id not in available_ids]
        if missing:
            raise MailerLiteConfigError(
                invalid=["unknown MailerLite group IDs: " + ", ".join(missing)]
            )
        return [group for group in groups if str(group.get("id", "")) in self.config.group_ids]

    def list_timezones(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/timezones")
        return [item for item in payload.get("data", []) if isinstance(item, dict)]

    def resolve_timezone_id(self, timezone_name: str) -> int:
        for timezone in self.list_timezones():
            if str(timezone.get("name", "")) == timezone_name:
                try:
                    return int(timezone["id"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise MailerLiteConfigError(
                        invalid=[f"invalid timezone ID for {timezone_name}"]
                    ) from exc
        raise MailerLiteConfigError(
            invalid=[f"MailerLite timezone not found: {timezone_name}"]
        )

    def schedule_campaign(self, campaign_id: str, *, send_at: datetime) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/campaigns/{campaign_id}/schedule",
            build_schedule_payload(send_at, self.config),
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Version": MAILERLITE_API_VERSION,
            },
        )
        try:
            with self.transport(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise MailerLiteAPIError(exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise MailerLiteAPIError(0, str(exc.reason)) from exc
