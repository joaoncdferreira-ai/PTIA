import shutil
import unittest
import uuid
from collections import namedtuple
from pathlib import Path

from ptia_engine.editorial_board import add_final_post
from ptia_engine.services.channels import buffer_channel_id_for, expected_schedule_channels
from ptia_engine.services.editorial_hygiene import (
    apply_ptia_editorial_rules,
    clean_editorial_title,
    copy_quality_issues,
    normalise_hashtags,
)
from ptia_engine.services.gemini import polish_final_post_copy
from ptia_engine.services.media import copy_image_to_public_site_assets, public_image_url
from ptia_engine.services.site import (
    article_url_for_site_post,
    clean_article_body,
    excerpt,
    is_public_site_post,
    slugify_site_value,
)
from ptia_engine.services.social_text import fit_x_post_text, x_post_validation_issues, x_weighted_len


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_editorial_hygiene_is_independent_and_strict(self):
        title, body = apply_ptia_editorial_rules(
            "Tema - O que significa para Portugal?",
            "A notícia da Reuters mostra adoção real.\n\nIsto entra na tua lista de prioridades para os próximos meses?",
            "linkedin",
        )

        self.assertEqual(title, "Tema")
        self.assertIn("O relato da Reuters", body)
        self.assertNotIn("lista de prioridades", body)

    def test_editorial_titles_are_plain_text(self):
        self.assertEqual(
            clean_editorial_title(
                "Responsible AI lança <i>framework</i> **TrustX** &amp; validação"
            ),
            "Responsible AI lança framework TrustX & validação",
        )

    def test_hashtag_normalisation_limits_by_channel(self):
        hashtags = normalise_hashtags(
            "['#InteligenciaArtificial', '#IA', '#Portugal', '#Mercado', '#Extra']",
            "linkedin",
        )

        self.assertEqual(hashtags, "#InteligenciaArtificial #IA #Portugal #Mercado")

    def test_copy_quality_detects_blocking_source_bullet(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="instagram",
            title="Post",
            body="Três leituras:\n- Uma leitura.\n- - Fonte: https://example.com",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com"],
        )

        self.assertIn("bullet de fonte quebrada", copy_quality_issues(post))

    def test_media_service_builds_public_url_and_copies_asset(self):
        image = self.root / "image.jpg"
        image.write_bytes(b"image")
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="linkedin",
            title="Post",
            body="Texto",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com"],
            image_path=str(image),
        )

        copied = copy_image_to_public_site_assets(self.root / "site", post)

        self.assertTrue(Path(copied).exists())
        self.assertEqual(Path(copied).name, "image.jpg")
        self.assertEqual(
            public_image_url(
                post,
                self.root,
                base_url="https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site",
            ),
            "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site/assets/final/image.jpg",
        )

    def test_public_image_url_handles_windows_path_when_compiled_on_linux(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_windows_image",
            channel="site",
            title="Windows image path",
            body="Body",
            hashtags="",
            image_prompt="",
            source_urls=["https://example.com/story"],
            image_variants={
                "site": r"C:\Users\editor\ptia\data\final_assets\story-site.jpg"
            },
        )

        self.assertEqual(
            public_image_url(post, base_url="https://ptia.pt", channel="site"),
            "https://ptia.pt/assets/final/story-site.jpg",
        )

    def test_channel_service_maps_buffer_ids_and_disabled_schedule_channels(self):
        config = {
            "channels": {"linkedin_page": "li_1", "twitter": "x_1"},
            "disabled_channels": ["x"],
        }

        self.assertEqual(buffer_channel_id_for("linkedin", config), "li_1")
        self.assertEqual(buffer_channel_id_for("x", config), "x_1")
        self.assertEqual(expected_schedule_channels(config), {"instagram", "linkedin", "site"})

    def test_social_text_service_fits_and_validates_x_posts(self):
        source = "https://example.com/a-very-long-source-url-that-x-counts-as-short"
        body = ("Uma leitura longa sobre IA aplicada a empresas portuguesas. " * 12) + f"\n\nFonte: {source}"

        text = fit_x_post_text(body, "#IA #Portugal", [source])

        self.assertLessEqual(x_weighted_len(text), 280)
        self.assertEqual(x_post_validation_issues(text, "https://example.com/image.jpg"), [])

    def test_site_service_builds_article_paths_and_public_copy(self):
        post = add_final_post(
            self.root / "final_posts.jsonl",
            topic_id="topic_1",
            channel="site",
            title="IA em Portugal: o que muda?",
            body="Primeiro paragrafo.\n\nFonte: https://example.com\n\nSegundo paragrafo.",
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com"],
        )

        self.assertEqual(slugify_site_value("IA em Portugal: o que muda?"), "ia-em-portugal-o-que-muda")
        self.assertTrue(article_url_for_site_post(post).startswith("artigos/ia-em-portugal-o-que-muda-"))
        self.assertEqual(clean_article_body(post.body), "Primeiro paragrafo.\n\nSegundo paragrafo.")
        self.assertEqual(excerpt(post.body, length=24), "Primeiro paragrafo...")
        self.assertTrue(is_public_site_post({"published_at": ""}))

    def test_gemini_service_uses_provider_and_editorial_rules(self):
        Polished = namedtuple("Polished", ["title", "body", "hashtags", "rationale"])

        class Provider:
            available = True

            def polish_final_post(self, **kwargs):
                return Polished("Titulo - O que significa para Portugal?", "A noticia explica o impacto.", "", "ok")

        result = polish_final_post_copy(
            channel="linkedin",
            title="Original",
            body="Texto original",
            hashtags="#IA",
            source_urls=["https://example.com"],
            provider=Provider(),
            apply_editorial_rules=apply_ptia_editorial_rules,
        )

        self.assertEqual(result["title"], "Titulo")
        self.assertIn("O relato", result["body"])
        self.assertEqual(result["hashtags"], "#IA")
        self.assertIn("PT-PT Editorial Polish", result["editor_notes"])


if __name__ == "__main__":
    unittest.main()
