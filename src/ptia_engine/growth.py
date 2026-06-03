from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ptia_engine.learning import engagement_score
from ptia_engine.models import ContentPerformance, FinalPost
from ptia_engine.services.site import article_url_for_site_post, site_public_base_url
from ptia_engine.storage import load_content_performance, load_final_posts


DEFAULT_CAMPAIGN = "daily-post"
SOCIAL_UTM_MEDIUM = "social"


def _utm_value(value: str, fallback: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", (value or "").casefold()).strip("-")
    return clean or fallback


def add_utm_parameters(
    url: str,
    *,
    source: str,
    medium: str = SOCIAL_UTM_MEDIUM,
    campaign: str = DEFAULT_CAMPAIGN,
    content: str = "",
) -> str:
    """Return a URL with deterministic UTM parameters.

    Existing non-UTM query parameters and fragments are preserved. Existing UTM
    values are replaced so future reports can group traffic consistently.
    """

    raw_url = (url or "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    query.extend(
        [
            ("utm_source", _utm_value(source, "unknown")),
            ("utm_medium", _utm_value(medium, "referral")),
            ("utm_campaign", _utm_value(campaign, DEFAULT_CAMPAIGN)),
        ]
    )
    if content:
        query.append(("utm_content", _utm_value(content, "post")))
    return urlunparse(parsed._replace(query=urlencode(query)))


def tracked_article_url_for_social(
    site_post: FinalPost,
    *,
    channel: str,
    campaign: str = DEFAULT_CAMPAIGN,
    content: str = "",
    base_url: str | None = None,
) -> str:
    base = (base_url or site_public_base_url()).rstrip("/")
    article_url = f"{base}/{article_url_for_site_post(site_post).strip('/')}"
    return add_utm_parameters(
        article_url,
        source=channel,
        medium=SOCIAL_UTM_MEDIUM,
        campaign=campaign,
        content=content or site_post.post_id,
    )


def growth_score(perf: ContentPerformance) -> int:
    reader_score = (perf.clicks * 2) + getattr(perf, "site_views", 0) + (getattr(perf, "unique_visitors", 0) * 2)
    conversion_score = getattr(perf, "newsletter_signups", 0) * 8
    return engagement_score(perf) + reader_score + conversion_score


@dataclass(slots=True)
class GrowthGroup:
    name: str
    sample_count: int
    score: int
    impressions: int = 0
    clicks: int = 0
    site_views: int = 0
    newsletter_signups: int = 0

    @property
    def ctr_percent(self) -> float:
        if self.impressions <= 0:
            return 0.0
        return round((self.clicks / self.impressions) * 100, 2)

    def to_record(self) -> dict:
        payload = asdict(self)
        payload["ctr_percent"] = self.ctr_percent
        return payload


@dataclass(slots=True)
class GrowthPost:
    performance_id: str
    post_id: str
    channel: str
    title: str
    section: str
    score: int
    impressions: int = 0
    clicks: int = 0
    site_views: int = 0
    newsletter_signups: int = 0
    page_url: str = ""

    def to_record(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class GrowthReport:
    post_count: int
    performance_count: int
    channel_groups: list[GrowthGroup] = field(default_factory=list)
    section_groups: list[GrowthGroup] = field(default_factory=list)
    top_posts: list[GrowthPost] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return {
            "post_count": self.post_count,
            "performance_count": self.performance_count,
            "channel_groups": [group.to_record() for group in self.channel_groups],
            "section_groups": [group.to_record() for group in self.section_groups],
            "top_posts": [post.to_record() for post in self.top_posts],
            "recommendations": self.recommendations,
        }


def _post_index(posts: list[FinalPost]) -> dict[str, FinalPost]:
    index: dict[str, FinalPost] = {}
    for post in posts:
        index[post.post_id] = post
    return index


def _find_post(perf: ContentPerformance, posts_by_id: dict[str, FinalPost]) -> FinalPost | None:
    return posts_by_id.get(perf.post_id) or posts_by_id.get(perf.draft_id)


def _group_performance(performance: list[ContentPerformance], key_func) -> list[GrowthGroup]:
    buckets: dict[str, list[ContentPerformance]] = defaultdict(list)
    for perf in performance:
        buckets[key_func(perf)].append(perf)
    groups = []
    for name, rows in buckets.items():
        groups.append(
            GrowthGroup(
                name=name or "unknown",
                sample_count=len(rows),
                score=sum(growth_score(row) for row in rows),
                impressions=sum(row.impressions for row in rows),
                clicks=sum(row.clicks for row in rows),
                site_views=sum(getattr(row, "site_views", 0) for row in rows),
                newsletter_signups=sum(getattr(row, "newsletter_signups", 0) for row in rows),
            )
        )
    return sorted(groups, key=lambda group: (group.score, group.sample_count), reverse=True)


def build_growth_report(
    *,
    final_posts: list[FinalPost],
    performance: list[ContentPerformance],
    top_limit: int = 8,
    min_samples: int = 3,
) -> GrowthReport:
    posts_by_id = _post_index(final_posts)
    top_posts = []
    for perf in sorted(performance, key=growth_score, reverse=True)[:top_limit]:
        post = _find_post(perf, posts_by_id)
        top_posts.append(
            GrowthPost(
                performance_id=perf.performance_id,
                post_id=perf.post_id or perf.draft_id,
                channel=perf.channel,
                title=(post.title if post else perf.topic) or "Untitled",
                section=perf.section or "unknown",
                score=growth_score(perf),
                impressions=perf.impressions,
                clicks=perf.clicks,
                site_views=getattr(perf, "site_views", 0),
                newsletter_signups=getattr(perf, "newsletter_signups", 0),
                page_url=getattr(perf, "page_url", ""),
            )
        )

    channel_groups = _group_performance(performance, lambda perf: perf.channel)
    section_groups = _group_performance(performance, lambda perf: perf.section)
    recommendations = _recommendations(
        performance=performance,
        channel_groups=channel_groups,
        section_groups=section_groups,
        min_samples=min_samples,
    )
    return GrowthReport(
        post_count=len(final_posts),
        performance_count=len(performance),
        channel_groups=channel_groups,
        section_groups=section_groups,
        top_posts=top_posts,
        recommendations=recommendations,
    )


def _recommendations(
    *,
    performance: list[ContentPerformance],
    channel_groups: list[GrowthGroup],
    section_groups: list[GrowthGroup],
    min_samples: int,
) -> list[str]:
    if len(performance) < min_samples:
        return [
            "Amostra insuficiente: recolher metricas reais antes de alterar prioridades editoriais.",
            "Prioridade operacional: publicar links futuros com UTMs e importar clicks/views para content_performance.jsonl.",
        ]
    recommendations = []
    best_channel = channel_groups[0] if channel_groups else None
    best_section = section_groups[0] if section_groups else None
    if best_channel:
        recommendations.append(
            f"Canal com melhor sinal agregado: {best_channel.name} "
            f"(score={best_channel.score}, samples={best_channel.sample_count})."
        )
    if best_section:
        recommendations.append(
            f"Tema/seccao com melhor sinal agregado: {best_section.name} "
            f"(score={best_section.score}, samples={best_section.sample_count})."
        )
    low_click_rows = [row for row in performance if row.impressions >= 100 and row.clicks == 0]
    if low_click_rows:
        recommendations.append(
            "Ha posts com impressoes mas sem clicks registados; rever CTA, link tracking ou distribuicao."
        )
    if not recommendations:
        recommendations.append("Metricas recolhidas, mas ainda sem padrao forte. Manter cadencia e medir mais uma semana.")
    return recommendations


def format_growth_report(report: GrowthReport) -> str:
    lines = [
        "growth_report",
        f"posts={report.post_count} performance_records={report.performance_count}",
        "",
        "recommendations:",
    ]
    lines.extend(f"- {item}" for item in report.recommendations)
    if report.channel_groups:
        lines.extend(["", "channels:"])
        lines.extend(
            f"- {group.name}: score={group.score} samples={group.sample_count} "
            f"impressions={group.impressions} clicks={group.clicks} ctr={group.ctr_percent}%"
            for group in report.channel_groups
        )
    if report.section_groups:
        lines.extend(["", "sections:"])
        lines.extend(
            f"- {group.name}: score={group.score} samples={group.sample_count} "
            f"views={group.site_views} signups={group.newsletter_signups}"
            for group in report.section_groups
        )
    if report.top_posts:
        lines.extend(["", "top_posts:"])
        lines.extend(
            f"- {post.channel} score={post.score} clicks={post.clicks} views={post.site_views}: {post.title[:90]}"
            for post in report.top_posts
        )
    return "\n".join(lines)


def load_growth_report(
    *,
    final_posts_path: Path,
    performance_path: Path,
    top_limit: int = 8,
    min_samples: int = 3,
) -> GrowthReport:
    return build_growth_report(
        final_posts=load_final_posts(final_posts_path),
        performance=load_content_performance(performance_path),
        top_limit=top_limit,
        min_samples=min_samples,
    )


def write_growth_report(path: Path, report: GrowthReport, *, json_output: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if json_output:
        path.write_text(json.dumps(report.to_record(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(format_growth_report(report) + "\n", encoding="utf-8")
