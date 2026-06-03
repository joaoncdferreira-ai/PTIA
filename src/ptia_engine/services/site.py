from __future__ import annotations

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


def clean_article_body(body: str) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", body or "")
        if paragraph.strip()
    ]
    return "\n\n".join(
        paragraph
        for paragraph in paragraphs
        if not re.match(r"^fonte(?:\s+original)?\s*:", paragraph, flags=re.IGNORECASE)
    ).strip()


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
