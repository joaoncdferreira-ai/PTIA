import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ptia_engine.linkedin_performance import (
    LinkedInExportRow,
    import_linkedin_export,
    match_linkedin_post,
)
from ptia_engine.models import FinalPost
from ptia_engine.storage import load_content_performance, write_jsonl


class LinkedInPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.post = FinalPost(
            post_id="post_1",
            topic_id="topic_1",
            channel="linkedin",
            title="BBVA escala ChatGPT Enterprise para 100.000 colaboradores",
            body=(
                "O banco expandiu o acesso à ferramenta e publicou resultados da adoção "
                "por equipas em vários mercados."
            ),
            hashtags="#IA #PTIA",
            image_prompt="Editorial image",
            published_url="https://linkedin.com/posts/1",
            status="published",
        )
        write_jsonl(self.root / "final_posts.jsonl", [self.post])

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_fuzzy_match_handles_exported_full_post_text(self):
        row = LinkedInExportRow(
            title=(
                "O BBVA escalou o ChatGPT Enterprise para 100.000 colaboradores e publicou "
                "resultados da adoção por equipas."
            ),
            url="",
            published_at="2026-06-12T00:00:00+00:00",
            impressions=100,
            clicks=4,
            likes=3,
            comments=1,
            shares=0,
            followers_gained=0,
        )

        self.assertEqual(match_linkedin_post(row, [self.post]).post_id, self.post.post_id)

    @patch("ptia_engine.linkedin_performance._read_linkedin_rows")
    def test_import_upserts_metrics_and_links_matched_post(self, read_rows):
        read_rows.return_value = [
            LinkedInExportRow(
                title=self.post.title,
                url=self.post.published_url,
                published_at="2026-06-12T00:00:00+00:00",
                impressions=120,
                clicks=5,
                likes=4,
                comments=2,
                shares=1,
                followers_gained=1,
            )
        ]

        result = import_linkedin_export(
            export_path=self.root / "export.xls",
            final_posts_path=self.root / "final_posts.jsonl",
            performance_path=self.root / "content_performance.jsonl",
        )
        records = load_content_performance(self.root / "content_performance.jsonl")

        self.assertEqual(result.matched, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].post_id, self.post.post_id)
        self.assertEqual(records[0].impressions, 120)


if __name__ == "__main__":
    unittest.main()
