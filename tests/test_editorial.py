import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.editorial import (
    export_scheduling_queue,
    update_draft_status,
    update_item_status,
)
from ptia_engine.models import ContentDraft, ProcessedItem
from ptia_engine.storage import append_jsonl, load_content_drafts, load_processed_items


class EditorialWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_update_item_status(self):
        path = self.root / "processed.jsonl"
        item = ProcessedItem(
            item_id="item_1",
            article_id="art_1",
            source_id="source",
            source_name="Source",
            title_original="Title",
            source_url="https://example.com",
            section="world_ai",
            relevance_score=8,
            hype_score=1,
            portugal_relevance_score=2,
            builder_relevance_score=4,
            business_relevance_score=5,
            should_cover=True,
            reason="Useful.",
        )
        append_jsonl(path, [item])

        update_item_status(path, "item_1", "approved_for_draft", "Looks useful.")

        updated = load_processed_items(path)[0]
        self.assertEqual(updated.editorial_status, "approved_for_draft")
        self.assertIn("Looks useful.", updated.editor_notes)

    def test_export_scheduling_queue_only_approved_social_drafts(self):
        drafts_path = self.root / "drafts.jsonl"
        out_path = self.root / "schedule.csv"
        append_jsonl(
            drafts_path,
            [
                ContentDraft(
                    draft_id="draft_linkedin",
                    item_id="item_1",
                    article_id="art_1",
                    channel="linkedin",
                    format="linkedin_post",
                    title="LinkedIn",
                    body="Post",
                    status="approved",
                ),
                ContentDraft(
                    draft_id="draft_site",
                    item_id="item_1",
                    article_id="art_1",
                    channel="site",
                    format="site_short_article",
                    title="Site",
                    body="Article",
                    status="approved",
                ),
                ContentDraft(
                    draft_id="draft_instagram",
                    item_id="item_2",
                    article_id="art_2",
                    channel="instagram",
                    format="instagram_caption",
                    title="Instagram",
                    caption="Caption",
                    status="draft",
                ),
            ],
        )

        update_draft_status(drafts_path, "draft_instagram", "approved", "2026-05-15T12:30:00+01:00")
        count = export_scheduling_queue(drafts_path, out_path)

        self.assertEqual(count, 2)
        csv_text = out_path.read_text(encoding="utf-8-sig")
        self.assertIn("draft_linkedin", csv_text)
        self.assertIn("draft_instagram", csv_text)
        self.assertNotIn("draft_site", csv_text)
        self.assertEqual(load_content_drafts(drafts_path)[2].status, "approved")


if __name__ == "__main__":
    unittest.main()
