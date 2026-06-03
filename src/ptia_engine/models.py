from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class Source:
    source_id: str
    name: str
    url: str
    rss_url: str
    type: str
    category: str
    language: str
    country: str
    trust_score: int
    active: bool
    notes: str = ""

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Source":
        return cls(
            source_id=str(record["source_id"]),
            name=str(record["name"]),
            url=str(record.get("url", "")),
            rss_url=str(record.get("rss_url", "")),
            type=str(record.get("type", "")),
            category=str(record.get("category", "")),
            language=str(record.get("language", "unknown")),
            country=str(record.get("country", "")),
            trust_score=int(record.get("trust_score", 5)),
            active=bool(record.get("active", False)),
            notes=str(record.get("notes", "")),
        )


@dataclass(slots=True)
class RawArticle:
    article_id: str
    source_id: str
    source_name: str
    title_original: str
    url: str
    author: str = ""
    published_at: str = ""
    fetched_at: str = field(default_factory=utc_now_iso)
    language: str = "unknown"
    country: str = ""
    raw_excerpt: str = ""
    image_url: str = ""
    status: str = "new"
    duplicate_of: str = ""
    content_hash: str = ""

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "RawArticle":
        return cls(
            article_id=str(record["article_id"]),
            source_id=str(record["source_id"]),
            source_name=str(record.get("source_name", "")),
            title_original=str(record.get("title_original", "")),
            url=str(record.get("url", "")),
            author=str(record.get("author", "")),
            published_at=str(record.get("published_at", "")),
            fetched_at=str(record.get("fetched_at", "")),
            language=str(record.get("language", "unknown")),
            country=str(record.get("country", "")),
            raw_excerpt=str(record.get("raw_excerpt", "")),
            image_url=str(record.get("image_url", "")),
            status=str(record.get("status", "new")),
            duplicate_of=str(record.get("duplicate_of", "")),
            content_hash=str(record.get("content_hash", "")),
        )


@dataclass(slots=True)
class ProcessedItem:
    item_id: str
    article_id: str
    source_id: str
    source_name: str
    title_original: str
    source_url: str
    section: str
    relevance_score: int
    hype_score: int
    portugal_relevance_score: int
    builder_relevance_score: int
    business_relevance_score: int
    should_cover: bool
    reason: str
    risk_notes: str = ""
    summary_pt: str = ""
    why_it_matters_pt: str = ""
    portugal_angle_pt: str = ""
    key_takeaways: str = ""
    ai_confidence: int = 0
    editorial_status: str = "needs_review"
    editor_notes: str = ""
    classifier_mode: str = "heuristic"
    model: str = ""
    estimated_cost_usd: float = 0.0
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ProcessedItem":
        return cls(
            item_id=str(record["item_id"]),
            article_id=str(record["article_id"]),
            source_id=str(record.get("source_id", "")),
            source_name=str(record.get("source_name", "")),
            title_original=str(record.get("title_original", "")),
            source_url=str(record.get("source_url", "")),
            section=str(record.get("section", "world_ai")),
            relevance_score=int(record.get("relevance_score", 1)),
            hype_score=int(record.get("hype_score", 1)),
            portugal_relevance_score=int(record.get("portugal_relevance_score", 1)),
            builder_relevance_score=int(record.get("builder_relevance_score", 1)),
            business_relevance_score=int(record.get("business_relevance_score", 1)),
            should_cover=bool(record.get("should_cover", False)),
            reason=str(record.get("reason", "")),
            risk_notes=str(record.get("risk_notes", "")),
            summary_pt=str(record.get("summary_pt", "")),
            why_it_matters_pt=str(record.get("why_it_matters_pt", "")),
            portugal_angle_pt=str(record.get("portugal_angle_pt", "")),
            key_takeaways=str(record.get("key_takeaways", "")),
            ai_confidence=int(record.get("ai_confidence", 0)),
            editorial_status=str(record.get("editorial_status", "needs_review")),
            editor_notes=str(record.get("editor_notes", "")),
            classifier_mode=str(record.get("classifier_mode", "heuristic")),
            model=str(record.get("model", "")),
            estimated_cost_usd=float(record.get("estimated_cost_usd", 0.0)),
            created_at=str(record.get("created_at", "")),
        )


