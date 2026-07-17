from __future__ import annotations

from dataclasses import dataclass
from calendar import monthrange
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ptia_engine.brevo import (
    BrevoAPIError,
    BrevoClient,
    BrevoConfig,
    BrevoConfigError,
)
from ptia_engine.models import NewsletterIssue
from ptia_engine.newsletter import (
    NEWSLETTER_GENERATOR_VERSION,
    _parse_date,
    generate_weekly_issue,
    has_suspicious_encoding,
    repair_text_encoding,
    update_newsletter_delivery,
)
from ptia_engine.storage import (
    load_content_performance,
    load_final_posts,
    load_newsletter_issues,
    load_radar_signals,
    load_trend_signals,
)


PTIA_TIMEZONE = "Europe/Lisbon"
FRIDAY = 4
RECOVERY_DEADLINE_HOUR = 18


class NewsletterPreflightError(RuntimeError):
    pass


class EuropeLisbonFallback(tzinfo):
    """Minimal Europe/Lisbon timezone fallback for Windows without tzdata."""

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=1) if self.dst(dt) else timedelta(0)

    def dst(self, dt: datetime | None) -> timedelta:
        if dt is None:
            return timedelta(0)
        naive = dt.replace(tzinfo=None)
        start = datetime(naive.year, 3, _last_sunday(naive.year, 3), 1, 0)
        end = datetime(naive.year, 10, _last_sunday(naive.year, 10), 2, 0)
        return timedelta(hours=1) if start <= naive < end else timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "WEST" if self.dst(dt) else "WET"


def _last_sunday(year: int, month: int) -> int:
    last_day = monthrange(year, month)[1]
    candidate = date(year, month, last_day)
    return last_day - ((candidate.weekday() - 6) % 7)


def ptia_timezone(timezone_name: str = PTIA_TIMEZONE) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == PTIA_TIMEZONE:
            return EuropeLisbonFallback()
        raise


@dataclass(slots=True)
class NewsletterDeliveryResult:
    action: str
    issue: NewsletterIssue
    send_at: datetime
    campaign_id: str = ""
    message: str = ""


def next_friday_send_at(
    now: datetime | None = None,
    *,
    hour: int = 9,
    minute: int = 0,
    timezone_name: str = PTIA_TIMEZONE,
    recovery_deadline_hour: int = RECOVERY_DEADLINE_HOUR,
) -> datetime:
    tz = ptia_timezone(timezone_name)
    current = now.astimezone(tz) if now else datetime.now(tz)
    days_until_friday = (FRIDAY - current.weekday()) % 7
    target_date = current.date() + timedelta(days=days_until_friday)
    target = datetime.combine(target_date, time(hour, minute), tzinfo=tz)
    if target <= current:
        recovery_deadline = datetime.combine(
            target_date,
            time(recovery_deadline_hour, 0),
            tzinfo=tz,
        )
        if target_date == current.date() and current < recovery_deadline:
            target = current + timedelta(minutes=2)
        else:
            target += timedelta(days=7)
    return target


def issue_matches_send_date(issue: NewsletterIssue, target_date: date) -> bool:
    if not issue.send_at:
        return False
    return _parse_date(issue.send_at).astimezone(ptia_timezone()).date() == target_date


def latest_issue_for_send_date(
    issues: list[NewsletterIssue],
    target_date: date,
) -> NewsletterIssue | None:
    matches = [issue for issue in issues if issue_matches_send_date(issue, target_date)]
    if not matches:
        return None
    return sorted(matches, key=lambda issue: _parse_date(issue.created_at), reverse=True)[0]


def validate_newsletter_issue(issue: NewsletterIssue) -> None:
    errors = []
    if not issue.subject.strip():
        errors.append("subject is empty")
    if not issue.item_ids:
        errors.append("no editorial items were selected")
    if not issue.html.strip():
        errors.append("HTML content is empty")
    story_image_count = issue.html.count('class="ptia-story-image"')
    if issue.item_ids and story_image_count != len(issue.item_ids):
        errors.append(
            f"expected {len(issue.item_ids)} editorial images, found {story_image_count}"
        )
    if "{{ unsubscribe }}" not in issue.html:
        errors.append("HTML is missing the Brevo unsubscribe tag")
    if not issue.text.strip():
        errors.append("plain-text content is empty")
    subject = repair_text_encoding(issue.subject)
    preheader = repair_text_encoding(issue.preheader)
    html = repair_text_encoding(issue.html)
    plain_text = repair_text_encoding(issue.text)
    if any(has_suspicious_encoding(value) for value in (subject, preheader, html, plain_text)):
        errors.append("newsletter contains suspicious encoding artifacts")
    if errors:
        raise NewsletterPreflightError("; ".join(errors))


