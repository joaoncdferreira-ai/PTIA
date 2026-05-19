import shutil
import unittest
import uuid
from pathlib import Path

from ptia_engine.assets import create_assets_for_draft
from ptia_engine.models import ContentDraft


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_create_square_card_asset(self):
        draft = ContentDraft(
            draft_id="draft_1",
            item_id="item_1",
            article_id="art_1",
            channel="linkedin",
            format="linkedin_post",
            title="AI for Portuguese companies",
            body="This is the key takeaway.",
        )

        assets = create_assets_for_draft(draft, "business", "Source", self.root / "assets")

        self.assertEqual(len(assets), 1)
        svg_path = Path(assets[0].file_path)
        self.assertTrue(svg_path.exists())
        self.assertIn("<svg", svg_path.read_text(encoding="utf-8"))

    def test_create_carousel_assets(self):
        draft = ContentDraft(
            draft_id="draft_2",
            item_id="item_2",
            article_id="art_2",
            channel="instagram",
            format="instagram_carousel",
            title="Carousel",
            carousel_outline=(
                "Slide 1: Hook\nTexto: First\nVisual: One\n\n"
                "Slide 2: Impact\nTexto: Second\nVisual: Two"
            ),
        )

        assets = create_assets_for_draft(draft, "builders", "Source", self.root / "assets")

        self.assertEqual(len(assets), 2)
        self.assertTrue(all(Path(asset.file_path).exists() for asset in assets))


if __name__ == "__main__":
    unittest.main()
