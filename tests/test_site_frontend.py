import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteFrontendTests(unittest.TestCase):
    def test_homepage_waits_for_live_feed_and_does_not_ship_stale_stories(self):
        script = (ROOT / "site" / "app.js").read_text(encoding="utf-8")

        self.assertIn("today: []", script)
        self.assertNotIn("Governo quer usar IA no combate aos incêndios", script)
        self.assertIn('renderFeedStatus("A atualizar a edição…")', script)
        self.assertIn("const hydrated = await hydrateFromFeedIfAvailable();", script)
        self.assertIn('cache: "no-store"', script)
        self.assertIn("FEED_CACHE_KEY", script)

        initializer = re.search(
            r"async function initializeSite\(\) \{(?P<body>.*?)\n\}",
            script,
            re.DOTALL,
        )
        self.assertIsNotNone(initializer)
        body = initializer.group("body")
        self.assertLess(
            body.index('renderFeedStatus("A atualizar a edição…")'),
            body.index("await hydrateFromFeedIfAvailable()"),
        )
        self.assertNotIn("/1840", script)
        self.assertNotIn("setupSignalViz();", script)

    def test_dynamic_files_and_feed_revalidate_in_production(self):
        config = json.loads((ROOT / "site" / "vercel.json").read_text(encoding="utf-8"))
        headers = {
            entry["source"]: {header["key"]: header["value"] for header in entry["headers"]}
            for entry in config["headers"]
        }

        self.assertIn("must-revalidate", headers["/"]["Cache-Control"])
        self.assertIn("must-revalidate", headers["/app.js"]["Cache-Control"])
        self.assertIn("no-store", headers["/site-feed.json"]["Cache-Control"])
        self.assertIn("no-store", headers["/api/site-feed"]["Cache-Control"])

        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js?v=20261008-1", html)


if __name__ == "__main__":
    unittest.main()
