from ptia_engine.repositories import RadarSignalRepository
from ptia_engine.routes.common import to_dict
from ptia_engine.use_cases import ReverifySignalUseCase
from ptia_engine.editorial_board import add_radar_signal, update_signal_status, add_editorial_topic
from ptia_engine.source_verifier import resolve_submitted_link, verify_search_candidate
from ptia_engine.search_providers import GeminiGroundedSearchProvider

def handle_add_signal(handler, payload):
    signal = add_radar_signal(
        handler.state.radar_signals_path,
        source_type=str(payload["source_type"]),
        source_name=str(payload["source_name"]),
        title=str(payload["title"]),
        url=str(payload["url"]),
        published_at=str(payload["published_at"]),
        engagement_score=int(payload.get("engagement_score", 0) or 0),
        summary=str(payload.get("summary", "")),
        topic_hint=str(payload.get("topic_hint", "")),
        why_it_matters=str(payload.get("why_it_matters", "")),
        why_engaged=str(payload.get("why_engaged", "")),
        notes=str(payload.get("notes", "")),
    )
    handler._send_json({"ok": True, "signal": to_dict(signal)})

def handle_signal_status(handler, payload):
    signal = update_signal_status(
        handler.state.radar_signals_path,
        signal_id=str(payload["signal_id"]),
        status=str(payload["status"]),
        notes=str(payload.get("notes", "")),
    )
    handler._send_json({"ok": True, "signal": to_dict(signal)})

def handle_quick_capture(handler, payload):
    link = str(payload.get("link", "")).strip()
    thought = str(payload.get("thought", "")).strip()
    results = {}
    if link:
        verification = resolve_submitted_link(link, thought=thought)
        target_status = "verified" if verification.status == "verified" else "verifying"
        signal = add_radar_signal(
            handler.state.radar_signals_path,
            source_type="news",
            source_name=verification.source_name,
            title=verification.title,
            url=verification.verified_url or link,
            published_at=verification.published_at,
            engagement_score=60 if verification.status == "verified" else 10,
            summary=verification.summary or thought,
            topic_hint=thought,
            why_it_matters=thought,
            why_engaged="",
            notes=verification.notes,
            status=target_status,
            require_recent=verification.status == "verified",
        )
        if signal.status != target_status:
            signal = update_signal_status(
                handler.state.radar_signals_path,
                signal.signal_id,
                target_status,
                "Re-submetido pelo editor: " + verification.notes,
            )
        results["signal"] = to_dict(signal)
    if thought and not link:
        topic = add_editorial_topic(
            handler.state.editorial_topics_path,
            title=thought[:90],
            thesis=thought,
            portugal_angle="A desenvolver pelo editor a partir deste pensamento.",
            audience="PTIA",
            source_signal_ids=[],
            urgency_score=5,
        )
        results["topic"] = to_dict(topic)
    if not link and not thought:
        raise ValueError("Cola um link ou escreve um pensamento.")
    handler._send_json({"ok": True, **results})

def handle_gemini_scout(handler, payload):
    provider = GeminiGroundedSearchProvider()
    candidates = provider.scout_today_ai_news(limit=int(payload.get("limit", 8) or 8))
    written = []
    rejected = []
    for candidate in candidates:
        verification = verify_search_candidate(candidate)
        if verification.status != "verified":
            rejected.append({"url": candidate.url, "status": verification.status})
            continue
        signal = add_radar_signal(
            handler.state.radar_signals_path,
            source_type="gemini_scout",
            source_name=verification.source_name,
            title=verification.title or candidate.title,
            url=verification.verified_url or candidate.url,
            published_at=verification.published_at,
            engagement_score=55,
            summary=verification.summary or candidate.summary,
            topic_hint=candidate.title,
            why_it_matters=candidate.why_it_matters,
            why_engaged="",
            notes="Gemini Scout diário; fonte e data verificadas localmente.",
            status="verified",
            require_recent=True,
        )
        written.append(to_dict(signal))
    handler._send_json({"ok": True, "written": written, "rejected": rejected})

def handle_source_scout(handler, payload):
    from ptia_engine.dashboard import _run_rss_scout, _run_discovery_scout
    source = str(payload.get("source", "")).strip()
    limit = int(payload.get("limit", 8) or 8)
    if source == "rss":
        result = _run_rss_scout(handler.state, limit=limit)
    else:
        result = _run_discovery_scout(handler.state, source=source, limit=limit)
    handler._send_json({"ok": True, **result})

def handle_reverify_signal(handler, payload):
    repo = RadarSignalRepository(handler.state.radar_signals_path)
    use_case = ReverifySignalUseCase(repo)
    result = use_case.execute_single(str(payload["signal_id"]))
    if result.get("verified"):
        handler._send_json({"ok": True, "signal": to_dict(result["signal"])})
    else:
        handler._send_json({"ok": True, "status": result.get("status"), "notes": result.get("notes")})

def handle_reverify_verifying(handler, payload):
    repo = RadarSignalRepository(handler.state.radar_signals_path)
    use_case = ReverifySignalUseCase(repo)
    result = use_case.execute_queue()
    handler._send_json({"ok": True, **result})
