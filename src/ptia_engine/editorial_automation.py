from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ptia_engine.cloud_state import persist_cloud_state_file, sync_cloud_state_file
from ptia_engine.editorial_board import update_final_post_status, update_signal_status, update_topic_status
from ptia_engine.editorial_quality import (
    EditorialFactPack,
    build_fact_pack,
    validate_fact_pack,
    validate_package,
)
from ptia_engine.editorial_scoring import CandidateScore, select_portfolio
from ptia_engine.models import FinalPost, RadarSignal, utc_now_iso
from ptia_engine.learning import load_learning_weights
from ptia_engine.repositories import EditorialTopicRepository, FinalPostRepository, RadarSignalRepository
from ptia_engine.search_providers import GeminiGroundedSearchProvider
from ptia_engine.services.image_generation import (
    EditorialImageGenerator,
    OpenAIEditorialImageGenerator,
)
from ptia_engine.source_verifier import verify_search_candidate
from ptia_engine.storage import load_final_posts
from ptia_engine.use_cases import BuildFinalPackUseCase
from ptia_engine.editorial_board import add_radar_signal


_EVENT_STOPWORDS = {
    "com",
    "das",
    "dos",
    "para",
    "por",
    "que",
    "the",
}


def _event_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if (len(token) > 2 or token.isdigit()) and token not in _EVENT_STOPWORDS
    }


def _same_event(left: RadarSignal, right: RadarSignal) -> bool:
    left_tokens = _event_tokens(f"{left.title} {left.summary}")
    right_tokens = _event_tokens(f"{right.title} {right.summary}")
    if not left_tokens or not right_tokens:
        return False
    left_numbers = {token for token in left_tokens if token.isdigit()}
    right_numbers = {token for token in right_tokens if token.isdigit()}
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return False
    overlap = len(left_tokens & right_tokens)
    return overlap / min(len(left_tokens), len(right_tokens)) >= 0.58


@dataclass(slots=True)
class EditorialAutomationRun:
    run_id: str
    status: str
    requested_packages: int
    discovered: int = 0
    verified: int = 0
    selected_signal_ids: list[str] = field(default_factory=list)
    alternative_signal_ids: list[str] = field(default_factory=list)
    created_topic_ids: list[str] = field(default_factory=list)
    rejected_signal_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str = ""

    def to_record(self) -> dict:
        return asdict(self)


def _read_records(path: Path) -> list[dict]:
    sync_cloud_state_file(path)
    if not path.exists():
        return []
    records = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            records.append(json.loads(raw))
    return records


