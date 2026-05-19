from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError

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


class BufferAPIError(RuntimeError):
    pass


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

    def create_scheduled_post(
        self,
        *,
        channel_id: str,
        text: str,
        due_at: str,
        image_url: str = "",
        post_type: str = "",
        scheduling_type: str = "automatic",
    ) -> BufferPostResult:
        input_payload: dict[str, Any] = {
            "text": text,
            "channelId": channel_id,
            "schedulingType": scheduling_type,
            "mode": "customScheduled",
            "dueAt": due_at,
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
            "dueAt": due_at,
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
