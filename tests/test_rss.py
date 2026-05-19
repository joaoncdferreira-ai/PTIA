import unittest

from ptia_engine.models import Source
from ptia_engine.rss import parse_feed


class RSSTests(unittest.TestCase):
    def test_parse_rss_feed(self):
        source = Source(
            source_id="test_source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            type="news_media",
            category="world_ai",
            language="en",
            country="US",
            trust_score=5,
            active=True,
        )
        feed = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>AI agents arrive in enterprise software</title>
              <link>https://example.com/story?utm_source=newsletter</link>
              <pubDate>Wed, 13 May 2026 10:00:00 GMT</pubDate>
              <description><![CDATA[<p>A short summary about agents.</p>]]></description>
            </item>
          </channel>
        </rss>
        """

        articles = parse_feed(feed, source, fetched_at="2026-05-14T06:00:00+00:00")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title_original, "AI agents arrive in enterprise software")
        self.assertEqual(articles[0].url, "https://example.com/story")
        self.assertEqual(articles[0].raw_excerpt, "A short summary about agents.")


if __name__ == "__main__":
    unittest.main()
