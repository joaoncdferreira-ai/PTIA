import unittest

from ptia_engine.models import TrendSignal
from ptia_engine.trend_radar import _ptia_angle, _why_it_worked, trend_to_markdown


class TrendRadarTests(unittest.TestCase):
    def test_trend_markdown_contains_ptia_angle(self):
        signal = TrendSignal(
            signal_id="hn_1",
            platform="hacker_news",
            title="Show HN: AI agents for developers",
            url="https://example.com",
            discussion_url="https://news.ycombinator.com/item?id=1",
            score=200,
            comments=80,
            engagement_score=360,
            topic="agents",
        )
        signal.why_it_worked = _why_it_worked(signal)
        signal.ptia_angle = _ptia_angle(signal)

        markdown = trend_to_markdown([signal])

        self.assertIn("Porque funcionou", markdown)
        self.assertIn("Angulo PTIA", markdown)
        self.assertIn("equipas portuguesas", markdown)


if __name__ == "__main__":
    unittest.main()
