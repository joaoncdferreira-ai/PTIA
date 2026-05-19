import unittest

from ptia_engine.dedupe import normalize_title, normalize_url, title_similarity


class DedupeTests(unittest.TestCase):
    def test_normalize_url_removes_tracking_params(self):
        url = "https://example.com/article/?utm_source=x&gclid=y&id=123#section"

        self.assertEqual(normalize_url(url), "https://example.com/article?id=123")

    def test_title_similarity_catches_near_duplicates(self):
        left = "OpenAI launches a new coding agent for Windows"
        right = "OpenAI launches new coding agent for Windows"

        self.assertGreater(title_similarity(left, right), 0.88)

    def test_normalize_title_removes_noise(self):
        self.assertEqual(normalize_title("AI Act: What's next?"), "ai act what s next")


if __name__ == "__main__":
    unittest.main()
