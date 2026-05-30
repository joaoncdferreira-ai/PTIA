import unittest
from uuid import uuid4
from pathlib import Path

from ptia_engine.meta_insights import InstagramMedia, InstagramMediaInsights, MetaGraphClient
from ptia_engine.models import FinalPost
from ptia_engine.performance_import import import_instagram_insights
from ptia_engine.storage import load_content_performance, write_jsonl


class FakeMetaClient:
    def recent_media_insights(self, limit=25):
        return [
            InstagramMediaInsights(
                media_id="ig_1",
                permalink="https://instagram.com/p/abc",
                caption="IA na fraude da saúde: o teste é público\n\nLegenda",
                timestamp="2026-05-25T16:00:00+0000",
                impressions=1000,
                reach=750,
                likes=80,
                comments=7,
                saves=9,
                shares=3,
                total_interactions=99,
            )
        ]


class MetaInsightsTests(unittest.TestCase):
    def test_recent_media_parses_graph_response(self):
        client = MetaGraphClient(access_token="token", instagram_business_id="igbiz")
        client._get = lambda path, params: {  # type: ignore[method-assign]
            "data": [
                {
                    "id": "media_1",
                    "caption": "Caption",
                    "media_type": "IMAGE",
                    "media_url": "https://example.com/image.jpg",
                    "permalink": "https://instagram.com/p/abc",
                    "timestamp": "2026-05-25T16:00:00+0000",
                }
            ]
        }

        media = client.recent_media(limit=5)

        self.assertEqual(media[0], InstagramMedia(
            id="media_1",
            caption="Caption",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            permalink="https://instagram.com/p/abc",
            timestamp="2026-05-25T16:00:00+0000",
        ))

    def test_import_instagram_insights_upserts_performance(self):
        root = Path("test_tmp") / f"ptia_meta_test_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            final_posts_path = root / "final_posts.jsonl"
            performance_path = root / "content_performance.jsonl"
            write_jsonl(
                final_posts_path,
                [
                    FinalPost(
                        post_id="post_ig",
                        topic_id="topic_1",
                        channel="instagram",
                        title="IA na fraude da saúde: o teste é público",
                        body="Texto",
                        hashtags="#IA",
                        image_prompt="",
                    )
                ],
            )

            records = import_instagram_insights(
                final_posts_path=final_posts_path,
                performance_path=performance_path,
                client=FakeMetaClient(),
            )

            self.assertEqual(len(records), 1)
            stored = load_content_performance(performance_path)
            self.assertEqual(stored[0].post_id, "post_ig")
            self.assertEqual(stored[0].impressions, 1000)
            self.assertEqual(stored[0].likes, 80)
            self.assertEqual(stored[0].saves, 9)
            self.assertIn("reach=750", stored[0].notes)
        finally:
            for child in root.glob("*"):
                child.unlink()
            root.rmdir()


if __name__ == "__main__":
    unittest.main()
