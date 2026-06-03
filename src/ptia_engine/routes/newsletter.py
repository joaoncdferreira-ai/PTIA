from __future__ import annotations

from ptia_engine.newsletter import generate_weekly_issue, update_newsletter_status
from ptia_engine.routes.common import send_ok, to_dict
from ptia_engine.storage import (
    load_content_performance,
    load_final_posts,
    load_radar_signals,
    load_trend_signals,
)


def handle_newsletter_generate(handler, payload) -> None:
    issue = generate_weekly_issue(
        handler.state.newsletter_issues_path,
        radar_signals=load_radar_signals(handler.state.radar_signals_path),
        trend_signals=load_trend_signals(handler.state.trends_path),
        final_posts=load_final_posts(handler.state.final_posts_path),
        performance=load_content_performance(handler.state.performance_path),
        limit=int(payload.get("limit", 5) or 5),
    )
    send_ok(handler, issue=to_dict(issue))


def handle_newsletter_status(handler, payload) -> None:
    issue = update_newsletter_status(
        handler.state.newsletter_issues_path,
        issue_id=str(payload["issue_id"]),
        status=str(payload["status"]),
        send_at=str(payload.get("send_at", "")),
    )
    send_ok(handler, issue=to_dict(issue))