@dataclass(slots=True)
class ContentDraft:
    draft_id: str
    item_id: str
    article_id: str
    channel: str
    format: str
    title: str
    body: str = ""
    caption: str = ""
    hashtags: str = ""
    cta: str = ""
    image_prompt: str = ""
    carousel_outline: str = ""
    scheduled_time: str = ""
    status: str = "draft"
    buffer_post_id: str = ""
    published_url: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ContentDraft":
        return cls(
            draft_id=str(record["draft_id"]),
            item_id=str(record["item_id"]),
            article_id=str(record.get("article_id", "")),
            channel=str(record.get("channel", "")),
            format=str(record.get("format", "")),
            title=str(record.get("title", "")),
            body=str(record.get("body", "")),
            caption=str(record.get("caption", "")),
            hashtags=str(record.get("hashtags", "")),
            cta=str(record.get("cta", "")),
            image_prompt=str(record.get("image_prompt", "")),
            carousel_outline=str(record.get("carousel_outline", "")),
            scheduled_time=str(record.get("scheduled_time", "")),
            status=str(record.get("status", "draft")),
            buffer_post_id=str(record.get("buffer_post_id", "")),
            published_url=str(record.get("published_url", "")),
            created_at=str(record.get("created_at", "")),
        )


@dataclass(slots=True)
class ContentPerformance:
    performance_id: str
    draft_id: str
    post_id: str
    channel: str
    published_at: str
    topic: str
    section: str
    impressions: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    clicks: int = 0
    followers_gained: int = 0
    site_views: int = 0
    unique_visitors: int = 0
    newsletter_signups: int = 0
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    utm_content: str = ""
    page_url: str = ""
    referrer: str = ""
    notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ContentPerformance":
        return cls(
            performance_id=str(record["performance_id"]),
            draft_id=str(record.get("draft_id", "")),
            post_id=str(record.get("post_id", "")),
            channel=str(record.get("channel", "")),
            published_at=str(record.get("published_at", "")),
            topic=str(record.get("topic", "")),
            section=str(record.get("section", "")),
            impressions=int(record.get("impressions", 0)),
            likes=int(record.get("likes", 0)),
            comments=int(record.get("comments", 0)),
            shares=int(record.get("shares", 0)),
            saves=int(record.get("saves", 0)),
            clicks=int(record.get("clicks", 0)),
            followers_gained=int(record.get("followers_gained", 0)),
            site_views=int(record.get("site_views", 0)),
            unique_visitors=int(record.get("unique_visitors", 0)),
            newsletter_signups=int(record.get("newsletter_signups", 0)),
            utm_source=str(record.get("utm_source", "")),
            utm_medium=str(record.get("utm_medium", "")),
            utm_campaign=str(record.get("utm_campaign", "")),
            utm_content=str(record.get("utm_content", "")),
            page_url=str(record.get("page_url", "")),
            referrer=str(record.get("referrer", "")),
            notes=str(record.get("notes", "")),
            created_at=str(record.get("created_at", "")),
        )


@dataclass(slots=True)
class TrendSignal:
    signal_id: str
    platform: str
    title: str
    url: str
    discussion_url: str
    author: str = ""
    published_at: str = ""
    fetched_at: str = field(default_factory=utc_now_iso)
    score: int = 0
    comments: int = 0
    engagement_score: int = 0
    topic: str = ""
    why_it_worked: str = ""
    ptia_angle: str = ""
    risk_notes: str = ""
    status: str = "new"

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "TrendSignal":
        return cls(
            signal_id=str(record["signal_id"]),
            platform=str(record.get("platform", "")),
            title=str(record.get("title", "")),
            url=str(record.get("url", "")),
            discussion_url=str(record.get("discussion_url", "")),
            author=str(record.get("author", "")),
            published_at=str(record.get("published_at", "")),
            fetched_at=str(record.get("fetched_at", "")),
            score=int(record.get("score", 0)),
            comments=int(record.get("comments", 0)),
            engagement_score=int(record.get("engagement_score", 0)),
            topic=str(record.get("topic", "")),
            why_it_worked=str(record.get("why_it_worked", "")),
            ptia_angle=str(record.get("ptia_angle", "")),
            risk_notes=str(record.get("risk_notes", "")),
            status=str(record.get("status", "new")),
        )


@dataclass(slots=True)
class ContentAsset:
    asset_id: str
    draft_id: str
    item_id: str
    channel: str
    asset_type: str
    title: str
    file_path: str
    format: str = "svg"
    status: str = "generated"
    notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ContentAsset":
        return cls(
            asset_id=str(record["asset_id"]),
            draft_id=str(record.get("draft_id", "")),
            item_id=str(record.get("item_id", "")),
            channel=str(record.get("channel", "")),
            asset_type=str(record.get("asset_type", "")),
            title=str(record.get("title", "")),
            file_path=str(record.get("file_path", "")),
            format=str(record.get("format", "svg")),
            status=str(record.get("status", "generated")),
            notes=str(record.get("notes", "")),
            created_at=str(record.get("created_at", "")),
        )


