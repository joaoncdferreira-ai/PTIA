import base64
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ptia_engine.buffer_api import BufferChannel, BufferOrganization, BufferPostResult
from ptia_engine.editorial_board import (
    add_editorial_topic,
    add_final_post,
    add_radar_signal,
    update_final_post_copy,
    update_final_post_status,
    update_signal_status,
)
from ptia_engine.dashboard import (
    DashboardState,
    _apply_ptia_editorial_rules,
    _buffer_channel_id_for,
    _build_final_pack_from_signal,
    _approve_final_package,
    _copy_quality_issues,
    _discover_buffer_channels,
    _final_post_text,
    _generate_final_image,
    _high_quality_image_prompt,
    _image_prompt_group_for_channel,
    _normalise_hashtags,
    _schedule_final_package,
    _schedule_post_in_buffer,
    _site_feed,
    _upload_final_image,
)
from ptia_engine.storage import load_editorial_topics, load_final_posts, load_radar_signals


class EditorialBoardTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.gemini_patcher = patch("ptia_engine.dashboard.GeminiGroundedSearchProvider")
        self.mock_gemini_cls = self.gemini_patcher.start()
        self.mock_provider = self.mock_gemini_cls.return_value
        self.mock_provider.available = True
        
        from collections import namedtuple
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

    def test_new_flow_creates_signal_topic_and_final_post(self):
        signal = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Google",
            title="Gemini Intelligence",
            url="https://example.com",
            published_at=datetime.now(timezone.utc).date().isoformat(),
            summary="Fresh AI news.",
        )
        topic = add_editorial_topic(
            self.root / "editorial_topics.jsonl",
            title="Android turns into an AI layer",
            thesis="The phone is becoming an assistant, not just an app launcher.",
            portugal_angle="Portuguese companies should revisit mobile workflows.",
            audience="business",
            source_signal_ids=[signal.signal_id],
            urgency_score=8,
        )
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id=topic.topic_id,
            channel="linkedin",
            title="O telemovel vai trabalhar mais por ti",
            body="Texto final.",
            hashtags="#IA #Portugal",
            image_prompt="Clean editorial image.",
            source_urls=["https://example.com"],
        )
        update_final_post_status(self.root / "final_posts.jsonl", post.post_id, "approved_for_schedule")

        self.assertEqual(len(load_radar_signals(self.root / "radar_signals.jsonl")), 1)
        self.assertEqual(len(load_editorial_topics(self.root / "editorial_topics.jsonl")), 1)
        self.assertEqual(load_final_posts(self.root / "final_posts.jsonl")[0].status, "approved_for_schedule")

    def test_signal_requires_exact_recent_date(self):
        with self.assertRaises(ValueError):
            add_radar_signal(
                self.root / "radar_signals.jsonl",
                source_type="instagram",
                source_name="Ranking",
                title="Vague month is not enough",
                url="https://example.com",
                published_at="2026-05",
            )

    def test_verifying_signal_can_wait_for_date(self):
        signal = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Unverified",
            title="Needs verification",
            url="https://example.com/story",
            status="verifying",
            require_recent=False,
        )

        self.assertEqual(signal.status, "verifying")

    def test_build_final_pack_from_verified_signal(self):
        signal = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="AI changes enterprise workflows",
            url="https://www.reuters.com/technology/ai/story",
            published_at=datetime.now(timezone.utc).date().isoformat(),
            summary="Companies are adopting AI in practical workflows.",
            why_it_matters="Relevant for Portuguese companies tracking productivity.",
            status="verified",
        )

        result = _build_final_pack_from_signal(DashboardState(self.root), signal.signal_id)

        self.assertEqual(len(result["posts"]), 4)
        self.assertEqual({post["channel"] for post in result["posts"]}, {"linkedin", "instagram", "x", "site"})
        linkedin = next(post for post in result["posts"] if post["channel"] == "linkedin")
        x_post = next(post for post in result["posts"] if post["channel"] == "x")
        self.assertNotIn("A notícia", linkedin["body"])
        self.assertNotIn("A leitura PTIA", linkedin["body"])
        self.assertNotIn("O que observar", linkedin["body"])
        self.assertNotIn("lista de prioridades", linkedin["body"])
        self.assertNotIn("O que significa para Portugal", linkedin["title"])
        self.assertIn("Fonte:", linkedin["body"])
        self.assertLessEqual(len(f'{x_post["body"]}\n\n{x_post["hashtags"]}'), 280)
        self.assertNotIn("separar sinal de ruído", linkedin["body"].casefold())
        all_copy = "\n\n".join(post["body"] for post in result["posts"])
        self.assertNotIn("quem ganha acesso primeiro", all_copy.casefold())
        self.assertNotIn("a pergunta útil", all_copy.casefold())
        self.assertNotIn("custo, risco e dependência", all_copy.casefold())
        self.assertEqual(load_radar_signals(self.root / "radar_signals.jsonl")[0].status, "used")

    def test_disabled_x_is_hidden_and_not_generated(self):
        (self.root / "buffer_channels.json").write_text(
            '{"channels":{"linkedin":"chan_linkedin","instagram":"chan_instagram"},"disabled_channels":["x"]}',
            encoding="utf-8",
        )
        signal = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="AI changes enterprise workflows",
            url="https://www.reuters.com/technology/ai/story",
            published_at=datetime.now(timezone.utc).date().isoformat(),
            summary="Companies are adopting AI in practical workflows.",
            status="verified",
        )

        result = _build_final_pack_from_signal(DashboardState(self.root), signal.signal_id)
        snapshot = DashboardState(self.root).snapshot()

        self.assertEqual({post["channel"] for post in result["posts"]}, {"linkedin", "instagram", "site"})
        self.assertEqual(snapshot["channel_settings"]["disabled_channels"], ["x"])
        self.assertNotIn("x", {post["channel"] for post in snapshot["final_posts"]})

    def test_image_prompts_split_instagram_x_from_linkedin_site(self):
        instagram = _high_quality_image_prompt(
            "Tema PTIA",
            "Contexto curto",
            group="instagram_x",
            visual_title="A IA ja mudou a pergunta",
        )
        linkedin_site = _high_quality_image_prompt("Tema PTIA", "Contexto curto")

        self.assertEqual(_image_prompt_group_for_channel("instagram"), "instagram_x")
        self.assertEqual(_image_prompt_group_for_channel("x"), "instagram_x")
        self.assertEqual(_image_prompt_group_for_channel("site"), "linkedin_site")
        self.assertIn("Instagram e X", instagram)
        self.assertIn(
            'Título visual escolhido no dashboard para o overlay PTIA: "A IA ja mudou a pergunta"',
            instagram,
        )
        self.assertIn("Não desenhes esse título", instagram)
        self.assertIn("LinkedIn e site", linkedin_site)
        self.assertIn("sem texto escrito na imagem", linkedin_site)

    def test_editorial_rules_remove_generic_ctas_and_labels(self):
        title, body = _apply_ptia_editorial_rules(
            "Nova ferramenta - O que significa para Portugal?",
            "A leitura PTIA: Texto bom.\n\nIsto entraria na tua lista de prioridades para os próximos meses?",
            "linkedin",
        )

        self.assertEqual(title, "Nova ferramenta")
        self.assertEqual(body, "Texto bom.")

    def test_editorial_rules_remove_banned_post_phrase(self):
        _, body = _apply_ptia_editorial_rules(
            "Nova ferramenta",
            "Facto claro.\n\nO entusiasmo é compreensível.\n\n**O teste** é execução.",
            "instagram",
        )

        self.assertEqual(body, "Facto claro.\n\nO teste é execução.")

    def test_editorial_rules_remove_ai_cliches(self):
        _, body = _apply_ptia_editorial_rules(
            "Nova ferramenta",
            (
                "No panorama atual, a IA acelera.\n\n"
                "Além disso, o impacto de X não pode ser subestimado.\n\n"
                "A verdade é que é crucial decidir.\n\n"
                "Será que este é o primeiro passo para a IA entrar nas empresas?\n\n"
                "Quem consegue executar sem aumentar custo, risco e dependência?"
            ),
            "site",
        )

        self.assertNotIn("No panorama atual", body)
        self.assertNotIn("Além disso", body)
        self.assertNotIn("não pode ser subestimado", body)
        self.assertNotIn("A verdade é que", body)
        self.assertNotIn("crucial", body.casefold())
        self.assertNotIn("será que", body.casefold())
        self.assertNotIn("quem consegue executar", body.casefold())
        self.assertNotIn("custo, risco e dependência", body.casefold())
        self.assertIn("importante", body)

    def test_final_post_text_does_not_duplicate_body_source_links(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Google I/O",
            body="Texto final.\n\nFonte: https://example.com/source",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com/source"],
        )

        text = _final_post_text(post)

        self.assertIn("Fonte: https://example.com/source", text)
        self.assertNotIn("Fontes:", text)
        self.assertEqual(text.count("https://example.com/source"), 1)

    def test_copy_quality_flags_broken_instagram_source_bullet(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Anthropic lança Project Glasswing",
            body=(
                "A Anthropic apresentou uma iniciativa para corrigir vulnerabilidades críticas em software.\n\n"
                "Três coisas a reter:\n"
                "- A novidade cabe num anúncio. O teste não.\n"
                "- - Fonte: anthropic.com"
            ),
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://www.anthropic.com/"],
        )

        issues = _copy_quality_issues(post)

        self.assertIn("bullet de fonte quebrada", issues)

    def test_copy_quality_flags_inline_source_after_truncated_sentence(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Anthropic usa IA na cibersegurança",
            body=(
                "A Anthropic lançou uma iniciativa para detetar vulnerabilidades críticas.\n\n"
                "A aplicação de IA na cibersegurança é importante. Contudo, importa perceber "
                "Fonte: https://www.anthropic.com/"
            ),
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://www.anthropic.com/"],
        )

        issues = _copy_quality_issues(post)

        self.assertIn("fonte colada no meio da frase", issues)

    def test_approve_final_package_blocks_broken_channel_copy(self):
        linkedin = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Post completo",
            body=(
                "Texto factual sobre a notícia, com contexto suficiente para publicar.\n\n"
                "A leitura editorial é específica e explica a consequência para equipas reais, "
                "sem depender de fórmulas genéricas ou frases truncadas.\n\n"
                "Fonte: https://example.com/source"
            ),
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com/source"],
        )
        instagram = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Post partido",
            body=(
                "Resumo curto da notícia.\n\n"
                "Três coisas a reter:\n"
                "- A primeira leitura ainda existe.\n"
                "- - Fonte: https://example.com/source"
            ),
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com/source"],
        )
        update_final_post_status(self.root / "final_posts.jsonl", linkedin.post_id, "needs_final_review")
        update_final_post_status(self.root / "final_posts.jsonl", instagram.post_id, "needs_final_review")

        with self.assertRaisesRegex(ValueError, "Pacote bloqueado"):
            _approve_final_package(DashboardState(self.root), linkedin.post_id)

    def test_x_final_post_text_respects_source_and_length(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="x",
            title="Google I/O",
            body=(
                "A Google mostrou agentes novos. A pergunta PTIA e quem consegue levar isto para trabalho real, "
                "com custos claros, equipas preparadas e uma decisao concreta para amanha. " * 3 + "\n\n"
                "Fonte original: https://example.com/source"
            ),
            hashtags="#IA #PTIA #Extra",
            image_prompt="",
            source_urls=["https://example.com/source"],
        )

        text = _final_post_text(post)

        self.assertNotIn("Fontes:", text)
        self.assertEqual(text.count("https://example.com/source"), 1)
        self.assertLessEqual(len(text), 280)

    def test_update_final_post_copy_records_feedback(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Old",
            body="Old body",
            hashtags="#IA",
            image_prompt="Prompt",
            source_urls=["https://example.com"],
        )

        updated = update_final_post_copy(
            self.root / "final_posts.jsonl",
            post.post_id,
            title="New",
            body="New body",
            notes="Feedback: mais ponto de vista",
        )

        self.assertEqual(updated.title, "New")
        self.assertIn("mais ponto de vista", updated.editor_notes)

    def test_generate_final_image_updates_post(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
        )

        updated = _generate_final_image(DashboardState(self.root), post.post_id, feedback="mais contraste")

        self.assertTrue(Path(updated.image_path).exists())
        self.assertEqual(updated.image_status, "needs_review")

    def test_upload_final_image_formats_channel_variants_for_package(self):
        linkedin = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
        )
        instagram = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
        )
        image = Image.new("RGB", (1400, 900), (18, 54, 92))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

        updated = _upload_final_image(DashboardState(self.root), linkedin.post_id, "master.png", data_url)

        self.assertIn("linkedin", updated.image_variants)
        self.assertIn("instagram", updated.image_variants)
        self.assertIn("x", updated.image_variants)
        self.assertTrue(Path(updated.image_variants["linkedin"]).exists())
        self.assertTrue(Path(updated.image_variants["instagram"]).exists())
        self.assertTrue(Path(updated.image_variants["x"]).exists())
        with Image.open(updated.image_variants["instagram"]) as instagram_variant:
            self.assertNotEqual(instagram_variant.getpixel((60, 1000)), (18, 54, 92))

        posts = {post.post_id: post for post in load_final_posts(self.root / "final_posts.jsonl")}
        self.assertEqual(posts[instagram.post_id].image_path, updated.image_path)
        self.assertIn("instagram", posts[instagram.post_id].image_variants)

    def test_instagram_with_local_image_gets_public_url_for_buffer(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Imagem PTIA",
            body="Texto final",
            hashtags="#IA",
            image_prompt="Imagem premium",
            source_urls=["https://example.com"],
            image_path=str(self.root / "image.png"),
        )
        Path(post.image_path).write_bytes(b"not-a-real-image-but-present")
        (self.root / "buffer_channels.json").write_text(
            '{"channels":{"instagram":"chan_instagram"}}',
            encoding="utf-8",
        )

        with (
            patch("ptia_engine.dashboard.BufferClient") as client_cls,
            patch(
                "ptia_engine.dashboard._public_asset_base_url",
                return_value="https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site",
            ),
        ):
            client_cls.return_value.create_scheduled_post.return_value = BufferPostResult(id="buffer_1")
            updated = _schedule_post_in_buffer(
                DashboardState(self.root),
                post.post_id,
                "2026-05-19T09:00:00+01:00",
            )

        self.assertEqual(updated.status, "scheduled")
        self.assertEqual(updated.buffer_post_id, "buffer_1")
        call_kwargs = client_cls.return_value.create_scheduled_post.call_args.kwargs
        self.assertEqual(
            call_kwargs["image_url"],
            "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site/assets/final/image.png",
        )
        self.assertTrue((self.root.parent / "site" / "assets" / "final" / "image.png").exists())

    def test_discover_buffer_channels_maps_twitter_to_x(self):
        with patch("ptia_engine.dashboard.BufferClient") as client_cls:
            client_cls.return_value.discover_channels.return_value = (
                [BufferOrganization(id="org_1", name="PTIA")],
                [BufferChannel(id="chan_x", name="PTIAPT", display_name="PTIAPT", service="twitter")],
            )

            payload = _discover_buffer_channels(self.root / "buffer_channels.json")

        self.assertEqual(payload["channels"]["x"], "chan_x")
        self.assertEqual(_buffer_channel_id_for("x", payload), "chan_x")

    def test_schedule_package_is_idempotent_when_already_scheduled(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Post ja agendado",
            body="Texto final",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com"],
        )
        update_final_post_status(
            self.root / "final_posts.jsonl",
            post.post_id,
            "scheduled",
            scheduled_time="2026-05-21T09:00:00+01:00",
            buffer_post_id="buffer_1",
        )

        updated = _schedule_final_package(
            DashboardState(self.root),
            "topic_1",
            "2026-05-21T09:00:00+01:00",
        )

        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].status, "scheduled")
        self.assertEqual(updated[0].buffer_post_id, "buffer_1")

    def test_site_feed_uses_scheduled_site_posts(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="site",
            title="Entrada site",
            body="Texto site",
            hashtags="",
            image_prompt="",
            source_urls=["https://example.com"],
        )
        update_final_post_status(
            self.root / "final_posts.jsonl",
            post.post_id,
            "scheduled",
            scheduled_time="2026-05-15T09:00:00+01:00",
        )

        feed = _site_feed(DashboardState(self.root))

        self.assertEqual(feed["posts"][0]["title"], "Entrada site")

    def test_dashboard_radar_count_only_counts_radar_stage(self):
        today = datetime.now(timezone.utc).date().isoformat()
        active = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="Active radar",
            url="https://example.com/active-radar",
            published_at=today,
            status="new",
            require_recent=False,
        )
        verified = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="Verified",
            url="https://example.com/verified",
            published_at=today,
            status="verified",
        )
        used = add_radar_signal(
            self.root / "radar_signals.jsonl",
            source_type="news",
            source_name="Reuters",
            title="Used",
            url="https://example.com/used",
            published_at=today,
            status="verified",
        )
        update_signal_status(self.root / "radar_signals.jsonl", used.signal_id, "used")

        snapshot = DashboardState(self.root).snapshot()

        self.assertEqual(snapshot["counts"]["radar_signals_v2"], 1)
        self.assertEqual(snapshot["radar_inbox_signals"][0]["signal_id"], active.signal_id)
        self.assertEqual(snapshot["counts"]["verified_selection"], 1)
        self.assertEqual(snapshot["verified_signals"][0]["signal_id"], verified.signal_id)

    def test_normalise_hashtags_removes_python_list_syntax(self):
        hashtags = _normalise_hashtags(
            "['#InteligenciaArtificial', '#IA', '#Portugal', '#MercadoDeTrabalho', '#PTIA']",
            "linkedin",
        )

        self.assertEqual(hashtags, "#InteligenciaArtificial #IA #Portugal #MercadoDeTrabalho")

    def test_due_scheduled_posts_stay_scheduled_until_confirmed_published(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Post antigo",
            body="Texto",
            hashtags="['#IA', '#Portugal']",
            image_prompt="",
            source_urls=[],
        )
        update_final_post_status(
            self.root / "final_posts.jsonl",
            post.post_id,
            "scheduled",
            scheduled_time="2000-01-01T09:00:00+00:00",
        )

        snapshot = DashboardState(self.root).snapshot()

        self.assertEqual(snapshot["counts"]["final_scheduled"], 1)
        self.assertEqual(snapshot["counts"]["final_published"], 0)
        scheduled = load_final_posts(self.root / "final_posts.jsonl")[0]
        self.assertEqual(scheduled.status, "scheduled")
        self.assertEqual(scheduled.hashtags, "#IA #Portugal")


if __name__ == "__main__":
    unittest.main()
