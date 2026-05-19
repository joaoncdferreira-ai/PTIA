from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ptia_engine.models import RawArticle

TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref"}


def normalize_title(title: str) -> str:
    title = title.casefold()
    title = re.sub(r"[^a-z0-9A-ZÀ-ÿ\s]", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        key_l = key.casefold()
        if key_l in TRACKING_KEYS or any(key_l.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        query_items.append((key, value))
    cleaned_query = urlencode(query_items, doseq=True)
    netloc = parts.netloc.casefold()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold(), netloc, path, cleaned_query, ""))


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def content_hash(title: str, excerpt: str = "") -> str:
    return stable_hash(f"{normalize_title(title)}\n{excerpt.strip()}", 24)


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def load_articles(path: Path) -> list[RawArticle]:
    if not path.exists():
        return []
    articles: list[RawArticle] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            articles.append(RawArticle.from_record(json.loads(line)))
    return articles


def append_articles(path: Path, articles: list[RawArticle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for article in articles:
            handle.write(json.dumps(article.to_record(), ensure_ascii=False) + "\n")


def find_duplicate(
    article: RawArticle,
    existing_articles: list[RawArticle],
    title_threshold: float = 0.88,
) -> RawArticle | None:
    normalized_url = normalize_url(article.url)
    for existing in existing_articles:
        if normalized_url and normalize_url(existing.url) == normalized_url:
            return existing
        if article.content_hash and article.content_hash == existing.content_hash:
            return existing
        if title_similarity(article.title_original, existing.title_original) >= title_threshold:
            return existing
    return None