@dataclass(slots=True)
class RadarSignal:
    signal_id: str
    source_type: str
    source_name: str
    title: str
    url: str
    published_at: str = ""
    fetched_at: str = field(default_factory=utc_now_iso)
    engagement_score: int = 0
    summary: str = ""
    topic_hint: str = ""
    why_it_matters: str = ""
    why_engaged: str = ""
    status: str = "new"
    notes: str = ""

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "RadarSignal":
        return cls(
            signal_id=str(record["signal_id"]),
            source_type=str(record.get("source_type", "")),
            source_name=str(record.get("source_name", "")),
            title=str(record.get("title", "")),
            url=str(record.get("url", "")),
            published_at=str(record.get("published_at", "")),
            fetched_at=str(record.get("fetched_at", "")),
            engagement_score=int(record.get("engagement_score", 0)),
            summary=str(record.get("summary", "")),
            topic_hint=str(record.get("topic_hint", "")),
            why_it_matters=str(record.get("why_it_matters", "")),
            why_engaged=str(record.get("why_engaged", "")),
            status=str(record.get("status", "new")),
            notes=str(record.get("notes", "")),
        )


@dataclass(slots=True)
class EditorialTopic:
    topic_id: str
    title: str
    thesis: str
    portugal_angle: str
    audience: str
    source_signal_ids: list[str] = field(default_factory=list)
    urgency_score: int = 0
    status: str = "needs_review"
    editor_notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "EditorialTopic":
        source_signal_ids = record.get("source_signal_ids", [])
        if isinstance(source_signal_ids, str):
            source_signal_ids = [value.strip() for value in source_signal_ids.split(",") if value.strip()]
        return cls(
            topic_id=str(record["topic_id"]),
            title=str(record.get("title", "")),
            thesis=str(record.get("thesis", "")),
            portugal_angle=str(record.get("portugal_angle", "")),
            audience=str(record.get("audience", "")),
            source_signal_ids=[str(value) for value in source_signal_ids],
            urgency_score=int(record.get("urgency_score", 0)),
            status=str(record.get("status", "needs_review")),
            editor_notes=str(record.get("editor_notes", "")),
            created_at=str(record.get("created_at", "")),
        )


@dataclass(slots=True)
class FinalPost:
    post_id: str
    topic_id: str
    channel: str
    title: str
    body: str
    hashtags: str
    image_prompt: str
    source_urls: list[str] = field(default_factory=list)
    image_path: str = ""
    image_variants: dict[str, str] = field(default_factory=dict)
    image_status: str = "needs_review"
    editor_notes: str = ""
    status: str = "needs_final_review"
    scheduled_time: str = ""
    buffer_post_id: str = ""
    published_url: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "FinalPost":
        source_urls = record.get("source_urls", [])
        if isinstance(source_urls, str):
            source_urls = [value.strip() for value in source_urls.split("|") if value.strip()]
        return cls(
            post_id=str(record["post_id"]),
            topic_id=str(record.get("topic_id", "")),
            channel=str(record.get("channel", "")),
            title=str(record.get("title", "")),
            body=str(record.get("body", "")),
            hashtags=str(record.get("hashtags", "")),
            image_prompt=str(record.get("image_prompt", "")),
            source_urls=[str(value) for value in source_urls],
            image_path=str(record.get("image_path", "")),
            image_variants={
                str(key): str(value)
                for key, value in dict(record.get("image_variants", {}) or {}).items()
                if value
            },
            image_status=str(record.get("image_status", "needs_review")),
            editor_notes=str(record.get("editor_notes", "")),
            status=str(record.get("status", "needs_final_review")),
            scheduled_time=str(record.get("scheduled_time", "")),
            buffer_post_id=str(record.get("buffer_post_id", "")),
            published_url=str(record.get("published_url", "")),
            created_at=str(record.get("created_at", "")),
        )


@dataclass(slots=True)
class NewsletterIssue:
    issue_id: str
    title: str
    subject: str
    preheader: str
    intro: str
    html: str
    text: str
    item_ids: list[str] = field(default_factory=list)
    status: str = "draft"
    send_at: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "NewsletterIssue":
        item_ids = record.get("item_ids", [])
        if isinstance(item_ids, str):
            item_ids = [value.strip() for value in item_ids.split("|") if value.strip()]
        return cls(
            issue_id=str(record["issue_id"]),
            title=str(record.get("title", "")),
            subject=str(record.get("subject", "")),
            preheader=str(record.get("preheader", "")),
            intro=str(record.get("intro", "")),
            html=str(record.get("html", "")),
            text=str(record.get("text", "")),
            item_ids=[str(value) for value in item_ids],
            status=str(record.get("status", "draft")),
            send_at=str(record.get("send_at", "")),
            created_at=str(record.get("created_at", "")),
        )
