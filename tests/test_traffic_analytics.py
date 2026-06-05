import json
import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.traffic import (
    build_analytics_snippet,
    build_traffic_report,
    inject_snippet_into_file,
    inject_snippet_into_html,
    list_trackable_pages,
    snippet_already_present,
)


class TrafficAnalyticsTests(unittest.TestCase):
    """Testes para a camada de traffic analytics do site ptia.pt.

    Garante:
    - analytics aparece na homepage
    - analytics aparece em paginas estaticas geradas (artigos)
    - nenhum ficheiro editorial e alterado
    """

    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.site = self.root / "site"
        self.site.mkdir()
        self.data = self.root / "data"
        self.data.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_html(self, path: Path, title: str = "Teste") -> None:
        """Cria um HTML minimo com </head> para testar injecao."""
        html = (
            "<!doctype html>\n"
            "<html lang=\"pt\">\n"
            "<head>\n"
            f"<title>{title}</title>\n"
            "</head>\n"
            "<body><p>Conteudo</p></body>\n"
            "</html>\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    def _make_jsonl(self, path: Path, records: list) -> None:
        """Cria um ficheiro JSONL."""
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + ("\n" if records else ""),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Teste 1: analytics aparece na homepage apos injecao
    # ------------------------------------------------------------------

    def test_analytics_injected_in_homepage(self):
        """Apos inject_snippet_into_file, a homepage deve ter o marcador analytics."""
        homepage = self.site / "index.html"
        self._make_html(homepage, "PTIA Homepage")

        snippet = build_analytics_snippet(provider="plausible", domain="ptia.pt")
        self.assertIn("ptia-analytics", snippet)
        self.assertIn("plausible.io", snippet)

        changed = inject_snippet_into_file(homepage, snippet)
        self.assertTrue(changed, "O ficheiro devia ter sido alterado")

        content = homepage.read_text(encoding="utf-8")
        self.assertTrue(snippet_already_present(content))
        self.assertIn("plausible.io", content)

        # Idempotencia: segunda injecao nao altera o ficheiro
        changed_again = inject_snippet_into_file(homepage, snippet)
        self.assertFalse(changed_again, "Segunda injecao nao deve alterar o ficheiro")

    # ------------------------------------------------------------------
    # Teste 2: analytics aparece em paginas de artigos estaticos
    # ------------------------------------------------------------------

    def test_analytics_injected_in_article_pages(self):
        """Analytics deve ser injetado em todos os artigos estaticos."""
        # Criar homepage
        homepage = self.site / "index.html"
        self._make_html(homepage, "PTIA")

        # Criar 3 artigos estaticos
        slugs = [
            "artigo-um-abc123",
            "artigo-dois-def456",
            "artigos/artigo-tres-ghi789",
        ]
        article_pages = []
        for slug in slugs:
            page = self.site / slug / "index.html"
            self._make_html(page, "Artigo " + slug)
            article_pages.append(page)

        snippet = build_analytics_snippet(provider="plausible", domain="ptia.pt")

        # Injetar em todas
        all_pages = [homepage] + article_pages
        for page in all_pages:
            inject_snippet_into_file(page, snippet)

        # Verificar que todas as paginas tem analytics
        trackable = list_trackable_pages(self.site)
        self.assertEqual(len(trackable), 4)
        for tp in trackable:
            self.assertTrue(
                tp.has_analytics,
                f"Pagina {tp.path} devia ter analytics mas nao tem",
            )

        # Verificar relatorio
        report = build_traffic_report(self.site)
        self.assertEqual(report.total_pages, 4)
        self.assertEqual(report.pages_with_analytics, 4)
        self.assertEqual(report.pages_without_analytics, 0)

    # ------------------------------------------------------------------
    # Teste 3: ficheiros editoriais nao sao alterados
    # ------------------------------------------------------------------

    def test_editorial_files_not_modified(self):
        """final_posts, linkedin_comments e content_performance nao sao tocados."""
        # Criar ficheiros editoriais com conteudo de referencia
        fp_data = [{"id": "p1", "channel": "linkedin", "body": "Post 1"}]
        lc_data = [{"id": "c1", "post_id": "p1", "comment": "Bom post!"}]
        cp_data = []  # vazio conforme o estado real

        final_posts = self.data / "final_posts.jsonl"
        linkedin_comments = self.data / "linkedin_comments.jsonl"
        content_performance = self.data / "content_performance.jsonl"

        self._make_jsonl(final_posts, fp_data)
        self._make_jsonl(linkedin_comments, lc_data)
        self._make_jsonl(content_performance, cp_data)

        # Guardar checksums originais
        fp_original = final_posts.read_text(encoding="utf-8")
        lc_original = linkedin_comments.read_text(encoding="utf-8")
        cp_original = content_performance.read_text(encoding="utf-8")

        # Criar HTML no site e injetar analytics
        homepage = self.site / "index.html"
        self._make_html(homepage, "PTIA")
        snippet = build_analytics_snippet(provider="plausible", domain="ptia.pt")
        inject_snippet_into_file(homepage, snippet)

        # Build do relatorio (read-only)
        build_traffic_report(self.site)

        # Verificar que os ficheiros editoriais estao intactos
        self.assertEqual(
            final_posts.read_text(encoding="utf-8"),
            fp_original,
            "final_posts.jsonl foi alterado - nao devia!",
        )
        self.assertEqual(
            linkedin_comments.read_text(encoding="utf-8"),
            lc_original,
            "linkedin_comments.jsonl foi alterado - nao devia!",
        )
        self.assertEqual(
            content_performance.read_text(encoding="utf-8"),
            cp_original,
            "content_performance.jsonl foi alterado - nao devia!",
        )

    # ------------------------------------------------------------------
    # Teste 4: snippet nao e injetado se provider="none"
    # ------------------------------------------------------------------

    def test_no_snippet_for_provider_none(self):
        """Quando provider=none, nenhum snippet e gerado nem injetado."""
        snippet = build_analytics_snippet(provider="none", domain="ptia.pt")
        self.assertEqual(snippet, "")

        homepage = self.site / "index.html"
        self._make_html(homepage, "PTIA")
        changed = inject_snippet_into_file(homepage, snippet)
        self.assertFalse(changed)

        content = homepage.read_text(encoding="utf-8")
        self.assertFalse(snippet_already_present(content))


if __name__ == "__main__":
    unittest.main()
