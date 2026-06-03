from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import quote

from ptia_engine.models import FinalPost


DEFAULT_PUBLIC_ASSET_BASE_URL = "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site"


def image_path_for_channel(post: FinalPost) -> str:
    variants = post.image_variants or {}
    return str(variants.get(post.channel) or post.image_path or "")


def _env_file_value(repo_root: Path, keys: set[str]) -> str:
    env_path = repo_root / ".env.local"
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in keys:
            configured = value.strip().strip('"').strip("'")
            if configured:
                return configured
    return ""


def public_asset_base_url(repo_root: Path | None = None) -> str:
    configured = (os.getenv("PTIA_PUBLIC_ASSET_BASE_URL") or os.getenv("PTIA_PUBLIC_SITE_URL") or "").strip()
    if not configured and repo_root is not None:
        configured = _env_file_value(repo_root, {"PTIA_PUBLIC_ASSET_BASE_URL", "PTIA_PUBLIC_SITE_URL"})
    return (configured or DEFAULT_PUBLIC_ASSET_BASE_URL).rstrip("/")


def public_image_url(post: FinalPost, repo_root: Path | None = None, base_url: str = "") -> str:
    image_path = image_path_for_channel(post)
    if not image_path:
        return ""
    if image_path.startswith(("https://", "http://")):
        return image_path
    resolved_base_url = (base_url or public_asset_base_url(repo_root)).rstrip("/")
    return f"{resolved_base_url}/assets/final/{quote(Path(image_path).name)}"


def copy_image_to_public_site_assets(site_dir: Path, post: FinalPost) -> str:
    image_path = image_path_for_channel(post)
    if not image_path or image_path.startswith(("https://", "http://")):
        return image_path
    source = Path(image_path)
    if not source.exists():
        return ""
    target_dir = site_dir / "assets" / "final"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
        shutil.copy2(source, target)
    return str(target)