def schedule_weekly_newsletter(
    data_dir: Path,
    *,
    send_at: datetime,
    limit: int = 5,
    force: bool = False,
    dry_run: bool = False,
    client: BrevoClient | None = None,
) -> NewsletterDeliveryResult:
    issues_path = data_dir / "newsletter_issues.jsonl"
    send_at = send_at.astimezone(ptia_timezone())
    send_at_iso = send_at.isoformat()

    issue = latest_issue_for_send_date(load_newsletter_issues(issues_path), send_at.date())
    if issue and issue.status in {"scheduled", "sent"} and issue.provider_campaign_id:
        return NewsletterDeliveryResult(
            action="skipped_already_scheduled",
            issue=issue,
            send_at=send_at,
            campaign_id=issue.provider_campaign_id,
            message=f"Newsletter already {issue.status} for {send_at_iso}.",
        )

    outdated_draft = bool(
        issue
        and issue.generator_version != NEWSLETTER_GENERATOR_VERSION
        and not issue.provider_campaign_id
    )
    if issue is None or outdated_draft or (force and not issue.provider_campaign_id):
        issue = generate_weekly_issue(
            issues_path,
            radar_signals=load_radar_signals(data_dir / "radar_signals.jsonl"),
            trend_signals=load_trend_signals(data_dir / "trend_signals.jsonl"),
            final_posts=load_final_posts(data_dir / "final_posts.jsonl"),
            performance=load_content_performance(data_dir / "content_performance.jsonl"),
            limit=limit,
            send_at=send_at_iso,
            issue_date=send_at.date(),
        )
    elif issue.send_at != send_at_iso:
        issue = update_newsletter_delivery(issues_path, issue.issue_id, send_at=send_at_iso)

    if issue.generator_version != NEWSLETTER_GENERATOR_VERSION:
        raise NewsletterPreflightError(
            "campaign content was generated by an outdated newsletter compiler"
        )
    validate_newsletter_issue(issue)

    if dry_run:
        return NewsletterDeliveryResult(
            action="dry_run",
            issue=issue,
            send_at=send_at,
            campaign_id=issue.provider_campaign_id,
            message="Newsletter generated/reused without touching Brevo.",
        )

    campaign_id = issue.provider_campaign_id
    try:
        if client is None:
            client = BrevoClient(BrevoConfig.from_env())
            client.validate_lists()
            client.validate_sender()
            client.validate_capacity()
        if not campaign_id:
            existing = client.find_weekly_campaign(send_at)
            if existing:
                campaign_id = str(existing.get("id", ""))
                provider_status = str(existing.get("status", "draft"))
                issue = update_newsletter_delivery(
                    issues_path,
                    issue.issue_id,
                    status=(
                        "scheduled"
                        if provider_status in {"queued", "scheduled", "sent"}
                        else issue.status
                    ),
                    send_at=send_at_iso,
                    delivery_provider="brevo",
                    provider_campaign_id=campaign_id,
                    provider_status=provider_status,
                    delivery_error="",
                )
                if provider_status in {"queued", "scheduled", "sent"}:
                    return NewsletterDeliveryResult(
                        action="skipped_already_scheduled",
                        issue=issue,
                        send_at=send_at,
                        campaign_id=campaign_id,
                        message=(
                            f"Brevo campaign already {provider_status} "
                            f"for {send_at.date().isoformat()}."
                        ),
                    )
        if not campaign_id:
            created = client.create_campaign(issue, send_at=send_at)
            campaign = created.get("data", {})
            campaign_id = str(campaign.get("id", ""))
            if not campaign_id:
                raise BrevoAPIError(200, "Campaign created without data.id")
            issue = update_newsletter_delivery(
                issues_path,
                issue.issue_id,
                send_at=send_at_iso,
                delivery_provider="brevo",
                provider_campaign_id=campaign_id,
                provider_status=str(campaign.get("status", "draft")),
                delivery_error="",
            )

        scheduled = client.schedule_campaign(campaign_id, send_at=send_at)
        campaign = scheduled.get("data", {})
        issue = update_newsletter_delivery(
            issues_path,
            issue.issue_id,
            status="scheduled",
            send_at=send_at_iso,
            delivery_provider="brevo",
            provider_campaign_id=campaign_id,
            provider_status=str(campaign.get("status", "scheduled")),
            delivery_error="",
        )
        return NewsletterDeliveryResult(
            action="scheduled",
            issue=issue,
            send_at=send_at,
            campaign_id=campaign_id,
            message=f"Newsletter scheduled in Brevo for {send_at_iso}.",
        )
    except (BrevoAPIError, BrevoConfigError, NewsletterPreflightError) as exc:
        issue = update_newsletter_delivery(
            issues_path,
            issue.issue_id,
            status="failed",
            send_at=send_at_iso,
            delivery_provider="brevo",
            provider_campaign_id=campaign_id,
            delivery_error=str(exc),
        )
        raise
