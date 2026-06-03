from ptia_engine.storage import load_final_posts
from ptia_engine.editorial_board import update_final_post_status
from ptia_engine.routes.common import to_dict

def handle_final_image(handler, payload):
    from ptia_engine.dashboard import _generate_final_image
    post = _generate_final_image(
        handler.state,
        post_id=str(payload["post_id"]),
        feedback=str(payload.get("feedback", "")),
    )
    handler._send_json({"ok": True, "post": to_dict(post)})

def handle_upload_final_image(handler, payload):
    from ptia_engine.dashboard import _upload_final_image
    post = _upload_final_image(
        handler.state,
        post_id=str(payload["post_id"]),
        filename=str(payload.get("filename", "")),
        data_url=str(payload.get("data_url", "")),
    )
    handler._send_json({"ok": True, "post": to_dict(post)})

def handle_final_image_status(handler, payload):
    posts = {post.post_id: post for post in load_final_posts(handler.state.final_posts_path)}
    post_id = str(payload["post_id"])
    current = posts.get(post_id)
    if not current:
        raise ValueError(f"Final post not found: {post_id}")
    post = update_final_post_status(
        handler.state.final_posts_path,
        post_id=post_id,
        status=current.status,
        image_status=str(payload["image_status"]),
    )
    handler._send_json({"ok": True, "post": to_dict(post)})

def handle_image_prompt(handler, payload):
    from ptia_engine.dashboard import _image_prompt_group_for_channel, _high_quality_image_prompt, _channel_enabled
    post_id = str(payload["post_id"])
    posts = {post.post_id: post for post in load_final_posts(handler.state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
    group = str(payload.get("group", "")).strip()
    if group not in {"instagram_x", "linkedin_site"}:
        group = _image_prompt_group_for_channel(post.channel)
    handler._send_json(
        {
            "ok": True,
            "prompt": _high_quality_image_prompt(
                post.title,
                post.body,
                group=group,
                visual_title=str(payload.get("visual_title", "")),
                include_x=_channel_enabled(handler.state, "x"),
            ),
        }
    )

def handle_apply_visual_title(handler, payload):
    from ptia_engine.dashboard import _apply_visual_title_to_topic_package
    posts = _apply_visual_title_to_topic_package(
        handler.state,
        post_id=str(payload["post_id"]),
        visual_title=str(payload.get("visual_title", "")),
    )
    handler._send_json({"ok": True, "posts": [to_dict(post) for post in posts]})

def handle_suggest_image_titles(handler, payload):
    post_id = str(payload["post_id"])
    posts = {post.post_id: post for post in load_final_posts(handler.state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
        
    from ptia_engine.search_providers import GeminiGroundedSearchProvider
    from ptia_engine.dashboard import _fallback_visual_image_titles
    provider = GeminiGroundedSearchProvider()
    try:
        suggestions = (
            provider.suggest_visual_image_titles(
                title=post.title,
                body=post.body,
                source_urls=post.source_urls,
            )
            if provider.available
            else _fallback_visual_image_titles(post.title, post.body)
        )
    except Exception:
        suggestions = _fallback_visual_image_titles(post.title, post.body)
        
    if len(suggestions) < 2:
        suggestions = _fallback_visual_image_titles(post.title, post.body)
        
    handler._send_json({"ok": True, "suggestions": suggestions})
