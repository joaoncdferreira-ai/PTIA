from ptia_engine.routes.common import to_dict

def handle_buffer_discover(handler, payload):
    from ptia_engine.dashboard import _discover_buffer_channels
    config = _discover_buffer_channels(handler.state.buffer_channels_path)
    handler._send_json({"ok": True, "buffer_channels": config})

def handle_schedule_buffer(handler, payload):
    from ptia_engine.dashboard import _schedule_post_in_buffer
    post = _schedule_post_in_buffer(
        handler.state,
        post_id=str(payload["post_id"]),
        scheduled_time=str(payload["scheduled_time"]),
    )
    handler._send_json({"ok": True, "post": to_dict(post)})

def handle_schedule_package(handler, payload):
    from ptia_engine.dashboard import _schedule_final_package
    posts = _schedule_final_package(
        handler.state,
        topic_id=str(payload["topic_id"]),
        scheduled_time=str(payload["scheduled_time"]),
    )
    handler._send_json({"ok": True, "posts": [to_dict(post) for post in posts]})
