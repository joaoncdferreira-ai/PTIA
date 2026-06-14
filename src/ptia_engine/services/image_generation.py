from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ptia_engine.assets import create_final_post_image
from ptia_engine.dedupe import stable_hash
from ptia_engine.models import FinalPost


@dataclass(frozen=True, slots=True)
class GeneratedEditorialImage:
    path: Path
    provider: str
    model: str
    fallback: bool = False
    warning: str = ""


class EditorialImageGenerator(Protocol):
    def generate(self, post: FinalPost, out_dir: Path) -> GeneratedEditorialImage: ...


class OpenAIEditorialImageGenerator:
    """Generate one image master, with a deterministic local fallback."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        quality: str | None = None,
        client=None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        self.provider = (
            provider if provider is not None else os.getenv("PTIA_IMAGE_PROVIDER", "auto")
        ).strip().lower()
        self.model = (model or os.getenv("PTIA_IMAGE_MODEL", "gpt-image-2")).strip()
        self.quality = (quality or os.getenv("PTIA_IMAGE_QUALITY", "medium")).strip()
        self._client = client

    @property
    def available(self) -> bool:
        return self.provider not in {"off", "none", "template"} and bool(self.api_key or self._client)

    def _fallback(
        self,
        post: FinalPost,
        out_dir: Path,
        warning: str,
    ) -> GeneratedEditorialImage:
        return GeneratedEditorialImage(
            path=create_final_post_image(post, out_dir),
            provider="ptia_template",
            model="deterministic-svg",
            fallback=True,
            warning=warning,
        )

    def generate(self, post: FinalPost, out_dir: Path) -> GeneratedEditorialImage:
        if not self.available:
            return self._fallback(
                post,
                out_dir,
                "Imagem de IA indisponível; aplicado template PTIA.",
            )

        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self._client is None:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            response = self._client.images.generate(
                model=self.model,
                prompt=post.image_prompt,
                size="1536x1024",
                quality=self.quality,
                output_format="jpeg",
                n=1,
            )
            encoded = getattr(response.data[0], "b64_json", "") or ""
            if not encoded:
                raise RuntimeError("a API não devolveu imagem em base64")
            path = out_dir / (
                f"{post.topic_id}_{stable_hash(post.image_prompt + self.model, 10)}.jpg"
            )
            path.write_bytes(base64.b64decode(encoded))
            return GeneratedEditorialImage(path=path, provider="openai", model=self.model)
        except Exception as exc:
            return self._fallback(
                post,
                out_dir,
                f"Falha na imagem de IA ({type(exc).__name__}); aplicado template PTIA.",
            )
