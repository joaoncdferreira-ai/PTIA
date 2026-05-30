from __future__ import annotations

import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["PTIA_PUBLIC_ASSET_BASE_URL"] = "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site"

import ptia_engine.dashboard as dashboard_module  # noqa: E402
from ptia_engine.dashboard import (  # noqa: E402
    DashboardState,
    _channel_enabled,
    _copy_image_to_public_site_assets,
    _public_image_url_for_buffer,
    _public_url_available,
    _publish_site_assets_to_git,
    _schedule_final_package,
    _validate_final_package_copy,
    load_final_posts,
)


PLAN = [
    ("topic_0af679613b90482820", "2026-05-26T09:00:00+01:00"),
    ("topic_05b65bfd50e18b4cd1", "2026-05-26T13:00:00+01:00"),
    ("topic_dd001b4c4f0867daf7", "2026-05-26T16:00:00+01:00"),
    ("topic_bde638b1a57a8df8b8", "2026-05-26T21:00:00+01:00"),
]


def main() -> None:
    state = DashboardState(ROOT / "data")
    original_sync_static_site_feed = dashboard_module._sync_static_site_feed
    dashboard_module._sync_static_site_feed = lambda sync_state: original_sync_static_site_feed(
        sync_state,
        deploy=False,
    )

    backup_path = state.final_posts_path.with_name(
        f"final_posts.jsonl.bak_before_schedule_20260526_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(state.final_posts_path, backup_path)
    print(f"Backup: {backup_path}")

    posts = load_final_posts(state.final_posts_path)
    relevant = [
        post
        for post in posts
        if post.status in {"approved_for_schedule", "scheduled"}
        and post.channel in {"instagram", "linkedin", "site"}
        and _channel_enabled(state, post.channel)
    ]
    by_topic = {topic_id: [] for topic_id, _ in PLAN}
    for post in relevant:
        if post.topic_id in by_topic:
            by_topic[post.topic_id].append(post)

    counts = Counter(post.topic_id for post in relevant)
    print(f"Relevant enabled posts: {len(relevant)}")
    for topic_id, scheduled_time in PLAN:
        package = sorted(by_topic[topic_id], key=lambda post: post.channel)
        channels = ",".join(f"{post.channel}:{post.status}" for post in package)
        print(f"Plan {scheduled_time} {topic_id}: {channels}")
        if len(package) != 3:
            raise SystemExit(f"Pacote incompleto para {topic_id}: {counts[topic_id]} posts")
        _validate_final_package_copy(package)
        for post in package:
            if post.status == "scheduled" and post.scheduled_time != scheduled_time:
                raise SystemExit(f"Hora errada em post ja scheduled: {post.post_id} {post.scheduled_time}")
        for post in package:
            if post.channel in {"instagram", "x"}:
                image_path = str((post.image_variants or {}).get(post.channel) or post.image_path or "")
                if "ptia_v7" not in image_path:
                    raise SystemExit(f"Imagem sem overlay v7: {post.post_id} {image_path}")

    social_posts = [
        post
        for topic_id, _ in PLAN
        for post in by_topic[topic_id]
        if post.channel in {"instagram", "linkedin"}
    ]
    public_asset_paths = [_copy_image_to_public_site_assets(state, post) for post in social_posts]
    _publish_site_assets_to_git(state, [path for path in public_asset_paths if path])
    missing = list(social_posts)
    for attempt in range(12):
        missing = [post for post in missing if not _public_url_available(_public_image_url_for_buffer(post, state))]
        if not missing:
            break
        print(f"Aguardar assets publicos: tentativa {attempt + 1}, em falta {len(missing)}")
        time.sleep(3)
    if missing:
        first = missing[0]
        raise SystemExit(f"Asset ainda sem URL publico: {first.post_id} {_public_image_url_for_buffer(first, state)}")

    for topic_id, scheduled_time in PLAN:
        package = by_topic[topic_id]
        if all(post.status == "scheduled" for post in package):
            print(f"Skip already scheduled {scheduled_time} {topic_id}")
            continue
        updated = _schedule_final_package(state, topic_id, scheduled_time)
        print(f"Scheduled {scheduled_time} {topic_id}:")
        for post in sorted(updated, key=lambda item: item.channel):
            print(f"  {post.channel}: {post.post_id} {post.buffer_post_id or 'site-local'}")

    scheduled = [
        post
        for post in load_final_posts(state.final_posts_path)
        if post.topic_id in {topic_id for topic_id, _ in PLAN} and post.status == "scheduled"
    ]
    print(f"Scheduled total for plan: {len(scheduled)}")
    for post in sorted(scheduled, key=lambda item: (item.scheduled_time or "", item.topic_id, item.channel)):
        print(f"VERIFY {post.scheduled_time} {post.channel} {post.post_id} {post.buffer_post_id or 'site-local'}")


if __name__ == "__main__":
    main()
