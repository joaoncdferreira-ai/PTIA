from dataclasses import asdict
from ptia_engine.models import FinalPost
from ptia_engine.repositories import RadarSignalRepository, EditorialTopicRepository, FinalPostRepository
from ptia_engine.routes.common import to_dict
from ptia_engine.use_cases import BuildFinalPackUseCase, EditPolishPostUseCase
from ptia_engine.editorial_board import update_final_post_status, update_final_post_copy
from ptia_engine.storage import load_final_posts
from ptia_engine.services.editorial_hygiene import (
    normalise_hashtags,
    apply_ptia_editorial_rules,
    validate_final_post_copy,
)
from ptia_engine.search_providers import GeminiGroundedSearchProvider

def handle_build_final_pack(handler, payload):
    signal_repo = RadarSignalRepository(handler.state.radar_signals_path)
    topic_repo = EditorialTopicRepository(handler.state.editorial_topics_path)
    post_repo = FinalPostRepository(handler.state.final_posts_path)
    use_case = BuildFinalPackUseCase(
        signal_repo=signal_repo,
        topic_repo=topic_repo,
        post_repo=post_repo,
        buffer_channels_path=handler.state.buffer_channels_path,
    )
    result = use_case.execute(str(payload["signal_id"]))
    handler._send_json({
        "ok": True,
        "topic": to_dict(result["topic"]),
        "posts": [to_dict(p) for p in result["posts"]]
    })

def handle_update_final_post_copy(handler, payload):
    post_repo = FinalPostRepository(handler.state.final_posts_path)
    use_case = EditPolishPostUseCase(post_repo)
    post_id = str(payload["post_id"])
    sync_topic = bool(payload.get("sync_topic", False))
    title = payload.get("title")
    body = payload.get("body")
    hashtags = payload.get("hashtags")
    image_prompt = payload.get("image_prompt")

    # Older dashboard clients bulk-save every channel even though only the active
    # channel is rendered. Those hidden controls submit empty values; preserving
    # the stored copy prevents a valid package from being blocked or overwritten.
    if not str(title or "").strip() and not str(body or "").strip():
        title = body = hashtags = image_prompt = None

    updated = use_case.execute(
        post_id=post_id,
        title=title,
        body=body,
        hashtags=hashtags,
        image_prompt=image_prompt,
        notes="Editor manual update.",
    )

    response = {"ok": True, "post": to_dict(updated)}

    if sync_topic:
        from ptia_engine.dashboard import _sync_topic_posts_from_reference
        posts = _sync_topic_posts_from_reference(
            handler.state,
            post_id,
            "O editor alterou manualmente este canal. Alinha os restantes canais com a mesma tese, tom e decisão editorial.",
        )
        response["posts"] = [to_dict(p) for p in posts]

    handler._send_json(response)
def handle_final_post_status(handler, payload):
    from ptia_engine.dashboard import _reject_final_post, _sync_static_site_feed
    status = str(payload["status"])
    post_id = str(payload["post_id"])
    post_path = handler.state.final_posts_path
    
    if status == "rejected":
        post = _reject_final_post(handler.state, post_id)
    elif status == "approved_for_schedule":
        from ptia_engine.dashboard import _approve_final_package

        posts = _approve_final_package(handler.state, post_id)
        handler._send_json({"ok": True, "posts": [to_dict(post) for post in posts]})
        return
    else:
        if status in {"approved_for_schedule", "scheduled"}:
            posts = {post.post_id: post for post in load_final_posts(post_path)}
            current = posts.get(post_id)
            if not current:
                raise ValueError(f"Final post not found: {post_id}")
            candidate = FinalPost(
                **{
                    **asdict(current),
                    "status": status,
                    "scheduled_time": str(payload.get("scheduled_time", "")) or current.scheduled_time,
                    "buffer_post_id": str(payload["buffer_post_id"]) if "buffer_post_id" in payload else current.buffer_post_id,
                    "published_url": str(payload.get("published_url", "")) or current.published_url,
                    "image_path": str(payload.get("image_path", "")) or current.image_path,
                    "image_status": str(payload.get("image_status", "")) or current.image_status,
                }
            )
            validate_final_post_copy(candidate)
            
        post = update_final_post_status(
            post_path,
            post_id=post_id,
            status=status,
            scheduled_time=str(payload.get("scheduled_time", "")),
            buffer_post_id=str(payload["buffer_post_id"]) if "buffer_post_id" in payload else None,
            published_url=str(payload.get("published_url", "")),
            image_path=str(payload.get("image_path", "")),
            image_status=str(payload.get("image_status", "")),
        )
        
    if post.channel == "site":
        _sync_static_site_feed(handler.state)
        
    handler._send_json({"ok": True, "post": to_dict(post)})

