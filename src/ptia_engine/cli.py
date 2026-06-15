from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
except Exception:
    pass

from ptia_engine.budget import (
    append_usage,
    estimate_tokens,
    load_monthly_spend_usd,
    make_usage_record,
)
from ptia_engine.ai_drafts import (
    build_ai_draft_prompt,
    estimate_ai_draft_cost,
    generate_ai_draft_payload,
    payload_to_drafts,
)
from ptia_engine.assets import create_assets_for_draft
from ptia_engine.classifier import (
    build_classification_prompt,
    classify_heuristic,
    classify_openai,
    estimate_openai_classification_cost,
)
from ptia_engine.dedupe import append_articles, find_duplicate, load_articles
from ptia_engine.drafts import make_template_drafts
from ptia_engine.dashboard import serve_dashboard
from ptia_engine.editorial import (
    export_scheduling_queue,
    update_draft_status,
    update_item_status,
)
from ptia_engine.editorial_automation import EditorialAutomationService
from ptia_engine.editorial_board import (
    add_editorial_topic,
    add_final_post,
    add_radar_signal,
    update_final_post_status,
    update_signal_status,
    update_topic_status,
)
from ptia_engine.exports import (
    export_content_drafts_csv,
    export_processed_items_csv,
    export_raw_articles_csv,
    export_sources_csv,
)
from ptia_engine.growth import format_growth_report, load_growth_report, write_growth_report
from ptia_engine.ai_visibility import build_ai_visibility_report, format_ai_visibility_report
from ptia_engine.knowledge import KnowledgeValidationError, build_knowledge_site
from ptia_engine.learning import (
    generate_learning_weights,
    load_learning_weights,
    write_learning_weights,
)
from ptia_engine.linkedin_performance import import_linkedin_export
from ptia_engine.llm_providers import default_model_for_provider, normalize_provider
from ptia_engine.meta_insights import MetaGraphClient, MetaInsightsError
from ptia_engine.models import RawArticle, Source
from ptia_engine.performance_import import import_instagram_insights
from ptia_engine.rss import fetch_source
from ptia_engine.search_providers import GeminiGroundedSearchProvider
from ptia_engine.scheduler import (
    NoopScheduleBackend,
    build_schedule_day_plan,
    build_schedule_execution_plan,
    execute_schedule_plan,
    format_execution_plan,
    format_schedule_plan,
    load_schedule_slots,
)
from ptia_engine.services.schedule_backend import (
    DashboardScheduleBackend,
    ScheduleCapabilities,
    missing_capabilities,
)
from ptia_engine.source_verifier import verify_search_candidate
from ptia_engine.storage import (
    append_jsonl,
    load_content_drafts,
    load_final_posts,
    load_processed_items,
    load_trend_signals,
)
from ptia_engine.trend_radar import fetch_hacker_news_trends, trend_to_markdown

DEFAULT_DATA_FILES = [
    "raw_articles.jsonl",
    "processed_items.jsonl",
    "content_drafts.jsonl",
    "content_performance.jsonl",
    "trend_signals.jsonl",
    "content_assets.jsonl",
    "radar_signals.jsonl",
    "editorial_topics.jsonl",
    "final_posts.jsonl",
    "editorial_fact_packs.jsonl",
    "editorial_automation_runs.jsonl",
]

SIGNAL_KEYWORDS = {
    "portugal": 5,
    "portuguese": 4,
    "europe": 3,
    "european": 3,
    "eu": 2,
    "regulation": 4,
    "ai act": 5,
    "privacy": 3,
    "agent": 3,
    "agents": 3,
    "open source": 3,
    "model": 2,
    "enterprise": 2,
    "business": 2,
    "developer": 2,
    "research": 2,
    "safety": 2,
}


def load_local_env() -> None:
    for filename in (".env", ".env.local"):
        path = Path(filename)
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_sources(path: Path) -> list[Source]:
    records = json.loads(path.read_text(encoding="utf-8"))
    return [Source.from_record(record) for record in records]


