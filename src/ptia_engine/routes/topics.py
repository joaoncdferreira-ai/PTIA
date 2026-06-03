from ptia_engine.repositories import EditorialTopicRepository, FinalPostRepository
from ptia_engine.routes.common import to_dict
from ptia_engine.use_cases import CreateTopicFromSignalUseCase, ApprovePackageUseCase
from ptia_engine.editorial_board import update_topic_status

def handle_add_topic(handler, payload):
    repo = EditorialTopicRepository(handler.state.editorial_topics_path)
    use_case = CreateTopicFromSignalUseCase(repo)
    raw_signal_ids = str(payload.get("signal_ids", ""))
    signal_ids = [value.strip() for value in raw_signal_ids.split(",") if value.strip()]
    topic = use_case.execute(
        title=str(payload["title"]),
        thesis=str(payload["thesis"]),
        portugal_angle=str(payload["portugal_angle"]),
        audience=str(payload.get("audience", "")),
        signal_ids=signal_ids,
        urgency_score=int(payload.get("urgency_score", 0) or 0),
    )
    handler._send_json({"ok": True, "topic": to_dict(topic)})

def handle_topic_status(handler, payload):
    topic = update_topic_status(
        handler.state.editorial_topics_path,
        topic_id=str(payload["topic_id"]),
        status=str(payload["status"]),
        notes=str(payload.get("notes", "")),
    )
    handler._send_json({"ok": True, "topic": to_dict(topic)})

def handle_approve_final_package(handler, payload):
    post_repo = FinalPostRepository(handler.state.final_posts_path)
    use_case = ApprovePackageUseCase(post_repo, handler.state.buffer_channels_path)
    posts = use_case.execute(str(payload["post_id"]))
    handler._send_json({"ok": True, "posts": [to_dict(post) for post in posts]})