def handle_rewrite_final_post(handler, payload):
    post_id = str(payload["post_id"])
    feedback = str(payload.get("feedback", "")).strip()
    if not feedback:
        raise ValueError("Escreve o que queres melhorar.")
        
    posts = {post.post_id: post for post in load_final_posts(handler.state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
        
    provider = GeminiGroundedSearchProvider()
    rewrite = provider.rewrite_final_post(
        channel=post.channel,
        title=post.title,
        body=post.body,
        hashtags=post.hashtags,
        source_urls=post.source_urls,
        feedback=feedback,
    )
    
    clean_title, clean_body = apply_ptia_editorial_rules(
        rewrite.title or post.title,
        rewrite.body or post.body,
        post.channel,
    )
    
    candidate = FinalPost(
        post_id=post.post_id,
        topic_id=post.topic_id,
        channel=post.channel,
        title=clean_title,
        body=clean_body,
        hashtags=normalise_hashtags(rewrite.hashtags or post.hashtags, post.channel),
        image_prompt=post.image_prompt,
        source_urls=post.source_urls,
        image_path=post.image_path,
        image_variants=post.image_variants,
        image_status=post.image_status,
        editor_notes=post.editor_notes,
        status=post.status,
        scheduled_time=post.scheduled_time,
        buffer_post_id=post.buffer_post_id,
        published_url=post.published_url,
        created_at=post.created_at,
    )
    validate_final_post_copy(candidate)
    
    updated = update_final_post_copy(
        handler.state.final_posts_path,
        post_id,
        title=clean_title,
        body=clean_body,
        hashtags=candidate.hashtags,
        notes=f"Feedback: {feedback}\nRewrite: {rewrite.rationale}",
    )
    handler._send_json({"ok": True, "post": to_dict(updated)})

def handle_rewrite_final_package(handler, payload):
    post_id = str(payload["post_id"])
    feedback = str(payload.get("feedback", "")).strip()
    if not feedback:
        raise ValueError("Escreve o que queres melhorar.")
        
    from ptia_engine.dashboard import _sync_topic_posts_from_reference
    updated = _sync_topic_posts_from_reference(handler.state, post_id, feedback)
    handler._send_json({"ok": True, "posts": [to_dict(post) for post in updated]})

def handle_polish_final_post(handler, payload):
    post_id = str(payload["post_id"])
    posts = {post.post_id: post for post in load_final_posts(handler.state.final_posts_path)}
    post = posts.get(post_id)
    if not post:
        raise ValueError(f"Final post not found: {post_id}")
        
    from ptia_engine.dashboard import _polish_final_post_copy
    polished = _polish_final_post_copy(
        channel=post.channel,
        title=post.title,
        body=post.body,
        hashtags=post.hashtags,
        source_urls=post.source_urls,
    )
    
    candidate = FinalPost(
        post_id=post.post_id,
        topic_id=post.topic_id,
        channel=post.channel,
        title=polished["title"],
        body=polished["body"],
        hashtags=normalise_hashtags(polished["hashtags"], post.channel),
        image_prompt=post.image_prompt,
        source_urls=post.source_urls,
        image_path=post.image_path,
        image_variants=post.image_variants,
        image_status=post.image_status,
        editor_notes=post.editor_notes,
        status=post.status,
        scheduled_time=post.scheduled_time,
        buffer_post_id=post.buffer_post_id,
        published_url=post.published_url,
        created_at=post.created_at,
    )
    validate_final_post_copy(candidate)
    
    updated = update_final_post_copy(
        handler.state.final_posts_path,
        post_id,
        title=polished["title"],
        body=polished["body"],
        hashtags=candidate.hashtags,
        notes=polished["editor_notes"],
    )
    handler._send_json({"ok": True, "post": to_dict(updated)})
