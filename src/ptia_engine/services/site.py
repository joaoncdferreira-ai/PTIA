from __future__ import annotations

import html
import os
import re
import unicodedata
from datetime import datetime, timezone

from ptia_engine.models import FinalPost


def site_public_base_url() -> str:
    return (os.getenv("PTIA_PUBLIC_SITE_URL") or "https://ptia.pt").rstrip("/")


def slugify_site_value(value: str, *, fallback: str = "artigo") -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or fallback


def article_url_for_site_post(post: FinalPost) -> str:
    slug = slugify_site_value(post.title)
    suffix = post.post_id.replace("post_", "")
    return f"artigos/{slug}-{suffix}"


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_URL_ONLY_RE = re.compile(r"^(?:https?://|www\.)\S+\.?$", flags=re.IGNORECASE)


def clean_public_text(value: str) -> str:
    """Remove internal/editorial markup before copy reaches public surfaces."""
    clean = html.unescape(value or "")
    clean = _MARKDOWN_LINK_RE.sub(r"\1", clean)
    clean = re.sub(
        r"<\s*(?:i|em|b|strong)\s*>(.*?)<\s*/\s*(?:i|em|b|strong)\s*>",
        r"\1",
        clean,
        flags=re.IGNORECASE | re.DOTALL,
    )
    clean = _HTML_TAG_RE.sub("", clean)
    clean = clean.replace("\u00a0", " ")
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def _is_url_only_paragraph(paragraph: str) -> bool:
    return bool(_URL_ONLY_RE.match(clean_public_text(paragraph).strip()))


def clean_article_body(body: str) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", body or "")
        if paragraph.strip()
    ]
    clean_paragraphs = []
    for paragraph in paragraphs:
        if re.match(r"^fonte(?:\s+original)?\s*:", paragraph, flags=re.IGNORECASE):
            continue
        if _is_url_only_paragraph(paragraph):
            continue
        clean = clean_public_text(paragraph)
        if clean and not _is_url_only_paragraph(clean):
            clean_paragraphs.append(clean)
    return "\n\n".join(clean_paragraphs).strip()


def excerpt(text: str, *, length: int = 165) -> str:
    clean = re.sub(r"\s+", " ", clean_article_body(text)).strip()
    if len(clean) <= length:
        return clean
    return clean[: length - 1].rsplit(" ", 1)[0].rstrip(" .,:;") + "..."


def is_public_site_post(post: dict) -> bool:
    published_at = str(post.get("published_at") or "")
    if not published_at:
        return True
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except ValueError:
        return True
