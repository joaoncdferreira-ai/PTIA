import unittest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NewsletterSignupTests(unittest.TestCase):
    def test_homepage_uses_brevo_cloud_subscription_without_ui_embed(self):
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "site" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="ptia-newsletter-form"', html)
        self.assertNotIn("assets.mailerlite.com", html)
        self.assertNotIn("ptia-newsletter-frame", html)
        self.assertIn('name="email"', html)
        self.assertIn("newsletter_subscribe", script)
        self.assertIn("event.preventDefault()", script)
        self.assertIn("Sexta-feira, 9h00", html)


if __name__ == "__main__":
    unittest.main()
