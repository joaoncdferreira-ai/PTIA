from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from ptia_engine.http_client import urlopen_direct


BUFFER_GRAPHQL_URL = "https://api.buffer.com"


@dataclass(slots=True)
class BufferOrganization:
    id: str
    name: str


@dataclass(slots=True)
class BufferChannel:
    id: str
    name: str
    service: str
    display_name: str = ""


@dataclass(slots=True)
class BufferPostResult:
    id: str
    text: str = ""
    due_at: str = ""


@dataclass(slots=True)
class BufferPostDetails:
    id: str
    text: str = ""
    status: str = ""
    due_at: str = ""
    channel_id: str = ""
    channel_service: str = ""
    external_link: str = ""
    asset_sources: list[str] | None = None


class BufferAPIError(RuntimeError):
    pass


def _buffer_due_at(due_at: str) -> str:
    raw = due_at.strip()
    if not raw:
        return raw
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        local_tz = ZoneInfo(os.getenv("BUFFER_LOCAL_TIMEZONE", "Europe/Lisbon"))
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class BufferClient:
    def __init__(self, api_key: str | None = None, timeout_seconds: int = 30) -> None:
        self.api_key = api_key or os.getenv("BUFFER_API_KEY", "")
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.api_key.strip())

    def account_organizations(self) -> list[BufferOrganization]:
        payload = self._graphql(
            """
            query BufferAccount {
              account {
                organizations {
                  id
                  name
                }
              }
            }
            """
        )
        organizations = payload.get("data", {}).get("account", {}).get("organizations", [])
        return [
            BufferOrganization(id=str(item.get("id", "")), name=str(item.get("name", "")))
            for item in organizations
            if item.get("id")
        ]

    def channels(self, organization_id: str) -> list[BufferChannel]:
        payload = self._graphql(
            """
            query BufferChannels($organizationId: OrganizationId!) {
              channels(input: { organizationId: $organizationId }) {
                id
                name
                displayName
                service
              }
            }
            """,
            {"organizationId": organization_id},
        )
        channels = payload.get("data", {}).get("channels", [])
        return [
            BufferChannel(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                display_name=str(item.get("displayName", "")),
                service=str(item.get("service", "")),
            )
            for item in channels
            if item.get("id")
        ]

    def discover_channels(self) -> tuple[list[BufferOrganization], list[BufferChannel]]:
        organizations = self.account_organizations()
        channels: list[BufferChannel] = []
        for organization in organizations:
            channels.extend(self.channels(organization.id))
        return organizations, channels

    def get_post(self, post_id: str) -> BufferPostDetails:
        payload = self._graphql(
            """
            query BufferPost($input: PostInput!) {
              post(input: $input) {
                id
                status
                dueAt
                text
                channelId
                channelService
                externalLink
                assets {
                  id
                  type
                  source
                  thumbnail
                  mimeType
                }
              }
            }
            """,
            {"input": {"id": post_id}},
        )
        post = payload.get("data", {}).get("post") or {}
        if not post.get("id"):
            raise BufferAPIError(f"Buffer did not return a post: {payload}")
        assets = post.get("assets") or []
        return BufferPostDetails(
            id=str(post.get("id", "")),
            text=str(post.get("text", "")),
            status=str(post.get("status", "")),
            due_at=str(post.get("dueAt", "")),
            channel_id=str(post.get("channelId", "")),
            channel_service=str(post.get("channelService", "")),
            external_link=str(post.get("externalLink", "")),
            asset_sources=[
                str(asset.get("source") or asset.get("thumbnail") or "")
                for asset in assets
                if asset.get("source") or asset.get("thumbnail")
            ],
        )

    def create_scheduled_post(
        self,
        *,
        channel_id: str,
        text: str,
        due_at: str,
        image_url: str = "",
        image_urls: list[str] | None = None,
        post_type: str = "",
        scheduling_type: str = "automatic",
        channel_service: str = "",
        first_comment: str = "",
    ) -> BufferPostResult:
        input_payload: dict[str, Any] = {
            "text": text,
            "channelId": channel_id,
            "schedulingType": scheduling_type,
            "mode": "customScheduled",
            "dueAt": _buffer_due_at(due_at),
        }
        metadata = {}
        if post_type or (channel_service == "instagram" and first_comment):
            metadata["instagram"] = {
                "type": post_type or "post",
                "shouldShareToFeed": True,
            }
            if first_comment:
                metadata["instagram"]["firstComment"] = first_comment
        elif channel_service == "linkedin" and first_comment:
            metadata["linkedin"] = {
                "firstComment": first_comment
            }
        elif channel_service == "facebook" and first_comment:
            metadata["facebook"] = {
                "firstComment": first_comment
            }
        if metadata:
            input_payload["metadata"] = metadata
        asset_urls = [url for url in (image_urls or []) if url]
        if image_url and not asset_urls:
            asset_urls = [image_url]
        if asset_urls:
            input_payload["assets"] = [{"image": {"url": url}} for url in asset_urls]
        payload = self._graphql(
            """
            mutation CreateScheduledPost($input: CreatePostInput!) {
              createPost(input: $input) {
                ... on PostActionSuccess {
                  post {
                    id
                    text
                    dueAt
                  }
                }
                ... on MutationError {
                  message
                }
              }
            }
            """,
            {"input": input_payload},
        )
        result = payload.get("data", {}).get("createPost", {})
        if result.get("message"):
            raise BufferAPIError(str(result["message"]))
        post = result.get("post") or {}
        if not post.get("id"):
            raise BufferAPIError(f"Buffer did not return a post id: {payload}")
        return BufferPostResult(
            id=str(post.get("id", "")),
            text=str(post.get("text", "")),
            due_at=str(post.get("dueAt", "")),
        )

    def edit_scheduled_post(
        self,
        *,
        post_id: str,
        text: str,
        due_at: str,
        image_url: str = "",
        post_type: str = "",
        scheduling_type: str = "automatic",
    ) -> BufferPostResult:
        input_payload: dict[str, Any] = {
            "id": post_id,
            "text": text,
            "schedulingType": scheduling_type,
            "mode": "customScheduled",
            "dueAt": _buffer_due_at(due_at),
        }
        if post_type:
            input_payload["metadata"] = {
                "instagram": {
                    "type": post_type,
                    "shouldShareToFeed": True,
                }
            }
        if image_url:
            input_payload["assets"] = [{"image": {"url": image_url}}]
        payload = self._graphql(
            """
            mutation EditScheduledPost($input: EditPostInput!) {
              editPost(input: $input) {
                ... on PostActionSuccess {
                  post {
                    id
                    text
                    dueAt
                  }
                }
                ... on MutationError {
                  message
                }
              }
            }
            """,
            {"input": input_payload},
        )
        result = payload.get("data", {}).get("editPost", {})
        if result.get("message"):
            raise BufferAPIError(str(result["message"]))
        post = result.get("post") or {}
        if not post.get("id"):
            raise BufferAPIError(f"Buffer did not return a post id: {payload}")
        return BufferPostResult(
            id=str(post.get("id", "")),
            text=str(post.get("text", "")),
            due_at=str(post.get("dueAt", "")),
        )

    def delete_post(self, post_id: str) -> bool:
        payload = self._graphql(
            """
            mutation DeletePost($input: DeletePostInput!) {
              deletePost(input: $input) {
                ... on DeletePostSuccess {
                  id
                }
                ... on VoidMutationError {
                  message
                }
              }
            }
            """,
            {"input": {"id": post_id}},
        )
        result = payload.get("data", {}).get("deletePost", {})
        if result.get("message"):
            raise BufferAPIError(str(result["message"]))
        return bool(result.get("id", post_id))

    def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.available:
            raise BufferAPIError("BUFFER_API_KEY nao esta configurada.")
        request = urllib.request.Request(
            BUFFER_GRAPHQL_URL,
            data=json.dumps({"query": query, "variables": variables or {}}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urlopen_direct(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BufferAPIError(f"Buffer API HTTP {exc.code}: {body[:1000]}") from exc
        if payload.get("errors"):
            raise BufferAPIError(json.dumps(payload["errors"], ensure_ascii=False))
        return payload
