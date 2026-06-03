from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class PolishProvider(Protocol):
    available: bool

    def polish_final_post(
        self,
        *,
        channel: str,
        title: str,
        body: str,
        hashtags: str,
        source_urls: list[str],
    ): ...


def polish_final_post_copy(
    *,
    channel: str,
    title: str,
    body: str,
    hashtags: str,
    source_urls: list[str],
    provider: PolishProvider,
    apply_editorial_rules: Callable[[str, str, str], tuple[str, str]],
) -> dict:
    if not provider.available:
        return {
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "editor_notes": "PT-PT polish nao aplicado: GEMINI_API_KEY indisponivel.",
        }
    try:
        polished = provider.polish_final_post(
            channel=channel,
            title=title,
            body=body,
            hashtags=hashtags,
            source_urls=source_urls,
        )
    except RuntimeError as exc:
        return {
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "editor_notes": f"PT-PT polish nao aplicado: {exc}",
        }

    final_title, final_body = apply_editorial_rules(
        polished.title or title,
        polished.body or body,
        channel,
    )
    return {
        "title": final_title,
        "body": final_body,
        "hashtags": polished.hashtags if polished.hashtags != "" else hashtags,
        "editor_notes": (
            "PT-PT Editorial Polish aplicado com prompt Gemini. "
            "Evaristo/Gervasio fica pendente de API estavel. "
            f"{polished.rationale}"
        ).strip(),
    }
