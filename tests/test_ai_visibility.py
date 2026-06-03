import json
import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.ai_visibility import (
    AI_CRAWLER_USER_AGENTS,
    ANSWER_PAGES,
    ENTITY_PAGES,
    build_ai_visibility_report,
    format_ai_visibility_report,
)


class AIVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.site = self.root / "site"
        self.site.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_report_scores_complete_static_ai_layer(self):
        robots = "User-agent: *\nAllow: /\n\n" + "".join(
            f"User-agent: {bot}\nAllow: /\n" for bot in AI_CRAWLER_USER_AGENTS
        )
        (self.site / "robots.txt").write_text(robots, encoding="utf-8")

        sitemap_lines = []
        llms_lines = ["# PTIA.pt", "AI index: https://ptia.pt/ai-index.json"]
        for page in ANSWER_PAGES:
            path = self.site / "perguntas" / page["slug"]
            path.mkdir(parents=True)
            (path / "index.html").write_text("FAQPage", encoding="utf-8")
            sitemap_lines.append(f"https://ptia.pt/perguntas/{page['slug']}/")
            llms_lines.append(f"https://ptia.pt/perguntas/{page['slug']}/")
        for page in ENTITY_PAGES:
            path = self.site / page["path"].strip("/")
            path.mkdir(parents=True)
            (path / "index.html").write_text(str(page["schema_type"]), encoding="utf-8")
            sitemap_lines.append(f"https://ptia.pt{page['path']}")
            llms_lines.append(f"https://ptia.pt{page['path']}")

        article_dir = self.site / "artigos" / "teste"
        article_dir.mkdir(parents=True)
        (article_dir / "index.html").write_text('<a href="/perguntas/como-usar-ia-numa-pme-portuguesa/">Pergunta</a>', encoding="utf-8")

        (self.site / "sitemap.xml").write_text("\n".join(sitemap_lines), encoding="utf-8")
        (self.site / "llms.txt").write_text("\n".join(llms_lines), encoding="utf-8")
        (self.site / "ai-index.json").write_text(
            json.dumps({"answer_pages": [{"url": page["slug"]} for page in ANSWER_PAGES]}),
            encoding="utf-8",
        )

        report = build_ai_visibility_report(self.site)

        self.assertEqual(report["score"], 100)
        self.assertTrue(report["ai_index_valid"])
        self.assertEqual(report["articles_with_question_links"], 1)
        self.assertIn("Score: 100/100", format_ai_visibility_report(report))


if __name__ == "__main__":
    unittest.main()
