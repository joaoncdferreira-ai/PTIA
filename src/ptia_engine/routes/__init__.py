from urllib.parse import urlparse
from http import HTTPStatus

from ptia_engine.routes.static import dashboard_do_get as dashboard_do_get
from ptia_engine.routes.signals import (
    handle_add_signal,
    handle_signal_status,
    handle_quick_capture,
    handle_gemini_scout,
    handle_source_scout,
    handle_reverify_signal,
    handle_reverify_verifying,
)
from ptia_engine.routes.topics import (
    handle_add_topic,
    handle_topic_status,
    handle_approve_final_package,
)
from ptia_engine.routes.posts import (
    handle_build_final_pack,
    handle_update_final_post_copy,
    handle_final_post_status,
    handle_rewrite_final_post,
    handle_rewrite_final_package,
    handle_polish_final_post,
)
from ptia_engine.routes.media import (
    handle_final_image,
    handle_upload_final_image,
    handle_final_image_status,
    handle_image_prompt,
    handle_apply_visual_title,
    handle_suggest_image_titles,
)
from ptia_engine.routes.scheduling import (
    handle_buffer_discover,
    handle_schedule_buffer,
    handle_schedule_package,
)
from ptia_engine.routes.editorial import (
    handle_draft_status,
    handle_item_status,
    handle_performance,
)
from ptia_engine.routes.newsletter import (
    handle_newsletter_generate,
    handle_newsletter_status,
)


POST_ROUTES = {
    # Editorial workflow
    "/api/item-status": handle_item_status,
    "/api/draft-status": handle_draft_status,
    "/api/performance": handle_performance,

    # Signals
    "/api/add-signal": handle_add_signal,
    "/api/signal-status": handle_signal_status,
    "/api/quick-capture": handle_quick_capture,
    "/api/gemini-scout": handle_gemini_scout,
    "/api/source-scout": handle_source_scout,
    "/api/reverify-signal": handle_reverify_signal,
    "/api/reverify-verifying": handle_reverify_verifying,
    
    # Topics
    "/api/add-topic": handle_add_topic,
    "/api/topic-status": handle_topic_status,
    "/api/approve-final-package": handle_approve_final_package,
    
    # Posts
    "/api/build-final-pack": handle_build_final_pack,
    "/api/update-final-post-copy": handle_update_final_post_copy,
    "/api/final-post-status": handle_final_post_status,
    "/api/rewrite-final-post": handle_rewrite_final_post,
    "/api/rewrite-final-package": handle_rewrite_final_package,
    "/api/polish-final-post": handle_polish_final_post,
    
    # Media
    "/api/final-image": handle_final_image,
    "/api/upload-final-image": handle_upload_final_image,
    "/api/final-image-status": handle_final_image_status,
    "/api/image-prompt": handle_image_prompt,
    "/api/apply-visual-title": handle_apply_visual_title,
    "/api/suggest-image-titles": handle_suggest_image_titles,
    
    # Scheduling
    "/api/buffer-discover": handle_buffer_discover,
    "/api/schedule-buffer": handle_schedule_buffer,
    "/api/schedule-package": handle_schedule_package,

    # Newsletter
    "/api/newsletter-generate": handle_newsletter_generate,
    "/api/newsletter-status": handle_newsletter_status,
}

def dashboard_do_post(handler):
    path = urlparse(handler.path).path
    try:
        from ptia_engine.dashboard import _load_project_env
        _load_project_env()
        payload = handler._read_json()
        
        if path in POST_ROUTES:
            POST_ROUTES[path](handler, payload)
            return
            
    except Exception as exc:
        message = str(exc) or repr(exc) or exc.__class__.__name__
        handler._send_json({"error": message}, HTTPStatus.BAD_REQUEST)
        return
        
    handler._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