def _append_record(path: Path, record: dict) -> None:
    sync_cloud_state_file(path, force=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    persist_cloud_state_file(path)


class EditorialAutomationService:
    """Prepare complete editorial packages without crossing the human approval boundary."""

    def __init__(
        self,
        *,
        repo_root: Path,
        data_dir: Path,
        search_provider: GeminiGroundedSearchProvider | None = None,
        image_generator: EditorialImageGenerator | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.data_dir = data_dir
        self.signal_repo = RadarSignalRepository(data_dir / "radar_signals.jsonl")
        self.topic_repo = EditorialTopicRepository(data_dir / "editorial_topics.jsonl")
        self.post_repo = FinalPostRepository(data_dir / "final_posts.jsonl")
        self.channels_path = data_dir / "buffer_channels.json"
        self.fact_packs_path = data_dir / "editorial_fact_packs.jsonl"
        self.runs_path = data_dir / "editorial_automation_runs.jsonl"
        configured_assets_dir = os.getenv("PTIA_EDITORIAL_ASSETS_DIR", "").strip()
        self.assets_dir = (
            Path(configured_assets_dir)
            if configured_assets_dir
            else data_dir / "final_assets"
        )
        self.search_provider = search_provider or GeminiGroundedSearchProvider()
        self.image_generator = image_generator or OpenAIEditorialImageGenerator()

    def _discover(self, limit: int) -> tuple[int, int]:
        if not self.search_provider.available:
            return 0, 0
        candidates = []
        for attempt in range(2):
            try:
                candidates = self.search_provider.scout_today_ai_news(limit=max(limit, 8))
                break
            except (TimeoutError, OSError):
                if attempt == 1:
                    raise
                time.sleep(2)
        verified = 0
        for candidate in candidates:
            verification = verify_search_candidate(candidate)
            if verification.status != "verified":
                continue
            try:
                published_date = date.fromisoformat(verification.published_at[:10])
            except ValueError:
                continue
            if published_date < date.today() - timedelta(days=1):
                continue
            if published_date < date.today() and not candidate.trend_evidence.strip():
                continue
            trend_score = candidate.trend_score or int(candidate.confidence * 100)
            trend_note = (
                f" Evidência de momentum: {candidate.trend_evidence}"
                if candidate.trend_evidence
                else ""
            )
            add_radar_signal(
                self.signal_repo.file_path,
                source_type="gemini_scout",
                source_name=verification.source_name,
                title=verification.title or candidate.title,
                url=verification.verified_url or candidate.url,
                published_at=verification.published_at,
                engagement_score=max(55, trend_score),
                summary=verification.summary or candidate.summary,
                topic_hint=candidate.title,
                why_it_matters=candidate.why_it_matters,
                notes=(
                    "Descoberto pela pesquisa grounded de notícias trending; "
                    f"fonte e data verificadas.{trend_note}"
                ),
                status="verified",
                require_recent=True,
            )
            verified += 1
        return len(candidates), verified

    def _existing_signal_ids(self) -> set[str]:
        topics = self.topic_repo.load_all()
        posts = self.post_repo.load_all()
        active_topic_ids = {
            post.topic_id
            for post in posts
            if post.status in {"needs_final_review", "approved_for_schedule", "scheduled", "published"}
        }
        return {
            signal_id
            for topic in topics
            if topic.topic_id in active_topic_ids
            for signal_id in topic.source_signal_ids
        }

    def _save_fact_pack(self, pack: EditorialFactPack) -> None:
        existing = {
            str(record.get("fact_pack_id"))
            for record in _read_records(self.fact_packs_path)
        }
        if pack.fact_pack_id not in existing:
            _append_record(self.fact_packs_path, pack.to_record())

    def _generate_images(self, posts: list[FinalPost]) -> tuple[list[FinalPost], list[str]]:
        if not posts:
            return [], []
        reference = next(
            (post for post in posts if post.channel == "instagram"),
            posts[0],
        )
        generated = self.image_generator.generate(reference, self.assets_dir)
        updated = []
        for post in posts:
            updated.append(
                update_final_post_status(
                    self.post_repo.file_path,
                    post.post_id,
                    post.status,
                    image_path=str(generated.path),
                    image_status="needs_review" if generated.fallback else "generated",
                )
            )
        warnings = [generated.warning] if generated.warning else []
        return updated, warnings

    def _reject_failed_package(self, signal: RadarSignal, posts: list[FinalPost], issues: list[str]) -> None:
        reason = "Quality gates: " + "; ".join(issues)
        for post in posts:
            update_final_post_status(self.post_repo.file_path, post.post_id, "rejected")
        topic_ids = {post.topic_id for post in posts}
        for topic_id in topic_ids:
            update_topic_status(self.topic_repo.file_path, topic_id, "rejected", reason)
        update_signal_status(self.signal_repo.file_path, signal.signal_id, "rejected", reason)

    def _build_candidate(self, signal: RadarSignal, score: CandidateScore) -> tuple[str | None, list[str]]:
        pack = build_fact_pack(signal)
        fact_report = validate_fact_pack(pack)
        if not fact_report.passed:
            update_signal_status(
                self.signal_repo.file_path,
                signal.signal_id,
                "rejected",
                "Fact Pack bloqueado: " + "; ".join(fact_report.issues),
            )
            return None, fact_report.issues
        self._save_fact_pack(pack)
        update_signal_status(
            self.signal_repo.file_path,
            signal.signal_id,
            "selected",
            f"Selecionado automaticamente: score {score.total:.2f}; {', '.join(score.explanation)}",
        )
        result = BuildFinalPackUseCase(
            signal_repo=self.signal_repo,
            topic_repo=self.topic_repo,
            post_repo=self.post_repo,
            buffer_channels_path=self.channels_path,
        ).execute(signal.signal_id)
        posts, image_warnings = self._generate_images(result["posts"])
        quality = validate_package(pack, posts, require_images=True)
        if not quality.passed:
            self._reject_failed_package(signal, posts, quality.issues)
            return None, quality.issues
        warnings = [*image_warnings, *quality.warnings]
        if warnings:
            topic = result["topic"]
            update_topic_status(
                self.topic_repo.file_path,
                topic.topic_id,
                topic.status,
                "Avisos automáticos: " + "; ".join(warnings),
            )
        return result["topic"].topic_id, warnings

    def _pending_topic_ids(self) -> set[str]:
        return {
            post.topic_id
            for post in self.post_repo.load_all()
            if post.status == "needs_final_review"
        }

    def run(
        self,
        *,
        limit: int = 4,
        scout: bool = True,
        respect_pending_capacity: bool = True,
    ) -> EditorialAutomationRun:
        requested = max(1, limit)
        create_count = requested
        if respect_pending_capacity:
            create_count = max(0, requested - len(self._pending_topic_ids()))
        run = EditorialAutomationRun(
            run_id=f"editorial_{utc_now_iso().replace(':', '').replace('+', '_')}",
            status="running",
            requested_packages=requested,
        )
        try:
            if create_count == 0:
                run.status = "completed"
                run.warnings.append(
                    f"A fila A Rever já tem {requested} ou mais pacotes; nada foi criado."
                )
                run.completed_at = utc_now_iso()
                _append_record(self.runs_path, run.to_record())
                return run
            if scout:
                run.discovered, run.verified = self._discover(create_count * 3)
            signals = self.signal_repo.load_all()
            selected, alternatives = select_portfolio(
                signals,
                limit=max(create_count * 2, create_count + 3),
                excluded_signal_ids=self._existing_signal_ids(),
                learning_weights=load_learning_weights(
                    self.repo_root / "config" / "learning_weights.json"
                ),
            )
            run.alternative_signal_ids = [signal.signal_id for signal, _score in alternatives[:12]]
            attempted_urls: set[str] = set()
            attempted_events: list[RadarSignal] = []
            for signal, score in [*selected, *alternatives]:
                if len(run.created_topic_ids) >= create_count:
                    break
                if signal.signal_id in run.selected_signal_ids:
                    continue
                canonical_url = signal.url.strip().casefold()
                if canonical_url and canonical_url in attempted_urls:
                    continue
                if canonical_url:
                    attempted_urls.add(canonical_url)
                if any(_same_event(signal, previous) for previous in attempted_events):
                    continue
                attempted_events.append(signal)
                run.selected_signal_ids.append(signal.signal_id)
                try:
                    topic_id, warnings = self._build_candidate(signal, score)
                except Exception as exc:
                    run.errors.append(f"{signal.signal_id}: {exc}")
                    continue
                if topic_id:
                    run.created_topic_ids.append(topic_id)
                    run.warnings.extend(f"{signal.signal_id}: {warning}" for warning in warnings)
                else:
                    run.rejected_signal_ids.append(signal.signal_id)
            run.status = "completed" if len(run.created_topic_ids) >= create_count else "partial"
        except Exception as exc:
            run.status = "failed"
            run.errors.append(str(exc))
        run.completed_at = utc_now_iso()
        _append_record(self.runs_path, run.to_record())
        return run

    def replace_topic(self, topic_id: str) -> EditorialAutomationRun:
        posts = [
            post
            for post in load_final_posts(self.post_repo.file_path)
            if post.topic_id == topic_id and post.status == "needs_final_review"
        ]
        if not posts:
            raise ValueError("O pacote já não está em A Rever.")
        for post in posts:
            update_final_post_status(self.post_repo.file_path, post.post_id, "rejected")
        update_topic_status(
            self.topic_repo.file_path,
            topic_id,
            "rejected",
            "Editor pediu uma notícia alternativa.",
        )
        return self.run(limit=1, scout=False, respect_pending_capacity=False)


def load_automation_runs(path: Path) -> list[dict]:
    return _read_records(path)
