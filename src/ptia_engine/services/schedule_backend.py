from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ptia_engine.models import FinalPost
from ptia_engine.scheduler import ScheduleAction, ScheduleActionResult
from ptia_engine.storage import load_final_posts


@dataclass(frozen=True, slots=True)
class ScheduleCapabilities:
    publish_assets: bool = False
    send_buffer: bool = False
    write_site_feed: bool = False


def required_capabilities_for_actions(actions: list[ScheduleAction]) -> set[str]:
    required: set[str] = set()
    for action in actions:
        if action.status == "skipped":
            continue
        if action.kind == "prepare_public_assets":
            required.add("publish_assets")
        elif action.kind in {"schedule_buffer_post", "schedule_instagram_carousel"}:
            required.add("send_buffer")
        elif action.kind in {"schedule_site_post", "sync_site_feed"}:
            required.add("write_site_feed")
    return required


def missing_capabilities(actions: list[ScheduleAction], capabilities: ScheduleCapabilities) -> list[str]:
    required = required_capabilities_for_actions(actions)
    missing = []
    if "publish_assets" in required and not capabilities.publish_assets:
        missing.append("publish_assets")
    if "send_buffer" in required and not capabilities.send_buffer:
        missing.append("send_buffer")
    if "write_site_feed" in required and not capabilities.write_site_feed:
        missing.append("write_site_feed")
    return missing


def _posts_for_action(posts_path: Path, action: ScheduleAction) -> list[FinalPost]:
    posts_by_id = {post.post_id: post for post in load_final_posts(posts_path)}
    return [posts_by_id[post_id] for post_id in action.post_ids if post_id in posts_by_id]


class DashboardScheduleBackend:
    """Real scheduling adapter around the existing dashboard operations.

    This class is intentionally thin. It converts scheduler actions into the
    existing operational functions, and is only meant to be used behind explicit
    CLI confirmation and capability flags.
    """

    def __init__(self, *, repo_root: Path, data_dir: Path, capabilities: ScheduleCapabilities) -> None:
        self.repo_root = repo_root
        self.data_dir = data_dir
        self.capabilities = capabilities

    @property
    def posts_path(self) -> Path:
        return self.data_dir / "final_posts.jsonl"

    def _state(self):
        from ptia_engine.dashboard import DashboardState

        return DashboardState(self.data_dir)

    def _blocked(self, action: ScheduleAction, capability: str) -> ScheduleActionResult:
        return ScheduleActionResult(
            action_id=action.action_id,
            kind=action.kind,
            status="blocked",
            message=f"Missing explicit capability: {capability}.",
        )

    def prepare_public_assets(self, action: ScheduleAction) -> ScheduleActionResult:
        if not self.capabilities.publish_assets:
            return self._blocked(action, "publish_assets")
        from ptia_engine.dashboard import _ensure_public_images_for_buffer

        _ensure_public_images_for_buffer(self._state(), _posts_for_action(self.posts_path, action))
        return ScheduleActionResult(action.action_id, action.kind, "ok", message="Public assets prepared.")

    def schedule_buffer_post(self, action: ScheduleAction) -> ScheduleActionResult:
        if not self.capabilities.send_buffer:
            return self._blocked(action, "send_buffer")
        from ptia_engine.dashboard import _schedule_post_in_buffer

        post_id = action.post_ids[0]
        updated = _schedule_post_in_buffer(self._state(), post_id, action.scheduled_time)
        return ScheduleActionResult(
            action.action_id,
            action.kind,
            "ok",
            external_id=updated.buffer_post_id,
            message=f"Scheduled {updated.channel} post {updated.post_id}.",
        )

    def schedule_instagram_carousel(self, action: ScheduleAction) -> ScheduleActionResult:
        if not self.capabilities.send_buffer:
            return self._blocked(action, "send_buffer")
        from ptia_engine.buffer_api import BufferClient
        from ptia_engine.dashboard import _buffer_channel_id_for, _discover_buffer_channels, _load_buffer_channels
        from ptia_engine.editorial_board import update_final_post_copy, update_final_post_status

        state = self._state()
        config = _load_buffer_channels(state.buffer_channels_path)
        channel_id = _buffer_channel_id_for("instagram", config)
        if not channel_id:
            config = _discover_buffer_channels(state.buffer_channels_path)
            channel_id = _buffer_channel_id_for("instagram", config)
        if not channel_id:
            raise ValueError("Buffer nao tem canal configurado para instagram.")

        buffer_post = BufferClient().create_scheduled_post(
            channel_id=channel_id,
            text=str(action.payload.get("caption", "")),
            due_at=action.scheduled_time,
            image_urls=[str(url) for url in action.payload.get("image_urls", []) if url],
            post_type="post",
        )
        for post_id in action.post_ids:
            post = update_final_post_status(
                self.posts_path,
                post_id=post_id,
                status="scheduled",
                scheduled_time=action.scheduled_time,
                buffer_post_id=buffer_post.id,
            )
            update_final_post_copy(
                self.posts_path,
                post.post_id,
                notes=f"[scheduler] Agendado como parte do carrossel Instagram {buffer_post.id}.",
            )
        return ScheduleActionResult(
            action.action_id,
            action.kind,
            "ok",
            external_id=buffer_post.id,
            message=f"Scheduled Instagram carousel with {len(action.post_ids)} slides.",
        )

    def schedule_site_post(self, action: ScheduleAction) -> ScheduleActionResult:
        if not self.capabilities.write_site_feed:
            return self._blocked(action, "write_site_feed")
        from ptia_engine.dashboard import _copy_image_to_public_site_assets, _validate_final_post_copy
        from ptia_engine.editorial_board import update_final_post_status

        post_id = action.post_ids[0]
        posts = _posts_for_action(self.posts_path, action)
        if not posts:
            raise ValueError(f"Final post not found: {post_id}")
        post = posts[0]
        _validate_final_post_copy(post)
        _copy_image_to_public_site_assets(self._state(), post)
        updated = update_final_post_status(
            self.posts_path,
            post_id,
            "scheduled",
            scheduled_time=action.scheduled_time,
        )
        return ScheduleActionResult(
            action.action_id,
            action.kind,
            "ok",
            external_id=updated.published_url or updated.post_id,
            message=f"Scheduled site post {updated.post_id}.",
        )

    def sync_site_feed(self, action: ScheduleAction) -> ScheduleActionResult:
        if not self.capabilities.write_site_feed:
            return self._blocked(action, "write_site_feed")
        from ptia_engine.dashboard import _sync_static_site_feed

        _sync_static_site_feed(self._state(), deploy=False)
        return ScheduleActionResult(action.action_id, action.kind, "ok", message="Static site feed synced.")