def cmd_init_data(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename in DEFAULT_DATA_FILES:
        path = data_dir / filename
        path.touch(exist_ok=True)
        print(f"ok {path}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    sources = [
        source
        for source in load_sources(Path(args.sources))
        if source.active and source.rss_url.strip()
    ]
    out_path = Path(args.out)
    existing = load_articles(out_path)
    existing_by_id = {article.article_id: article for article in existing}
    articles_to_append: list[RawArticle] = []
    stats: Counter[str] = Counter()

    for source in sources:
        try:
            fetched = fetch_source(source, limit=args.limit_per_source)
        except Exception as exc:  # noqa: BLE001 - CLI should keep processing other feeds.
            stats["source_errors"] += 1
            print(f"error {source.source_id}: {exc}")
            continue

        stats["fetched"] += len(fetched)
        seen_for_source = existing + articles_to_append
        for article in fetched:
            if article.article_id in existing_by_id:
                stats["already_seen"] += 1
                continue
            duplicate = find_duplicate(article, seen_for_source, title_threshold=args.title_threshold)
            if duplicate:
                article.status = "duplicate"
                article.duplicate_of = duplicate.article_id
                stats["duplicates"] += 1
            else:
                stats["new"] += 1
            articles_to_append.append(article)
            existing_by_id[article.article_id] = article

    append_articles(out_path, articles_to_append)
    print(
        "summary "
        + json.dumps(
            {
                "sources": len(sources),
                "fetched": stats["fetched"],
                "new": stats["new"],
                "duplicates": stats["duplicates"],
                "already_seen": stats["already_seen"],
                "source_errors": stats["source_errors"],
                "written": len(articles_to_append),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _briefing_score(article: RawArticle) -> int:
    text = f"{article.title_original} {article.raw_excerpt}".casefold()
    score = 0
    for keyword, value in SIGNAL_KEYWORDS.items():
        if keyword in text:
            score += value
    if article.country == "PT":
        score += 5
    if article.status == "duplicate":
        score -= 10
    return score


def cmd_briefing(args: argparse.Namespace) -> int:
    articles = load_articles(Path(args.articles))
    candidates = [article for article in articles if article.status != "duplicate"]
    ranked = sorted(candidates, key=_briefing_score, reverse=True)[: args.limit]
    lines = [
        "# PTIA Daily Briefing",
        "",
        "Este briefing local e uma triagem simples. A classificacao AI entra na proxima milestone.",
        "",
    ]
    if not ranked:
        lines.append("Sem candidatos ainda. Corre primeiro a ingestao RSS.")
    for index, article in enumerate(ranked, start=1):
        lines.extend(
            [
                f"## {index}. {article.title_original}",
                "",
                f"- Fonte: {article.source_name}",
                f"- URL: {article.url}",
                f"- Score local: {_briefing_score(article)}",
                f"- Publicado: {article.published_at or 'desconhecido'}",
                f"- Excerto: {article.raw_excerpt or 'sem excerto'}",
                "",
            ]
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"ok {out_path}")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    articles = [
        article
        for article in load_articles(Path(args.articles))
        if article.status != "duplicate"
    ]
    out_path = Path(args.out)
    processed = load_processed_items(out_path)
    processed_article_ids = {item.article_id for item in processed}
    ledger_path = Path(args.usage_ledger)
    monthly_budget_usd = float(args.monthly_budget_usd)
    model = args.model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    max_output_tokens = int(args.max_output_tokens)
    monthly_spend = load_monthly_spend_usd(ledger_path)
    learning_weights = load_learning_weights(Path(args.learning_weights))
    new_items = []
    stats: Counter[str] = Counter()

    for article in articles:
        if len(new_items) >= args.limit:
            break
        if article.article_id in processed_article_ids:
            stats["already_processed"] += 1
            continue

        if args.mode == "heuristic":
            item = classify_heuristic(article, learning_weights=learning_weights)
            new_items.append(item)
            stats["classified"] += 1
            stats["should_cover" if item.should_cover else "rejected"] += 1
            continue

        estimated_cost = estimate_openai_classification_cost(article, model, max_output_tokens)
        if monthly_spend + estimated_cost > monthly_budget_usd:
            stats["budget_skipped"] += 1
            continue

        try:
            item = classify_openai(article, model=model, max_output_tokens=max_output_tokens)
        except Exception as exc:  # noqa: BLE001 - CLI should report and keep batch usable.
            stats["errors"] += 1
            print(f"error {article.article_id}: {exc}")
            continue

        prompt = build_classification_prompt(article)
        input_tokens = estimate_tokens(prompt)
        output_tokens = max_output_tokens
        usage_record = make_usage_record(
            model=model,
            operation="classification",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            article_id=article.article_id,
        )
        usage_record.estimated_cost_usd = item.estimated_cost_usd or estimated_cost
        append_usage(ledger_path, usage_record)
        monthly_spend += usage_record.estimated_cost_usd

        new_items.append(item)
        stats["classified"] += 1
        stats["should_cover" if item.should_cover else "rejected"] += 1

    append_jsonl(out_path, new_items)
    print(
        "summary "
        + json.dumps(
            {
                "mode": args.mode,
                "model": model if args.mode == "openai" else "heuristic",
                "classified": stats["classified"],
                "should_cover": stats["should_cover"],
                "rejected": stats["rejected"],
                "already_processed": stats["already_processed"],
                "budget_skipped": stats["budget_skipped"],
                "errors": stats["errors"],
                "written": len(new_items),
                "monthly_spend_usd_estimate": round(monthly_spend, 6),
                "monthly_budget_usd": monthly_budget_usd,
                "learning_weights": args.learning_weights,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    processed = load_processed_items(Path(args.processed))
    articles_by_id = {article.article_id: article for article in load_articles(Path(args.articles))}
    candidates = [
        item
        for item in processed
        if item.should_cover and item.editorial_status in {"needs_review", "needs_source_check"}
    ]
    candidates.sort(
        key=lambda item: (
            item.relevance_score,
            item.portugal_relevance_score,
            item.builder_relevance_score,
            item.business_relevance_score,
            -item.hype_score,
        ),
        reverse=True,
    )
    lines = [
        "# PTIA Review Queue",
        "",
        "Fila local para revisao humana. Nada aqui esta aprovado para publicar.",
        "",
        f"Total candidatos: {len(candidates)}",
        "",
    ]
    for index, item in enumerate(candidates[: args.limit], start=1):
        article = articles_by_id.get(item.article_id)
        excerpt = article.raw_excerpt if article else ""
        lines.extend(
            [
                f"## {index}. {item.title_original}",
                "",
                f"- Item: `{item.item_id}`",
                f"- Seccao: `{item.section}`",
                f"- Fonte: {item.source_name}",
                f"- URL: {item.source_url}",
                f"- Relevancia: {item.relevance_score}/10",
                f"- Portugal: {item.portugal_relevance_score}/10",
                f"- Builders: {item.builder_relevance_score}/10",
                f"- Empresas: {item.business_relevance_score}/10",
                f"- Hype: {item.hype_score}/10",
                f"- Estado: `{item.editorial_status}`",
                f"- Razao: {item.reason}",
                f"- Riscos: {item.risk_notes or 'sem notas'}",
                "",
                "### Excerto",
                "",
                excerpt or "Sem excerto.",
                "",
                "### Checklist humana",
                "",
                "- [ ] Confirmar fonte original",
                "- [ ] Confirmar que nao ha claims sem suporte",
                "- [ ] Decidir se ha angulo Portugal",
                "- [ ] Aprovar, editar ou rejeitar",
                "",
            ]
        )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"ok {out_path}")
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    processed = load_processed_items(Path(args.processed))
    articles_by_id = {article.article_id: article for article in load_articles(Path(args.articles))}
    existing_drafts = load_content_drafts(Path(args.out))
    existing_draft_ids = {draft.draft_id for draft in existing_drafts}
    selected_items = [
        item
        for item in processed
        if item.should_cover and item.editorial_status in set(args.status)
    ]
    selected_items.sort(
        key=lambda item: (
            item.relevance_score,
            item.portugal_relevance_score,
            item.builder_relevance_score,
            item.business_relevance_score,
        ),
        reverse=True,
    )
    drafts_to_write = []
    stats: Counter[str] = Counter()
    for item in selected_items[: args.limit]:
        article = articles_by_id.get(item.article_id)
        if not article:
            stats["missing_article"] += 1
            continue
        drafts = make_template_drafts(item, article)
        for draft in drafts:
            if draft.draft_id in existing_draft_ids:
                stats["already_exists"] += 1
                continue
            drafts_to_write.append(draft)
            existing_draft_ids.add(draft.draft_id)
            stats[draft.channel] += 1

    append_jsonl(Path(args.out), drafts_to_write)
    print(
        "summary "
        + json.dumps(
            {
                "items": min(len(selected_items), args.limit),
                "written": len(drafts_to_write),
                "linkedin": stats["linkedin"],
                "instagram": stats["instagram"],
                "site": stats["site"],
                "newsletter": stats["newsletter"],
                "already_exists": stats["already_exists"],
                "missing_article": stats["missing_article"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_ai_drafts(args: argparse.Namespace) -> int:
    processed_path = Path(args.processed)
    drafts_path = Path(args.out)
    ledger_path = Path(args.usage_ledger)
    articles_by_id = {article.article_id: article for article in load_articles(Path(args.articles))}
    items = [
        item
        for item in load_processed_items(processed_path)
        if item.should_cover and item.editorial_status in set(args.status)
    ]
    items.sort(
        key=lambda item: (
            item.relevance_score,
            item.portugal_relevance_score,
            item.builder_relevance_score,
            item.business_relevance_score,
        ),
        reverse=True,
    )
    existing_draft_ids = {draft.draft_id for draft in load_content_drafts(drafts_path)}
    monthly_spend = load_monthly_spend_usd(ledger_path)
    provider = normalize_provider(args.provider)
    model = args.model or default_model_for_provider(provider)
    new_drafts = []
    stats: Counter[str] = Counter()

    for item in items[: args.limit]:
        article = articles_by_id.get(item.article_id)
        if not article:
            stats["missing_article"] += 1
            continue
        estimated_cost = estimate_ai_draft_cost(
            item,
            article,
            model,
            args.max_output_tokens,
            provider=provider,
        )
        if monthly_spend + estimated_cost > args.monthly_budget_usd:
            stats["budget_skipped"] += 1
            continue
        try:
            payload, actual_cost = generate_ai_draft_payload(
                item,
                article,
                provider=provider,
                model=model,
                max_output_tokens=args.max_output_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - CLI reports batch-level errors.
            stats["errors"] += 1
            print(f"error {item.item_id}: {exc}")
            continue

        drafts = payload_to_drafts(item, payload, f"{provider}:{model}")
        written_for_item = 0
        for draft in drafts:
            if draft.draft_id in existing_draft_ids:
                stats["already_exists"] += 1
                continue
            new_drafts.append(draft)
            existing_draft_ids.add(draft.draft_id)
            written_for_item += 1
            stats[draft.channel] += 1
        if written_for_item:
            update_item_status(processed_path, item.item_id, "draft_ready", "AI drafts generated.")
            stats["items"] += 1

        prompt = build_ai_draft_prompt(item, article)
        usage_record = make_usage_record(
            model=f"{provider}:{model}",
            operation="draft_generation",
            input_tokens=estimate_tokens(prompt),
            output_tokens=args.max_output_tokens,
            article_id=item.article_id,
        )
        usage_record.estimated_cost_usd = actual_cost
        append_usage(ledger_path, usage_record)
        monthly_spend += actual_cost

    append_jsonl(drafts_path, new_drafts)
    print(
        "summary "
        + json.dumps(
            {
                "items": stats["items"],
                "provider": provider,
                "model": model,
                "written": len(new_drafts),
                "linkedin": stats["linkedin"],
                "instagram": stats["instagram"],
                "site": stats["site"],
                "newsletter": stats["newsletter"],
                "already_exists": stats["already_exists"],
                "budget_skipped": stats["budget_skipped"],
                "missing_article": stats["missing_article"],
                "errors": stats["errors"],
                "monthly_spend_usd_estimate": round(monthly_spend, 6),
                "monthly_budget_usd": args.monthly_budget_usd,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_assets(args: argparse.Namespace) -> int:
    drafts = [
        draft
        for draft in load_content_drafts(Path(args.drafts))
        if draft.status in set(args.status) and draft.channel in set(args.channel)
    ]
    items = {item.item_id: item for item in load_processed_items(Path(args.processed))}
    out_dir = Path(args.out_dir)
    all_assets = []
    stats: Counter[str] = Counter()
    for draft in drafts[: args.limit]:
        item = items.get(draft.item_id)
        if not item:
            stats["missing_item"] += 1
            continue
        assets = create_assets_for_draft(
            draft=draft,
            item_section=item.section,
            source_name=item.source_name,
            out_dir=out_dir,
        )
        all_assets.extend(assets)
        for asset in assets:
            stats[asset.asset_type] += 1
    print(
        "summary "
        + json.dumps(
            {
                "drafts": len(drafts[: args.limit]),
                "assets": len(all_assets),
                "square_cards": stats["square_card"],
                "carousel_slides": stats["carousel_slide"],
                "missing_item": stats["missing_item"],
                "out_dir": args.out_dir,
                "ledger": str(out_dir.parent / "content_assets.jsonl"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_export_drafts(args: argparse.Namespace) -> int:
    drafts = load_content_drafts(Path(args.drafts))
    if args.channel:
        drafts = [draft for draft in drafts if draft.channel == args.channel]
    if args.format:
        drafts = [draft for draft in drafts if draft.format == args.format]
    drafts = drafts[: args.limit]
    lines = [
        "# PTIA Drafts",
        "",
        "Export local para revisao humana. Estes textos ainda nao estao aprovados para publicacao.",
        "",
    ]
    for index, draft in enumerate(drafts, start=1):
        content = draft.body or draft.caption or draft.carousel_outline
        lines.extend(
            [
                f"## {index}. {draft.title}",
                "",
                f"- Draft: `{draft.draft_id}`",
                f"- Item: `{draft.item_id}`",
                f"- Canal: `{draft.channel}`",
                f"- Formato: `{draft.format}`",
                f"- Estado: `{draft.status}`",
                "",
                "```text",
                content.strip(),
                "```",
                "",
            ]
        )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"ok {out_path}")
    return 0


def cmd_export_csv(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    exports = {
        "sources.csv": lambda path: export_sources_csv(Path(args.sources), path),
        "raw_articles.csv": lambda path: export_raw_articles_csv(Path(args.articles), path),
        "processed_items.csv": lambda path: export_processed_items_csv(Path(args.processed), path),
        "content_drafts.csv": lambda path: export_content_drafts_csv(Path(args.drafts), path),
    }
    for filename, export_func in exports.items():
        path = out_dir / filename
        export_func(path)
        print(f"ok {path}")
    return 0


def cmd_item_status(args: argparse.Namespace) -> int:
    item = update_item_status(
        processed_path=Path(args.processed),
        item_id=args.item_id,
        status=args.status,
        editor_notes=args.notes,
    )
    print(
        "summary "
        + json.dumps(
            {
                "item_id": item.item_id,
                "title": item.title_original,
                "editorial_status": item.editorial_status,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_draft_status(args: argparse.Namespace) -> int:
    draft = update_draft_status(
        drafts_path=Path(args.drafts),
        draft_id=args.draft_id,
        status=args.status,
        scheduled_time=args.scheduled_time,
        published_url=args.published_url,
        buffer_post_id=args.buffer_post_id,
    )
    print(
        "summary "
        + json.dumps(
            {
                "draft_id": draft.draft_id,
                "title": draft.title,
                "channel": draft.channel,
                "format": draft.format,
                "status": draft.status,
                "scheduled_time": draft.scheduled_time,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    serve_dashboard(data_dir=Path(args.data_dir), host=args.host, port=args.port)
    return 0


def cmd_schedule_day(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    slots = load_schedule_slots(Path(args.plan)) if args.plan else None
    final_posts_path = data_dir / "final_posts.jsonl"
    plan = build_schedule_day_plan(
        repo_root=Path.cwd(),
        date=args.date,
        final_posts_path=final_posts_path,
        buffer_channels_path=data_dir / "buffer_channels.json",
        slots=slots,
        dry_run=True,
    )
    if args.execution_plan or args.simulate_execute or args.execute_real:
        execution_plan = build_schedule_execution_plan(
            plan,
            final_posts=load_final_posts(final_posts_path),
            dry_run=not (args.simulate_execute or args.execute_real),
        )
        if args.simulate_execute or args.execute_real:
            capabilities = ScheduleCapabilities(
                publish_assets=args.publish_assets,
                send_buffer=args.send_buffer,
                write_site_feed=args.write_site_feed,
            )
            if args.execute_real:
                missing = missing_capabilities(execution_plan.actions, capabilities)
                if missing:
                    print("error missing explicit execution flags: " + ", ".join(missing))
                    return 2
                backend = DashboardScheduleBackend(
                    repo_root=Path.cwd(),
                    data_dir=data_dir,
                    capabilities=capabilities,
                )
            else:
                backend = NoopScheduleBackend()
            try:
                results = execute_schedule_plan(
                    execution_plan,
                    backend=backend,
                    confirm_date=args.confirm,
                    audit_path=Path(args.audit_log) if args.audit_log else None,
                )
            except ValueError as exc:
                print(f"error {exc}")
                return 2
            payload = {
                "execution_plan": execution_plan.to_record(),
                "results": [result.to_record() for result in results],
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_execution_plan(execution_plan))
                print("execution_results" if args.execute_real else "simulation_results")
                for result in results:
                    print(f"- {result.kind} {result.status} {result.external_id} {result.message}")
            return 0
        if args.json:
            print(json.dumps(execution_plan.to_record(), ensure_ascii=False, indent=2))
        else:
            print(format_execution_plan(execution_plan))
        return 0 if execution_plan.ready else 2
    if args.json:
        print(json.dumps(plan.to_record(), ensure_ascii=False, indent=2))
    else:
        print(format_schedule_plan(plan))
    return 0 if plan.ready else 2


def cmd_linkedin_comments(args: argparse.Namespace) -> int:
    from ptia_engine.linkedin_commenter import run_linkedin_comments_pipeline
    result = run_linkedin_comments_pipeline()
    if result.get("ok"):
        return 0
    print(f"Erro ao executar comentários do LinkedIn: {result.get('error')}")
    return 1


def cmd_add_signal(args: argparse.Namespace) -> int:
    signal = add_radar_signal(
        Path(args.out),
        source_type=args.source_type,
        source_name=args.source_name,
        title=args.title,
        url=args.url,
        published_at=args.published_at,
        engagement_score=args.engagement_score,
        summary=args.summary,
        topic_hint=args.topic_hint,
        why_it_matters=args.why_it_matters,
        why_engaged=args.why_engaged,
        notes=args.notes,
        max_age_days=args.max_age_days,
    )
    print("summary " + json.dumps(signal.to_record(), ensure_ascii=False))
    return 0


def cmd_signal_status(args: argparse.Namespace) -> int:
    signal = update_signal_status(Path(args.signals), args.signal_id, args.status, args.notes)
    print("summary " + json.dumps(signal.to_record(), ensure_ascii=False))
    return 0


def cmd_add_topic(args: argparse.Namespace) -> int:
    topic = add_editorial_topic(
        Path(args.out),
        title=args.title,
        thesis=args.thesis,
        portugal_angle=args.portugal_angle,
        audience=args.audience,
        source_signal_ids=[value.strip() for value in args.signal_ids.split(",") if value.strip()],
        urgency_score=args.urgency_score,
    )
    print("summary " + json.dumps(topic.to_record(), ensure_ascii=False))
    return 0


def cmd_topic_status(args: argparse.Namespace) -> int:
    topic = update_topic_status(Path(args.topics), args.topic_id, args.status, args.notes)
    print("summary " + json.dumps(topic.to_record(), ensure_ascii=False))
    return 0


def cmd_add_final_post(args: argparse.Namespace) -> int:
    post = add_final_post(
        Path(args.out),
        topic_id=args.topic_id,
        channel=args.channel,
        title=args.title,
        body=args.body,
        hashtags=args.hashtags,
        image_prompt=args.image_prompt,
        source_urls=[value.strip() for value in args.source_urls.split("|") if value.strip()],
        image_path=args.image_path,
    )
    print("summary " + json.dumps(post.to_record(), ensure_ascii=False))
    return 0


def cmd_final_post_status(args: argparse.Namespace) -> int:
    post = update_final_post_status(
        Path(args.posts),
        args.post_id,
        args.status,
        scheduled_time=args.scheduled_time,
        published_url=args.published_url,
        image_path=args.image_path,
    )
    print("summary " + json.dumps(post.to_record(), ensure_ascii=False))
    return 0


def cmd_export_schedule(args: argparse.Namespace) -> int:
    count = export_scheduling_queue(
        drafts_path=Path(args.drafts),
        out_path=Path(args.out),
        statuses=set(args.status),
        channels=set(args.channel),
    )
    print(
        "summary "
        + json.dumps(
            {
                "out": args.out,
                "drafts": count,
                "statuses": args.status,
                "channels": args.channel,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    weights = generate_learning_weights(
        processed_path=Path(args.processed),
        drafts_path=Path(args.drafts),
        performance_path=Path(args.performance),
        min_samples=args.min_samples,
        final_posts_path=Path(args.final_posts),
    )
    write_learning_weights(Path(args.out), weights)
    print(
        "summary "
        + json.dumps(
            {
                "out": args.out,
                "sample_count": weights["sample_count"],
                "baseline_score": weights["baseline_score"],
                "source_boosts": len(weights["source_boosts"]),
                "section_boosts": len(weights["section_boosts"]),
                "recommendations": weights["recommendations"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_instagram_insights(args: argparse.Namespace) -> int:
    client = MetaGraphClient(
        access_token=os.getenv("META_ACCESS_TOKEN", ""),
        instagram_business_id=os.getenv("META_INSTAGRAM_BUSINESS_ID", ""),
        graph_version=os.getenv("META_GRAPH_VERSION", ""),
    )
    try:
        records = import_instagram_insights(
            final_posts_path=Path(args.final_posts),
            performance_path=Path(args.performance),
            limit=args.limit,
            client=client,
        )
    except MetaInsightsError as exc:
        print("error " + json.dumps({"message": str(exc)}, ensure_ascii=False))
        return 1
    print(
        "summary "
        + json.dumps(
            {
                "records": len(records),
                "performance": args.performance,
                "instagram_business_id_configured": bool(client.instagram_business_id),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_growth_report(args: argparse.Namespace) -> int:
    report = load_growth_report(
        final_posts_path=Path(args.final_posts),
        performance_path=Path(args.performance),
        top_limit=args.top_limit,
        min_samples=args.min_samples,
    )
    if args.json:
        output = json.dumps(report.to_record(), ensure_ascii=False, indent=2)
    else:
        output = format_growth_report(report)
    print(output)
    if args.out:
        write_growth_report(Path(args.out), report, json_output=args.json)
    return 0


def cmd_ai_visibility_report(args: argparse.Namespace) -> int:
    report = build_ai_visibility_report(Path(args.site_dir))
    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        output = format_ai_visibility_report(report)
    print(output)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output, encoding="utf-8")
    return 0


def cmd_linkedin_insights(args: argparse.Namespace) -> int:
    result = import_linkedin_export(
        export_path=Path(args.export),
        final_posts_path=Path(args.final_posts),
        performance_path=Path(args.performance),
        match_threshold=args.match_threshold,
    )
    print(
        "summary "
        + json.dumps(
            {
                "imported": result.imported,
                "matched": result.matched,
                "unmatched": result.unmatched,
                "performance": args.performance,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_knowledge_update(args: argparse.Namespace) -> int:
    try:
        payload = build_knowledge_site(root=Path(args.root))
    except KnowledgeValidationError as exc:
        print("error " + json.dumps({"message": str(exc)}, ensure_ascii=False))
        return 1
    summary = {
        "edition": payload["edition"],
        "signal_articles": payload["signal_articles"],
        "companies": len(payload["companies"]),
        "people": len(payload["people"]),
        "tools": len(payload["tools"]),
        "prompts": len(payload["prompts"]),
        "glossary": len(payload["glossary"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.json else None))
    return 0


def cmd_trend_radar(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    new_signals = fetch_hacker_news_trends(
        out_path=out_path,
        kinds=args.kind,
        max_ids_per_kind=args.max_ids_per_kind,
        min_score=args.min_score,
        min_comments=args.min_comments,
    )
    all_signals = sorted(
        load_trend_signals(out_path),
        key=lambda signal: signal.engagement_score,
        reverse=True,
    )
    markdown = trend_to_markdown(all_signals, limit=args.markdown_limit)
    Path(args.markdown_out).write_text(markdown, encoding="utf-8")
    print(
        "summary "
        + json.dumps(
            {
                "new_signals": len(new_signals),
                "total_signals": len(all_signals),
                "out": args.out,
                "markdown": args.markdown_out,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_gemini_scout(args: argparse.Namespace) -> int:
    provider = GeminiGroundedSearchProvider(model=args.model or None)
    candidates = provider.scout_today_ai_news(limit=args.limit)
    written = []
    rejected = []
    for candidate in candidates:
        verification = verify_search_candidate(candidate)
        if verification.status != "verified":
            rejected.append({"url": candidate.url, "status": verification.status})
            continue
        signal = add_radar_signal(
            Path(args.out),
            source_type="gemini_scout",
            source_name=verification.source_name,
            title=verification.title or candidate.title,
            url=verification.verified_url or candidate.url,
            published_at=verification.published_at,
            engagement_score=args.engagement_score,
            summary=verification.summary or candidate.summary,
            topic_hint=candidate.title,
            why_it_matters=candidate.why_it_matters,
            why_engaged="",
            notes="Gemini Scout diário; fonte e data verificadas localmente.",
            status="verified",
            require_recent=True,
        )
        written.append(signal.to_record())
    print(
        "summary "
        + json.dumps(
            {
                "candidates": len(candidates),
                "verified_written": len(written),
                "rejected": len(rejected),
                "out": args.out,
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_editorial_automation(args: argparse.Namespace) -> int:
    load_local_env()
    data_dir = Path(args.data_dir)
    run = EditorialAutomationService(
        repo_root=data_dir.parent,
        data_dir=data_dir,
    ).run(limit=args.limit, scout=not args.no_scout)
    print("summary " + json.dumps(run.to_record(), ensure_ascii=False))
    return 0 if run.status in {"completed", "partial"} else 1


def cmd_daily_run(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    raw_path = data_dir / "raw_articles.jsonl"
    processed_path = data_dir / "processed_items.jsonl"
    drafts_path = data_dir / "content_drafts.jsonl"
    briefing_path = data_dir / "daily_briefing.md"
    review_path = data_dir / "review_queue.md"
    drafts_review_path = data_dir / "drafts_review.md"
    exports_dir = data_dir / "exports"
    learning_weights_path = Path(args.learning_weights)

    cmd_init_data(argparse.Namespace(data_dir=str(data_dir)))
    cmd_ingest(
        argparse.Namespace(
            sources=args.sources,
            out=str(raw_path),
            limit_per_source=args.limit_per_source,
            title_threshold=args.title_threshold,
        )
    )
    cmd_briefing(
        argparse.Namespace(
            articles=str(raw_path),
            out=str(briefing_path),
            limit=args.review_limit,
        )
    )
    cmd_learn(
        argparse.Namespace(
            processed=str(processed_path),
            drafts=str(drafts_path),
            performance=str(data_dir / "content_performance.jsonl"),
            out=str(learning_weights_path),
            min_samples=args.learning_min_samples,
        )
    )
    cmd_classify(
        argparse.Namespace(
            articles=str(raw_path),
            out=str(processed_path),
            usage_ledger=str(data_dir / "usage_ledger.jsonl"),
            mode=args.classify_mode,
            model=args.model,
            limit=args.classify_limit,
            max_output_tokens=args.max_output_tokens,
            monthly_budget_usd=args.monthly_budget_usd,
            learning_weights=str(learning_weights_path),
        )
    )
    cmd_review(
        argparse.Namespace(
            articles=str(raw_path),
            processed=str(processed_path),
            out=str(review_path),
            limit=args.review_limit,
        )
    )
    cmd_draft(
        argparse.Namespace(
            articles=str(raw_path),
            processed=str(processed_path),
            out=str(drafts_path),
            limit=args.draft_limit,
            status=["needs_review", "approved_for_draft"],
        )
    )
    cmd_export_drafts(
        argparse.Namespace(
            drafts=str(drafts_path),
            out=str(drafts_review_path),
            channel="",
            format="",
            limit=args.drafts_export_limit,
        )
    )
    cmd_export_csv(
        argparse.Namespace(
            sources=args.sources,
            articles=str(raw_path),
            processed=str(processed_path),
            drafts=str(drafts_path),
            out_dir=str(exports_dir),
        )
    )
    print(
        "daily_run "
        + json.dumps(
            {
                "briefing": str(briefing_path),
                "review_queue": str(review_path),
                "drafts_review": str(drafts_review_path),
                "exports": str(exports_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ptia-engine")
    subparsers = parser.add_subparsers(required=True)

    init_data = subparsers.add_parser("init-data", help="Create local data files.")
    init_data.add_argument("--data-dir", default="data")
    init_data.set_defaults(func=cmd_init_data)

    ingest = subparsers.add_parser("ingest", help="Fetch active RSS sources.")
    ingest.add_argument("--sources", default="config/sources.sample.json")
    ingest.add_argument("--out", default="data/raw_articles.jsonl")
    ingest.add_argument("--limit-per-source", type=int, default=20)
    ingest.add_argument("--title-threshold", type=float, default=0.88)
    ingest.set_defaults(func=cmd_ingest)

    briefing = subparsers.add_parser("briefing", help="Generate a local markdown briefing.")
    briefing.add_argument("--articles", default="data/raw_articles.jsonl")
    briefing.add_argument("--out", default="data/daily_briefing.md")
    briefing.add_argument("--limit", type=int, default=10)
    briefing.set_defaults(func=cmd_briefing)

    classify = subparsers.add_parser("classify", help="Classify raw articles into processed items.")
    classify.add_argument("--articles", default="data/raw_articles.jsonl")
    classify.add_argument("--out", default="data/processed_items.jsonl")
    classify.add_argument("--usage-ledger", default="data/usage_ledger.jsonl")
    classify.add_argument("--mode", choices=["heuristic", "openai"], default="heuristic")
    classify.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    classify.add_argument("--limit", type=int, default=20)
    classify.add_argument("--max-output-tokens", type=int, default=500)
    classify.add_argument("--learning-weights", default="config/learning_weights.json")
    classify.add_argument(
        "--monthly-budget-usd",
        type=float,
        default=float(os.getenv("OPENAI_MONTHLY_BUDGET_USD", "20")),
    )
    classify.set_defaults(func=cmd_classify)

    review = subparsers.add_parser("review", help="Generate a local human review queue.")
    review.add_argument("--articles", default="data/raw_articles.jsonl")
    review.add_argument("--processed", default="data/processed_items.jsonl")
    review.add_argument("--out", default="data/review_queue.md")
    review.add_argument("--limit", type=int, default=10)
    review.set_defaults(func=cmd_review)

    draft = subparsers.add_parser("draft", help="Generate template drafts for review candidates.")
    draft.add_argument("--articles", default="data/raw_articles.jsonl")
    draft.add_argument("--processed", default="data/processed_items.jsonl")
    draft.add_argument("--out", default="data/content_drafts.jsonl")
    draft.add_argument("--limit", type=int, default=5)
    draft.add_argument(
        "--status",
        nargs="+",
        default=["needs_review"],
        help="Editorial statuses eligible for draft generation.",
    )
    draft.set_defaults(func=cmd_draft)

    ai_drafts = subparsers.add_parser("ai-drafts", help="Generate final editorial drafts with an LLM provider.")
    ai_drafts.add_argument("--articles", default="data/raw_articles.jsonl")
    ai_drafts.add_argument("--processed", default="data/processed_items.jsonl")
    ai_drafts.add_argument("--out", default="data/content_drafts.jsonl")
    ai_drafts.add_argument("--usage-ledger", default="data/usage_ledger.jsonl")
    ai_drafts.add_argument("--status", nargs="+", default=["approved_for_draft"])
    ai_drafts.add_argument("--limit", type=int, default=3)
    ai_drafts.add_argument(
        "--provider",
        choices=["template", "gemini", "ollama", "local", "openai"],
        default=os.getenv("PTIA_LLM_PROVIDER", "template"),
        help="LLM provider. Use template for zero-cost local drafts.",
    )
    ai_drafts.add_argument("--model", default="", help="Provider model. Defaults come from env or provider preset.")
    ai_drafts.add_argument("--max-output-tokens", type=int, default=1800)
    ai_drafts.add_argument(
        "--monthly-budget-usd",
        type=float,
        default=float(os.getenv("OPENAI_MONTHLY_BUDGET_USD", "20")),
    )
    ai_drafts.set_defaults(func=cmd_ai_drafts)

    assets = subparsers.add_parser("assets", help="Generate PTIA SVG assets for social drafts.")
    assets.add_argument("--drafts", default="data/content_drafts.jsonl")
    assets.add_argument("--processed", default="data/processed_items.jsonl")
    assets.add_argument("--out-dir", default="data/assets")
    assets.add_argument("--status", nargs="+", default=["needs_edit", "approved", "draft"])
    assets.add_argument("--channel", nargs="+", default=["linkedin", "instagram"])
    assets.add_argument("--limit", type=int, default=12)
    assets.set_defaults(func=cmd_assets)

    export_drafts = subparsers.add_parser("export-drafts", help="Export drafts to markdown.")
    export_drafts.add_argument("--drafts", default="data/content_drafts.jsonl")
    export_drafts.add_argument("--out", default="data/drafts_review.md")
    export_drafts.add_argument("--channel", default="")
    export_drafts.add_argument("--format", default="")
    export_drafts.add_argument("--limit", type=int, default=20)
    export_drafts.set_defaults(func=cmd_export_drafts)

    export_csv = subparsers.add_parser("export-csv", help="Export local data to Airtable-friendly CSV files.")
    export_csv.add_argument("--sources", default="config/sources.sample.json")
    export_csv.add_argument("--articles", default="data/raw_articles.jsonl")
    export_csv.add_argument("--processed", default="data/processed_items.jsonl")
    export_csv.add_argument("--drafts", default="data/content_drafts.jsonl")
    export_csv.add_argument("--out-dir", default="data/exports")
    export_csv.set_defaults(func=cmd_export_csv)

    item_status = subparsers.add_parser("item-status", help="Update a processed item editorial status.")
    item_status.add_argument("--processed", default="data/processed_items.jsonl")
    item_status.add_argument("--item-id", required=True)
    item_status.add_argument("--status", required=True)
    item_status.add_argument("--notes", default="")
    item_status.set_defaults(func=cmd_item_status)

    draft_status = subparsers.add_parser("draft-status", help="Update a content draft status.")
    draft_status.add_argument("--drafts", default="data/content_drafts.jsonl")
    draft_status.add_argument("--draft-id", required=True)
    draft_status.add_argument("--status", required=True)
    draft_status.add_argument("--scheduled-time", default="")
    draft_status.add_argument("--published-url", default="")
    draft_status.add_argument("--buffer-post-id", default="")
    draft_status.set_defaults(func=cmd_draft_status)

    export_schedule = subparsers.add_parser("export-schedule", help="Export approved drafts for scheduling.")
    export_schedule.add_argument("--drafts", default="data/content_drafts.jsonl")
    export_schedule.add_argument("--out", default="data/scheduling_queue.csv")
    export_schedule.add_argument("--status", nargs="+", default=["approved"])
    export_schedule.add_argument("--channel", nargs="+", default=["linkedin", "instagram"])
    export_schedule.set_defaults(func=cmd_export_schedule)

    learn = subparsers.add_parser("learn", help="Generate editorial learning weights from post performance.")
    learn.add_argument("--processed", default="data/processed_items.jsonl")
    learn.add_argument("--drafts", default="data/content_drafts.jsonl")
    learn.add_argument("--performance", default="data/content_performance.jsonl")
    learn.add_argument("--final-posts", default="data/final_posts.jsonl")
    learn.add_argument("--out", default="config/learning_weights.json")
    learn.add_argument("--min-samples", type=int, default=3)
    learn.set_defaults(func=cmd_learn)

    instagram_insights = subparsers.add_parser(
        "instagram-insights",
        help="Import Instagram post metrics from Meta Graph API into content_performance.jsonl.",
    )
    instagram_insights.add_argument("--final-posts", default="data/final_posts.jsonl")
    instagram_insights.add_argument("--performance", default="data/content_performance.jsonl")
    instagram_insights.add_argument("--limit", type=int, default=25)
    instagram_insights.set_defaults(func=cmd_instagram_insights)

    linkedin_insights = subparsers.add_parser(
        "linkedin-insights",
        help="Import a LinkedIn page analytics .xls export into content_performance.jsonl.",
    )
    linkedin_insights.add_argument("--export", required=True)
    linkedin_insights.add_argument("--final-posts", default="data/final_posts.jsonl")
    linkedin_insights.add_argument("--performance", default="data/content_performance.jsonl")
    linkedin_insights.add_argument("--match-threshold", type=float, default=76.0)
    linkedin_insights.set_defaults(func=cmd_linkedin_insights)

    growth_report = subparsers.add_parser(
        "growth-report",
        help="Summarize content performance and growth recommendations without changing data.",
    )
    growth_report.add_argument("--final-posts", default="data/final_posts.jsonl")
    growth_report.add_argument("--performance", default="data/content_performance.jsonl")
    growth_report.add_argument("--top-limit", type=int, default=8)
    growth_report.add_argument("--min-samples", type=int, default=3)
    growth_report.add_argument("--out", default="", help="Optional path to write the report.")
    growth_report.add_argument("--json", action="store_true", help="Print/write the report as JSON.")
    growth_report.set_defaults(func=cmd_growth_report)

    ai_visibility = subparsers.add_parser(
        "ai-visibility-report",
        help="Audit AI-search readiness of the static PTIA site without changing data.",
    )
    ai_visibility.add_argument("--site-dir", default="site")
    ai_visibility.add_argument("--out", default="", help="Optional path to write the report.")
    ai_visibility.add_argument("--json", action="store_true", help="Print/write the report as JSON.")
    ai_visibility.set_defaults(func=cmd_ai_visibility_report)

    knowledge_update = subparsers.add_parser(
        "knowledge-update",
        help="Rebuild the weekly PTIA indexes, tools, prompts and glossary pages.",
    )
    knowledge_update.add_argument("--root", default=".")
    knowledge_update.add_argument("--json", action="store_true")
    knowledge_update.set_defaults(func=cmd_knowledge_update)

    trend_radar = subparsers.add_parser("trend-radar", help="Fetch external AI engagement signals.")
    trend_radar.add_argument("--out", default="data/trend_signals.jsonl")
    trend_radar.add_argument("--markdown-out", default="data/trend_radar.md")
    trend_radar.add_argument("--kind", nargs="+", default=["topstories", "beststories"])
    trend_radar.add_argument("--max-ids-per-kind", type=int, default=80)
    trend_radar.add_argument("--min-score", type=int, default=80)
    trend_radar.add_argument("--min-comments", type=int, default=20)
    trend_radar.add_argument("--markdown-limit", type=int, default=20)
    trend_radar.set_defaults(func=cmd_trend_radar)

    gemini_scout = subparsers.add_parser("gemini-scout", help="Fetch grounded Gemini AI news candidates.")
    gemini_scout.add_argument("--out", default="data/radar_signals.jsonl")
    gemini_scout.add_argument("--limit", type=int, default=8)
    gemini_scout.add_argument("--model", default=os.getenv("GEMINI_SEARCH_MODEL", "gemini-2.5-flash"))
    gemini_scout.add_argument("--engagement-score", type=int, default=55)
    gemini_scout.set_defaults(func=cmd_gemini_scout)

    editorial_auto = subparsers.add_parser(
        "editorial-auto",
        help="Prepare complete editorial packages in A Rever without scheduling anything.",
    )
    editorial_auto.add_argument("--data-dir", default="data")
    editorial_auto.add_argument("--limit", type=int, default=6)
    editorial_auto.add_argument(
        "--no-scout",
        action="store_true",
        help="Use only signals already verified in the local radar.",
    )
    editorial_auto.set_defaults(func=cmd_editorial_automation)

    add_signal = subparsers.add_parser("add-signal", help="Add a news/social signal to the new radar.")
    add_signal.add_argument("--out", default="data/radar_signals.jsonl")
    add_signal.add_argument("--source-type", required=True, choices=["news", "instagram", "linkedin", "hn", "manual"])
    add_signal.add_argument("--source-name", required=True)
    add_signal.add_argument("--title", required=True)
    add_signal.add_argument("--url", required=True)
    add_signal.add_argument("--published-at", default="")
    add_signal.add_argument("--max-age-days", type=int, default=5)
    add_signal.add_argument("--engagement-score", type=int, default=0)
    add_signal.add_argument("--summary", default="")
    add_signal.add_argument("--topic-hint", default="")
    add_signal.add_argument("--why-it-matters", default="")
    add_signal.add_argument("--why-engaged", default="")
    add_signal.add_argument("--notes", default="")
    add_signal.set_defaults(func=cmd_add_signal)

    signal_status = subparsers.add_parser("signal-status", help="Update a radar signal status.")
    signal_status.add_argument("--signals", default="data/radar_signals.jsonl")
    signal_status.add_argument("--signal-id", required=True)
    signal_status.add_argument("--status", required=True)
    signal_status.add_argument("--notes", default="")
    signal_status.set_defaults(func=cmd_signal_status)

    add_topic = subparsers.add_parser("add-topic", help="Create a curated editorial topic.")
    add_topic.add_argument("--out", default="data/editorial_topics.jsonl")
    add_topic.add_argument("--title", required=True)
    add_topic.add_argument("--thesis", required=True)
    add_topic.add_argument("--portugal-angle", required=True)
    add_topic.add_argument("--audience", required=True)
    add_topic.add_argument("--signal-ids", default="")
    add_topic.add_argument("--urgency-score", type=int, default=0)
    add_topic.set_defaults(func=cmd_add_topic)

    topic_status = subparsers.add_parser("topic-status", help="Update an editorial topic status.")
    topic_status.add_argument("--topics", default="data/editorial_topics.jsonl")
    topic_status.add_argument("--topic-id", required=True)
    topic_status.add_argument("--status", required=True)
    topic_status.add_argument("--notes", default="")
    topic_status.set_defaults(func=cmd_topic_status)

    add_final_post = subparsers.add_parser("add-final-post", help="Create a final post package.")
    add_final_post.add_argument("--out", default="data/final_posts.jsonl")
    add_final_post.add_argument("--topic-id", required=True)
    add_final_post.add_argument("--channel", required=True, choices=["linkedin", "instagram", "x", "site", "newsletter"])
    add_final_post.add_argument("--title", required=True)
    add_final_post.add_argument("--body", required=True)
    add_final_post.add_argument("--hashtags", default="")
    add_final_post.add_argument("--image-prompt", default="")
    add_final_post.add_argument("--source-urls", default="")
    add_final_post.add_argument("--image-path", default="")
    add_final_post.set_defaults(func=cmd_add_final_post)

    final_post_status = subparsers.add_parser("final-post-status", help="Update a final post package status.")
    final_post_status.add_argument("--posts", default="data/final_posts.jsonl")
    final_post_status.add_argument("--post-id", required=True)
    final_post_status.add_argument("--status", required=True)
    final_post_status.add_argument("--scheduled-time", default="")
    final_post_status.add_argument("--published-url", default="")
    final_post_status.add_argument("--image-path", default="")
    final_post_status.set_defaults(func=cmd_final_post_status)

    daily_run = subparsers.add_parser("daily-run", help="Run the local daily editorial pipeline.")
    daily_run.add_argument("--sources", default="config/sources.sample.json")
    daily_run.add_argument("--data-dir", default="data")
    daily_run.add_argument("--limit-per-source", type=int, default=5)
    daily_run.add_argument("--title-threshold", type=float, default=0.88)
    daily_run.add_argument("--classify-mode", choices=["heuristic", "openai"], default="heuristic")
    daily_run.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    daily_run.add_argument("--classify-limit", type=int, default=50)
    daily_run.add_argument("--max-output-tokens", type=int, default=500)
    daily_run.add_argument("--learning-weights", default="config/learning_weights.json")
    daily_run.add_argument("--learning-min-samples", type=int, default=3)
    daily_run.add_argument(
        "--monthly-budget-usd",
        type=float,
        default=float(os.getenv("OPENAI_MONTHLY_BUDGET_USD", "20")),
    )
    daily_run.add_argument("--review-limit", type=int, default=10)
    daily_run.add_argument("--draft-limit", type=int, default=5)
    daily_run.add_argument("--drafts-export-limit", type=int, default=20)
    daily_run.set_defaults(func=cmd_daily_run)

    dashboard = subparsers.add_parser("dashboard", help="Run the local PTIA editorial dashboard.")
    dashboard.add_argument("--data-dir", default="data")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.set_defaults(func=cmd_dashboard)

    schedule_day = subparsers.add_parser(
        "schedule-day",
        help="Dry-run the daily scheduling preflight without changing posts, Git, or Buffer.",
    )
    schedule_day.add_argument("--date", required=True, help="Target day in YYYY-MM-DD format.")
    schedule_day.add_argument("--data-dir", default="data")
    schedule_day.add_argument(
        "--plan",
        default="",
        help="Optional JSON schedule plan with topic_id and scheduled_time entries.",
    )
    schedule_day.add_argument(
        "--execution-plan",
        action="store_true",
        help="Print the side-effect-free execution plan, including Instagram carousel grouping.",
    )
    schedule_day.add_argument(
        "--simulate-execute",
        action="store_true",
        help="Run the execution plan against a noop backend. Requires --confirm and never calls Buffer or Git.",
    )
    schedule_day.add_argument(
        "--execute-real",
        action="store_true",
        help="Execute against real dashboard operations. Requires --confirm and explicit capability flags.",
    )
    schedule_day.add_argument("--publish-assets", action="store_true", help="Allow publishing/preparing public media assets.")
    schedule_day.add_argument("--send-buffer", action="store_true", help="Allow calls that create Buffer posts.")
    schedule_day.add_argument("--write-site-feed", action="store_true", help="Allow writing/syncing static site feed files.")
    schedule_day.add_argument("--confirm", default="", help="Required date confirmation for execution modes.")
    schedule_day.add_argument("--audit-log", default="", help="Optional JSONL audit log for simulated execution.")
    schedule_day.add_argument("--json", action="store_true", help="Print the preflight as JSON.")
    schedule_day.set_defaults(func=cmd_schedule_day)

    linkedin_comments = subparsers.add_parser("linkedin-comments", help="Run the automated LinkedIn commenting pipeline.")
    linkedin_comments.set_defaults(func=cmd_linkedin_comments)

    return parser


def main() -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
