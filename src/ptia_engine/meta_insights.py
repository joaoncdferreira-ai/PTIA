from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError

from ptia_engine.http_client import urlopen_direct


META_GRAPH_BASE_URL = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v20.0"
DEFAULT_MEDIA_METRICS = (
    "impressions,reach,likes,comments,saved,shares,total_interactions"
)


class MetaInsightsError(RuntimeError):
    pass


@dataclass(slots=True)
class InstagramMedia:
    id: str
    caption: str = ""
    media_type: str = ""
    media_url: str = ""
    permalink: str = ""
    timestamp: str = ""


@dataclass(slots=True)
class InstagramMediaInsights:
    media_id: str
    permalink: str = ""
    caption: str = ""
    timestamp: str = ""
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    saves: int = 0
    shares: int = 0
    total_interactions: int = 0


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class MetaGraphClient:
    def __init__(
        self,
        *,
        access_token: str | None = None,
        instagram_business_id: str | None = None,
        graph_version: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.access_token = access_token or os.getenv("META_ACCESS_TOKEN", "")
        self.instagram_business_id = instagram_business_id or os.getenv(
            "META_INSTAGRAM_BUSINESS_ID", ""
        )
        self.graph_version = graph_version or os.getenv("META_GRAPH_VERSION", DEFAULT_GRAPH_VERSION)
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.access_token.strip() and self.instagram_business_id.strip())

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.access_token.strip():
            raise MetaInsightsError("META_ACCESS_TOKEN nao esta configurado.")
        params = dict(params or {})
        params["access_token"] = self.access_token
        url = (
            f"{META_GRAPH_BASE_URL}/{self.graph_version}/{path.lstrip('/')}"
            + "?"
            + urllib.parse.urlencode(params)
        )
        request = urllib.request.Request(url, headers={"User-Agent": "PTIA-Engine/1.0"})
        try:
            with urlopen_direct(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise MetaInsightsError(f"Meta Graph API HTTP {exc.code}: {body[:1000]}") from exc

    def recent_media(self, limit: int = 25) -> list[InstagramMedia]:
        if not self.instagram_business_id.strip():
            raise MetaInsightsError("META_INSTAGRAM_BUSINESS_ID nao esta configurado.")
        payload = self._get(
            f"{self.instagram_business_id}/media",
            {
                "fields": "id,caption,media_type,media_url,permalink,timestamp",
                "limit": max(1, min(limit, 100)),
            },
        )
        return [
            InstagramMedia(
                id=str(item.get("id", "")),
                caption=str(item.get("caption", "")),
                media_type=str(item.get("media_type", "")),
                media_url=str(item.get("media_url", "")),
                permalink=str(item.get("permalink", "")),
                timestamp=str(item.get("timestamp", "")),
            )
            for item in payload.get("data", [])
            if item.get("id")
        ]

    def media_insights(
        self,
        media_id: str,
        *,
        metrics: str = DEFAULT_MEDIA_METRICS,
    ) -> dict[str, int]:
        payload = self._get(f"{media_id}/insights", {"metric": metrics})
        result: dict[str, int] = {}
        for item in payload.get("data", []):
            values = item.get("values") or []
            value = values[0].get("value") if values and isinstance(values[0], dict) else 0
            result[str(item.get("name", ""))] = _int_value(value)
        return result

    def recent_media_insights(self, limit: int = 25) -> list[InstagramMediaInsights]:
        rows: list[InstagramMediaInsights] = []
        for media in self.recent_media(limit=limit):
            metrics = self.media_insights(media.id)
            rows.append(
                InstagramMediaInsights(
                    media_id=media.id,
                    permalink=media.permalink,
                    caption=media.caption,
                    timestamp=media.timestamp,
                    impressions=metrics.get("impressions", 0),
                    reach=metrics.get("reach", 0),
                    likes=metrics.get("likes", 0),
                    comments=metrics.get("comments", 0),
                    saves=metrics.get("saved", metrics.get("saves", 0)),
                    shares=metrics.get("shares", 0),
                    total_interactions=metrics.get("total_interactions", 0),
                )
            )
        return rows
