from __future__ import annotations

import json
import os
from pathlib import Path


REQUIRED_SCHEDULE_CHANNELS = {"instagram", "linkedin", "site", "x"}


def load_channel_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def disabled_channels(config: dict | None, *, include_env: bool = True) -> set[str]:
    disabled = {
        str(channel).strip().casefold()
        for channel in (config or {}).get("disabled_channels", [])
        if str(channel).strip()
    }
    if include_env and os.getenv("PTIA_HIDE_X", "").strip().casefold() in {"1", "true", "yes", "on"}:
        disabled.add("x")
    return disabled


def channel_enabled(config: dict | None, channel: str) -> bool:
    return channel.strip().casefold() not in disabled_channels(config)


def expected_schedule_channels(config: dict | None = None) -> set[str]:
    return REQUIRED_SCHEDULE_CHANNELS - disabled_channels(config)


def buffer_channel_id_for(post_channel: str, config: dict) -> str:
    channels = config.get("channels", {})
    if post_channel == "linkedin":
        return str(channels.get("linkedin") or channels.get("linkedin_page") or "")
    if post_channel == "instagram":
        return str(channels.get("instagram") or "")
    if post_channel == "x":
        return str(channels.get("x") or channels.get("twitter") or "")
    return ""
