from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ptia_engine.http_client import requests_open_direct
from ptia_engine.models import NewsletterIssue


BREVO_API_BASE_URL = "https://api.brevo.com/v3"
BREVO_FREE_DAILY_LIMIT = 300


class BrevoConfigError(RuntimeError):
    def __init__(self, missing: list[str] | None = None, *, invalid: list[str] | None = None) -> None:
        self.missing = missing or []
        self.invalid = invalid or []
        details = []
        if self.missing:
            details.append("missing: " + ", ".join(self.missing))
        if self.invalid:
            details.append("invalid: " + ", ".join(self.invalid))
        super().__init__("Brevo config error (" + "; ".join(details) + ")")


class BrevoAPIError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Brevo API error {status_code}: {body[:500]}")


@dataclass(frozen=True, slots=True)
class BrevoConfig:
    api_key: str
    list_ids: tuple[int, ...]
    from_email: str
    from_name: str = "PTIA"
    reply_to: str = ""
    max_recipients: int = BREVO_FREE_DAILY_LIMIT
    doi_template_id: int | None = None
    base_url: str = BREVO_API_BASE_URL

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "BrevoConfig":
        values = env if env is not None else os.environ
        api_key = values.get("BREVO_API_KEY", "").strip()
        raw_list_ids = (
            values.get("BREVO_LIST_IDS", "").strip()
            or values.get("BREVO_LIST_ID", "").strip()
        )
        from_email = values.get("PTIA_NEWSLETTER_FROM_EMAIL", "").strip()
        from_name = values.get("PTIA_NEWSLETTER_FROM_NAME", "PTIA").strip() or "PTIA"
        reply_to = values.get("PTIA_NEWSLETTER_REPLY_TO", "").strip() or from_email

        missing = []
        if not api_key:
            missing.append("BREVO_API_KEY")
        if not raw_list_ids:
            missing.append("BREVO_LIST_ID or BREVO_LIST_IDS")
        if not from_email:
            missing.append("PTIA_NEWSLETTER_FROM_EMAIL")

        invalid = []
        list_ids: list[int] = []
        for raw_id in raw_list_ids.replace(";", ",").split(","):
            value = raw_id.strip()
            if not value:
                continue
            try:
                list_id = int(value)
            except ValueError:
                invalid.append(f"invalid Brevo list ID: {value}")
                continue
            if list_id <= 0:
                invalid.append(f"Brevo list ID must be positive: {value}")
                continue
            list_ids.append(list_id)

        raw_max = values.get("BREVO_MAX_RECIPIENTS", str(BREVO_FREE_DAILY_LIMIT)).strip()
        try:
            max_recipients = int(raw_max)
            if max_recipients <= 0:
                raise ValueError
        except ValueError:
            max_recipients = BREVO_FREE_DAILY_LIMIT
            invalid.append("BREVO_MAX_RECIPIENTS must be a positive integer")

        raw_doi_template_id = values.get("BREVO_DOI_TEMPLATE_ID", "").strip()
        doi_template_id = None
        if raw_doi_template_id:
            try:
                doi_template_id = int(raw_doi_template_id)
                if doi_template_id <= 0:
                    raise ValueError
            except ValueError:
                invalid.append("BREVO_DOI_TEMPLATE_ID must be a positive integer")

        if missing or invalid:
            raise BrevoConfigError(missing, invalid=invalid)
        return cls(
            api_key=api_key,
            list_ids=tuple(dict.fromkeys(list_ids)),
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            max_recipients=max_recipients,
            doi_template_id=doi_template_id,
            base_url=values.get("BREVO_BASE_URL", BREVO_API_BASE_URL).rstrip("/"),
        )


Transport = Callable[..., Any]


def brevo_html(html: str) -> str:
    return (
        html.replace("{{$unsubscribe}}", "{{ unsubscribe }}")
        .replace("{$unsubscribe}", "{{ unsubscribe }}")
        .replace("{$url}", "{{ mirror }}")
        .replace("MailerLite", "Brevo")
    )


