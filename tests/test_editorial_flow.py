import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock
from collections import namedtuple

from ptia_engine.models import RadarSignal, EditorialTopic, FinalPost
from ptia_engine.repositories import RadarSignalRepository, EditorialTopicRepository, FinalPostRepository
from ptia_engine.use_cases import (
    BuildFinalPackUseCase,
    ApprovePackageUseCase,
    EditPolishPostUseCase,
    GenerateNoopScheduleUseCase,
)
from ptia_engine.editorial_board import add_radar_signal


class EditorialFlowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        
        self.signals_path = self.root / "radar_signals.jsonl"
        self.topics_path = self.root / "editorial_topics.jsonl"
        self.posts_path = self.root / "final_posts.jsonl"
        self.channels_path = self.root / "buffer_channels.json"
        
        # Write dummy channels config
        self.channels_path.write_text('{"disabled_channels": [], "channels": {"linkedin": "li_123", "instagram": "ig_123", "x": "x_123"}}', encoding="utf-8")
        
        # Instantiate repositories
        self.signal_repo = RadarSignalRepository(self.signals_path)
        self.topic_repo = EditorialTopicRepository(self.topics_path)
        self.post_repo = FinalPostRepository(self.posts_path)

        # Mock Gemini polish service
        self.gemini_patcher = patch("ptia_engine.use_cases.curation.GeminiGroundedSearchProvider")
        self.mock_gemini_cls = self.gemini_patcher.start()
        self.mock_provider = self.mock_gemini_cls.return_value
        self.mock_provider.available = True
        
        Polished = namedtuple("Polished", ["title", "body", "hashtags", "rationale"])
        self.mock_provider.polish_final_post.return_value = Polished(
            title="Polished Title",
            body="Polished body text.",
            hashtags="#Polished #Hashtags",
            rationale="Mock rationale",
        )

    def tearDown(self):
        self.gemini_patcher.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_manual_selected_url_title_builds_review_pack(self):
        from ptia_engine.editorial_board import update_signal_status

        url = "https://www.cisa.gov/news-events/news/five-eyes-cyber-security-agencies-statement"
        signal = add_radar_signal(
            self.signals_path,
            source_type="news",
            source_name="Unverified",
            title=url,
            url=url,
            published_at="",
            summary="",
            topic_hint="",
            why_it_matters="",
            notes="Aprovado manualmente pelo editor",
            require_recent=False,
        )
        update_signal_status(self.signals_path, signal.signal_id, "selected")

        build_use_case = BuildFinalPackUseCase(
            signal_repo=self.signal_repo,
            topic_repo=self.topic_repo,
            post_repo=self.post_repo,
            buffer_channels_path=self.channels_path,
        )
        result = build_use_case.execute(signal.signal_id)

        self.assertEqual(result["topic"].status, "approved_for_final")
        self.assertEqual(result["topic"].title, "Five eyes cyber security agencies statement")
        self.assertFalse(result["topic"].title.startswith("http"))
        self.assertFalse(result["topic"].thesis.startswith("http"))
        self.assertEqual(len(result["posts"]), 4)
        self.assertTrue(all(post.status == "needs_final_review" for post in result["posts"]))
        self.assertEqual(self.signal_repo.get_by_id(signal.signal_id).status, "used")

    def test_manual_selected_news_url_strips_date_and_tracking_slug(self):
        from ptia_engine.editorial_board import update_signal_status

        url = "https://sicnoticias.pt/especiais/inteligencia-artificial/2025-11-12-video-e-se-cada-aluno-tivesse-um-tutor-de-inteligencia-artificial--ideia-foi-lancada-pelo-governo-344f04a8"
        signal = add_radar_signal(
            self.signals_path,
            source_type="news",
            source_name="SIC Noticias",
            title=url,
            url=url,
            published_at="2025-11-12",
            summary="",
            topic_hint="",
            why_it_matters="",
            notes="Aprovado manualmente pelo editor",
            require_recent=False,
        )
        update_signal_status(self.signals_path, signal.signal_id, "selected")

        result = BuildFinalPackUseCase(
            signal_repo=self.signal_repo,
            topic_repo=self.topic_repo,
            post_repo=self.post_repo,
            buffer_channels_path=self.channels_path,
        ).execute(signal.signal_id)

        self.assertEqual(
            result["topic"].title,
            "Video e se cada aluno tivesse um tutor de inteligencia artificial ideia foi lancada pelo governo",
        )
        self.assertFalse(result["topic"].thesis.startswith("http"))
        self.assertTrue(all(not post.title.startswith("http") for post in result["posts"]))

    def test_complete_editorial_curation_flow(self):
        # 1. Sinal entra (Radar Signal added)
        signal = add_radar_signal(
            self.signals_path,
            source_type="news",
            source_name="Wired",
            title="A revolução dos chips em Portugal",
            url="https://wired.com/chips-pt",
            published_at="2026-06-03T09:00:00+00:00",
            summary="Os novos chips de IA chegam ao mercado europeu com grande tração.",
            topic_hint="revolução chips",
            why_it_matters="Portugal está a investir no setor.",
            notes="Teste inicial",
            require_recent=False,
        )
        
        self.assertEqual(signal.status, "new")
        
        # Update status to verified to allow curation
        from ptia_engine.editorial_board import update_signal_status
        update_signal_status(self.signals_path, signal.signal_id, "verified")
        
        # 2. Pack final é gerado (BuildFinalPackUseCase)
        build_use_case = BuildFinalPackUseCase(
            signal_repo=self.signal_repo,
            topic_repo=self.topic_repo,
            post_repo=self.post_repo,
            buffer_channels_path=self.channels_path,
        )
        result = build_use_case.execute(signal.signal_id)
        
        topic = result["topic"]
        posts = result["posts"]
        
        self.assertIsNotNone(topic)
        self.assertEqual(len(posts), 4) # linkedin, instagram, site, x
        self.assertEqual(topic.status, "approved_for_final")
        
        # Verify signal is now marked as used
        updated_signal = self.signal_repo.get_by_id(signal.signal_id)
        self.assertEqual(updated_signal.status, "used")
        
        # 3. Post é editado (EditPolishPostUseCase)
        edit_use_case = EditPolishPostUseCase(self.post_repo)
        linkedin_post = next(p for p in posts if p.channel == "linkedin")
        
        edited_post = edit_use_case.execute(
            post_id=linkedin_post.post_id,
            title="Título Editado Manualmente",
            body="Texto editado com regras e conteúdo de alta qualidade.",
            hashtags="#ChipsIA #PTIA",
            notes="Edição rápida do editor.",
        )
        
        self.assertEqual(edited_post.title, "Título Editado Manualmente")
        self.assertEqual(edited_post.hashtags, "#ChipsIA #PTIA")
        self.assertEqual(edited_post.status, "needs_final_review")
        
        # 4. Pack é aprovado (ApprovePackageUseCase)
        approve_use_case = ApprovePackageUseCase(self.post_repo, self.channels_path)
        approved_posts = approve_use_case.execute(linkedin_post.post_id)
        
        self.assertEqual(len(approved_posts), 4)
        for post in approved_posts:
            self.assertEqual(post.status, "approved_for_schedule")
            
        # 5. Scheduler gera plano noop/dry-run (GenerateNoopScheduleUseCase)
        # Update scheduled time on posts to match target date
        from ptia_engine.editorial_board import update_final_post_status
        for post in approved_posts:
            update_final_post_status(
                self.posts_path,
                post.post_id,
                status="approved_for_schedule",
                scheduled_time="2026-06-03T15:00:00+01:00",
                image_path="dummy_image.png",
            )
            
        noop_use_case = GenerateNoopScheduleUseCase(
            repo_root=self.root,
            final_posts_path=self.posts_path,
            buffer_channels_path=self.channels_path,
        )
        plan_record = noop_use_case.execute(date_str="2026-06-03")
        
        self.assertEqual(plan_record["date"], "2026-06-03")
        self.assertTrue(plan_record["ready"], f"Plan is not ready. Issues: {plan_record.get('issues')}. Topic issues: {[t.get('issues') for t in plan_record.get('topics', [])]}. Warnings: {plan_record.get('warnings')}")
        self.assertEqual(plan_record["post_count"], 4)
        self.assertTrue(plan_record["dry_run"])


if __name__ == "__main__":
    unittest.main()
