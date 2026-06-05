from __future__ import annotations

import re


def x_post_body(summary: str, why_it_matters: str, source_line: str, hashtags: str) -> str:
    copy = re.sub(
        r"\s+",
        " ",
        " ".join(part.strip() for part in (summary, why_it_matters) if part.strip()),
    ).strip()
    suffix = f"\n\n{source_line}"
    final_suffix = f"{suffix}\n\n{hashtags}" if hashtags else suffix
    max_copy = max(72, 280 - len(final_suffix))
    if len(copy) > max_copy:
        trimmed = copy[: max_copy - 3].rsplit(" ", 1)[0].rstrip(" .,:;")
        copy = f"{trimmed or copy[: max_copy - 3].rstrip()}..."
    return f"{copy}{suffix}".strip()


def fit_x_post_text(body: str, hashtags: str = "", source_urls: list[str] | None = None) -> str:
    clean = re.sub(r"(?im)^\s*(?:\*\*)?Fonte(?:s| original)?(?:\*\*)?\s*:.*$", "", body).strip()
    clean = re.sub(r"https?://\S+", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    # Explicitly removed source_url from X posts to improve reach/avoid bot flag
    suffix_parts = [part for part in (hashtags,) if part]
    suffix = ("\n\n" + "\n\n".join(suffix_parts)) if suffix_parts else ""
    limit = 280 - x_weighted_len(suffix)
    if x_weighted_len(clean) > limit:
        clean = trim_x_weighted(clean, max(0, limit - 1))
    return f"{clean}{suffix}".strip()


def assert_x_post_ready(text: str, image_url: str = "") -> None:
    issues = x_post_validation_issues(text, image_url)
    if issues:
        raise ValueError("X post bloqueado: " + "; ".join(issues))


def x_post_validation_issues(text: str, image_url: str = "") -> list[str]:
    issues: list[str] = []
    clean = text or ""
    if not clean.strip():
        issues.append("texto vazio")
    if x_weighted_len(clean) > 280:
        issues.append(f"texto acima de 280 caracteres X ({x_weighted_len(clean)})")
    if "..." in clean or "\u2026" in clean or "\u00e2\u20ac\u00a6" in clean:
        issues.append("texto truncado com reticencias")
    # Strip URLs to avoid false positives on parameters like ?utm_source
    text_no_urls = re.sub(r"https?://\S+", "", clean)
    if "\ufffd" in text_no_urls or re.search(r"[A-Za-z\u00c0-\u00ff]\?[A-Za-z\u00c0-\u00ff]", text_no_urls):
        issues.append("acentos possivelmente corrompidos")
    if "#" not in clean:
        issues.append("sem hashtags")
    if not image_url.strip():
        issues.append("sem imagem publica")
    return issues


def x_weighted_len(text: str) -> int:
    """Approximate X length: each URL is shortened to a fixed t.co weight."""
    normalised = re.sub(r"https?://\S+", "x" * 23, text or "")
    return len(normalised)


def trim_x_weighted(text: str, limit: int) -> str:
    words = re.sub(r"\s+", " ", text or "").strip().split()
    kept: list[str] = []
    for word in words:
        candidate = " ".join([*kept, word]).strip()
        if x_weighted_len(candidate) > limit:
            break
        kept.append(word)
    trimmed = " ".join(kept).rstrip(" .,:;")
    if not trimmed:
        return ""
    ending = "." if not trimmed.endswith((".", "?", "!")) else ""
    return f"{trimmed}{ending}"
