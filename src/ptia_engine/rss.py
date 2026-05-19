from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from ptia_engine.dedupe import content_hash, normalize_url, stable_hash
from ptia_engine.http_client import urlopen_direct
from ptia_engine.models import RawArticle, Source, utc_now_iso


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def strip_html(value: str, max_length: int = 700) -> str:
    if not value:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html.unescape(value))
    text = re.sub(r"\s+", " ", stripper.text()).strip()
    text = repair_mojibake(text)
    return text[:max_length].strip()


def repair_mojibake(value: str) -> str:
    """Repair common UTF-8-as-Latin-1 artifacts without touching normal text."""
    if not value or not any(marker in value for marker in ("Ã", "Â", "â")):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value
    if repaired.count("\ufffd") > value.count("\ufffd"):
        return value
    return repaired


def sanitize_xml(feed_bytes: bytes) -> str:
    text = feed_bytes.decode("utf-8", errors="replace")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(
        r"&(?!(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);)",
        "&amp;",
        text,
    )
    return text


def fetch_feed(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PTIAContentEngine/0.1 (+https://ptia.pt; editorial curation)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen_direct(request, timeout=timeout) as response:
        return response.read()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(element: ET.Element, *names: str) -> str:
    wanted = set(names)
    for child in element:
        if _local_name(child.tag) in wanted and child.text:
            return child.text.strip()
    return ""


def _first_link(element: ET.Element) -> str:
    link_text = _child_text(element, "link")
    if link_text:
        return link_text
    for child in element:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
    return ""


def _first_image(element: ET.Element) -> str:
    for child in element.iter():
        name = _local_name(child.tag)
        if name in {"thumbnail", "content"}:
            url = child.attrib.get("url", "").strip()
            medium = child.attrib.get("medium", "")
            if url and (name == "thumbnail" or medium == "image"):
                return url
        if name == "enclosure":
            url = child.attrib.get("url", "").strip()
            content_type = child.attrib.get("type", "")
            if url and content_type.startswith("image/"):
                return url
    return ""


def _parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        return value


def _iter_entries(root: ET.Element) -> list[ET.Element]:
    if _local_name(root.tag) == "rss":
        channel = next((child for child in root if _local_name(child.tag) == "channel"), None)
        if channel is None:
            return []
        return [child for child in channel if _local_name(child.tag) == "item"]
    if _local_name(root.tag) == "feed":
        return [child for child in root if _local_name(child.tag) == "entry"]
    return [child for child in root.iter() if _local_name(child.tag) in {"item", "entry"}]


def parse_feed(feed_bytes: bytes, source: Source, fetched_at: str | None = None) -> list[RawArticle]:
    fetched_at = fetched_at or utc_now_iso()
    root = ET.fromstring(sanitize_xml(feed_bytes))
    articles: list[RawArticle] = []
    for entry in _iter_entries(root):
        title = _child_text(entry, "title")
        url = normalize_url(_first_link(entry))
        if not title or not url:
            continue

        summary = (
            _child_text(entry, "description")
            or _child_text(entry, "summary")
            or _child_text(entry, "content")
        )
        author = _child_text(entry, "author", "creator")
        published = (
            _child_text(entry, "pubDate")
            or _child_text(entry, "published")
            or _child_text(entry, "updated")
        )
        excerpt = strip_html(summary)
        c_hash = content_hash(title, excerpt)
        article_key = url or f"{source.source_id}:{title}:{published}"
        articles.append(
            RawArticle(
                article_id=f"art_{stable_hash(article_key)}",
                source_id=source.source_id,
                source_name=source.name,
                title_original=strip_html(title, max_length=260),
                url=url,
                author=strip_html(author, max_length=160),
                published_at=_parse_date(published),
                fetched_at=fetched_at,
                language=source.language,
                country=source.country,
                raw_excerpt=excerpt,
                image_url=_first_image(entry),
                content_hash=c_hash,
            )
        )
    return articles


def fetch_source(source: Source, limit: int = 20) -> list[RawArticle]:
    feed = fetch_feed(source.rss_url)
    return parse_feed(feed, source)[:limit]