def build_campaign_payload(
    issue: NewsletterIssue,
    config: BrevoConfig,
    *,
    send_at: datetime | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": f"PTIA Weekly - {(send_at or datetime.now()).date().isoformat()}",
        "subject": issue.subject,
        "previewText": issue.preheader,
        "sender": {"name": config.from_name, "email": config.from_email},
        "replyTo": config.reply_to,
        "recipients": {"listIds": list(config.list_ids)},
        "htmlContent": brevo_html(issue.html),
        "mirrorActive": True,
    }
    if send_at is not None:
        payload["scheduledAt"] = send_at.isoformat()
    return payload


class BrevoClient:
    def __init__(
        self,
        config: BrevoConfig,
        *,
        transport: Transport = requests_open_direct,
        timeout: int | float = 30,
    ) -> None:
        self.config = config
        self.transport = transport
        self.timeout = timeout

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/account")

    def list_lists(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/contacts/lists?limit=50&offset=0&sort=desc")
        return [item for item in payload.get("lists", []) if isinstance(item, dict)]

    def validate_lists(self) -> list[dict[str, Any]]:
        lists = self.list_lists()
        available_ids = {int(item["id"]) for item in lists if str(item.get("id", "")).isdigit()}
        missing = [list_id for list_id in self.config.list_ids if list_id not in available_ids]
        if missing:
            raise BrevoConfigError(invalid=["unknown Brevo list IDs: " + ", ".join(map(str, missing))])
        return [item for item in lists if int(item.get("id", 0)) in self.config.list_ids]

    def list_senders(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/senders")
        return [item for item in payload.get("senders", []) if isinstance(item, dict)]

    def validate_sender(self) -> dict[str, Any]:
        expected = self.config.from_email.casefold()
        for sender in self.list_senders():
            if str(sender.get("email", "")).casefold() != expected:
                continue
            if sender.get("active") is not True:
                raise BrevoConfigError(invalid=[f"Brevo sender is not active: {self.config.from_email}"])
            return sender
        raise BrevoConfigError(invalid=[f"unknown Brevo sender: {self.config.from_email}"])

    def recipient_count(self) -> int:
        query = urllib.parse.urlencode(
            [("limit", "1"), *(("listIds", str(list_id)) for list_id in self.config.list_ids)]
        )
        payload = self._request("GET", f"/contacts?{query}")
        return int(payload.get("count", 0))

    def validate_capacity(self) -> int:
        count = self.recipient_count()
        if count > self.config.max_recipients:
            raise BrevoConfigError(
                invalid=[
                    f"Brevo recipients ({count}) exceed configured free-plan limit "
                    f"({self.config.max_recipients})"
                ]
            )
        return count

    def create_doi_template(self) -> int:
        payload = self._request(
            "POST",
            "/smtp/templates",
            {
                "sender": {
                    "name": self.config.from_name,
                    "email": self.config.from_email,
                },
                "subject": "Confirma a tua subscrição na PTIA Weekly",
                "templateName": "PTIA Weekly - Double opt-in",
                "htmlContent": (
                    "<!doctype html><html lang=\"pt\"><head><meta charset=\"utf-8\">"
                    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                    "</head><body style=\"margin:0;background:#f6f1e7;color:#17130f;"
                    "font-family:Arial,sans-serif\">"
                    "<div style=\"display:none;max-height:0;overflow:hidden\">"
                    "Falta apenas confirmar o teu email para receberes a PTIA Weekly.</div>"
                    "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" "
                    "cellpadding=\"0\" style=\"background:#f6f1e7\"><tr>"
                    "<td align=\"center\" style=\"padding:32px 16px\">"
                    "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" "
                    "cellpadding=\"0\" style=\"max-width:560px;background:#ffffff;"
                    "border:1px solid #e4ddd0\"><tr><td style=\"padding:32px\">"
                    "<p style=\"margin:0 0 24px;font-size:14px;font-weight:700;"
                    "letter-spacing:1px\">PTIA WEEKLY</p>"
                    "<h1 style=\"margin:0 0 18px;font-family:Georgia,serif;font-size:32px;"
                    "line-height:1.15\">Confirma a tua subscrição</h1>"
                    "<p style=\"margin:0 0 22px;font-size:16px;line-height:1.6\">"
                    "Recebeste este email porque pediste para receber a PTIA Weekly em "
                    "ptia.pt. Confirma abaixo para concluíres a subscrição.</p>"
                    "<p style=\"margin:0 0 24px\"><a href=\"{{ doubleoptin }}\" "
                    "style=\"display:inline-block;background:#17130f;color:#ffffff;"
                    "padding:13px 20px;text-decoration:none;font-weight:700\">"
                    "Confirmar subscrição</a></p>"
                    "<p style=\"margin:0 0 8px;font-size:14px;line-height:1.55;"
                    "color:#574f47\">Se não fizeste este pedido, ignora o email. "
                    "Não serás adicionado à lista.</p>"
                    "<p style=\"margin:0;font-size:14px;line-height:1.55;color:#574f47\">"
                    "PTIA, curadoria independente de Inteligência Artificial para Portugal."
                    "</p></td></tr></table></td></tr></table></body></html>"
                ),
                "isActive": True,
                "replyTo": self.config.reply_to,
                "tag": "optin",
            },
        )
        template_id = int(payload.get("id", 0))
        if template_id <= 0:
            raise BrevoAPIError(200, "DOI template created without an ID")
        return template_id

    def get_doi_template(self, template_id: int) -> dict[str, Any]:
        return self._request("GET", f"/smtp/templates/{template_id}")

    def validate_doi_template(self, template_id: int | None = None) -> dict[str, Any]:
        resolved_id = template_id or self.config.doi_template_id
        if not resolved_id:
            raise BrevoConfigError(missing=["BREVO_DOI_TEMPLATE_ID"])
        template = self.get_doi_template(resolved_id)
        if template.get("isActive") is not True:
            raise BrevoConfigError(invalid=[f"Brevo DOI template is not active: {resolved_id}"])
        if template.get("doiTemplate") is not True:
            raise BrevoConfigError(invalid=[f"Brevo template is not double opt-in: {resolved_id}"])
        return template

    def create_doi_contact(
        self,
        email: str,
        *,
        first_name: str = "",
        redirection_url: str = "https://ptia.pt/#newsletter",
    ) -> None:
        if not self.config.doi_template_id:
            raise BrevoConfigError(missing=["BREVO_DOI_TEMPLATE_ID"])
        payload: dict[str, Any] = {
            "email": email,
            "includeListIds": list(self.config.list_ids),
            "redirectionUrl": redirection_url,
            "templateId": self.config.doi_template_id,
        }
        if first_name:
            payload["attributes"] = {"FIRSTNAME": first_name}
        self._request("POST", "/contacts/doubleOptinConfirmation", payload)

    def create_campaign(self, issue: NewsletterIssue, *, send_at: datetime) -> dict[str, Any]:
        payload = build_campaign_payload(issue, self.config, send_at=send_at)
        payload.pop("scheduledAt", None)
        payload = self._request(
            "POST",
            "/emailCampaigns",
            payload,
        )
        campaign_id = str(payload.get("id", ""))
        return {"data": {"id": campaign_id, "status": "draft"}}

    def list_campaigns(self, *, limit: int = 100) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "type": "classic",
                "limit": max(1, min(limit, 100)),
                "offset": 0,
                "sort": "desc",
                "excludeHtmlContent": "true",
            }
        )
        payload = self._request("GET", f"/emailCampaigns?{query}")
        return [item for item in payload.get("campaigns", []) if isinstance(item, dict)]

    def find_weekly_campaign(self, send_at: datetime) -> dict[str, Any] | None:
        expected_name = f"PTIA Weekly - {send_at.date().isoformat()}"
        for campaign in self.list_campaigns():
            if str(campaign.get("name", "")) == expected_name:
                return campaign
        return None

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"/emailCampaigns/{campaign_id}?excludeHtmlContent=true",
        )
        return {"data": payload}

    def delete_campaign(self, campaign_id: str) -> None:
        self._request("DELETE", f"/emailCampaigns/{campaign_id}")

    def schedule_campaign(self, campaign_id: str, *, send_at: datetime) -> dict[str, Any]:
        self._request(
            "PUT",
            f"/emailCampaigns/{campaign_id}",
            {"scheduledAt": send_at.isoformat()},
        )
        return self.get_campaign(campaign_id)

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
                "api-key": self.config.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "PTIA-Newsletter/1.0 (+https://ptia.pt)",
            },
        )
        try:
            with self.transport(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BrevoAPIError(exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise BrevoAPIError(0, str(exc.reason)) from exc
