import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.dashboard import DashboardState
from ptia_engine.models import ContentDraft, ContentPerformance, ProcessedItem, RadarSignal, RawArticle
from ptia_engine.storage import append_jsonl


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_snapshot_contains_funnel_and_learnings(self):
        append_jsonl(
            self.root / "raw_articles.jsonl",
            [
                RawArticle(
                    article_id="art_1",
                    source_id="source",
                    source_name="Source",
                    title_original="Agent story",
                    url="https://example.com",
                    status="new",
                )
            ],
        )
        append_jsonl(
            self.root / "processed_items.jsonl",
            [
                ProcessedItem(
                    item_id="item_1",
                    article_id="art_1",
                    source_id="source",
                    source_name="Source",
                    title_original="Agent story",
                    source_url="https://example.com",
                    section="builders",
                    relevance_score=8,
                    hype_score=1,
                    portugal_relevance_score=2,
                    builder_relevance_score=8,
                    business_relevance_score=4,
                    should_cover=True,
                    reason="Useful.",
                )
            ],
        )
        append_jsonl(
            self.root / "content_drafts.jsonl",
            [
                ContentDraft(
                    draft_id="draft_1",
                    item_id="item_1",
                    article_id="art_1",
                    channel="linkedin",
                    format="linkedin_post",
                    title="Agent story",
                    body="Post",
                    status="published",
                )
            ],
        )
        append_jsonl(
            self.root / "content_performance.jsonl",
            [
                ContentPerformance(
                    performance_id="perf_1",
                    draft_id="draft_1",
                    post_id="post_1",
                    channel="linkedin",
                    published_at="2026-05-14T12:00:00+00:00",
                    topic="Agent story",
                    section="builders",
                    likes=5,
                    comments=2,
                    shares=1,
                    saves=1,
                    clicks=3,
                )
            ],
        )

        snapshot = DashboardState(self.root).snapshot()

        self.assertEqual(snapshot["counts"]["raw_articles"], 1)
        self.assertEqual(snapshot["counts"]["published"], 1)
        self.assertEqual(snapshot["learnings"]["best_posts"][0]["score"], 18)

    def test_signal_funnel_counts_each_signal_once(self):
        append_jsonl(
            self.root / "radar_signals.jsonl",
            [
                RadarSignal(
                    signal_id="sig_new",
                    source_type="news",
                    source_name="Manual",
                    title="New",
                    url="https://example.com/new",
                    status="new",
                ),
                RadarSignal(
                    signal_id="sig_verifying",
                    source_type="news",
                    source_name="Manual",
                    title="Verifying",
                    url="https://example.com/verifying",
                    status="verifying",
                ),
                RadarSignal(
                    signal_id="sig_verified",
                    source_type="news",
                    source_name="Manual",
                    title="Verified",
                    url="https://example.com/verified",
                    status="verified",
                ),
                RadarSignal(
                    signal_id="sig_secondary",
                    source_type="news",
                    source_name="Manual",
                    title="Secondary",
                    url="https://example.com/secondary",
                    status="verified_secondary",
                ),
                RadarSignal(
                    signal_id="sig_selected",
                    source_type="news",
                    source_name="Manual",
                    title="Selected",
                    url="https://example.com/selected",
                    status="selected",
                ),
                RadarSignal(
                    signal_id="sig_used",
                    source_type="news",
                    source_name="Manual",
                    title="Used",
                    url="https://example.com/used",
                    status="used",
                ),
            ],
        )

        snapshot = DashboardState(self.root).snapshot()

        self.assertEqual(snapshot["counts"]["radar_signals_v2"], 1)
        self.assertEqual(snapshot["counts"]["verifying"], 1)
        self.assertEqual(snapshot["counts"]["verified_selection"], 3)
        self.assertEqual([signal["signal_id"] for signal in snapshot["radar_inbox_signals"]], ["sig_new"])


if __name__ == "__main__":
    unittest.main()
