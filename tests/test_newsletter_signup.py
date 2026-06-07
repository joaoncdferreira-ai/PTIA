import unittest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NewsletterSignupTests(unittest.TestCase):
    def test_homepage_posts_to_native_brevo_form_without_api_key(self):
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "site" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="ptia-newsletter-form"', html)
        self.assertNotIn("assets.mailerlite.com", html)
        self.assertIn("https://eb955785.sibforms.com/serve/", html)
        self.assertIn('name="EMAIL"', html)
        self.assertIn('name="FIRSTNAME"', html)
        self.assertIn('name="email_address_check"', html)
        self.assertIn('name="locale" value="pt"', html)
        self.assertIn('target="ptia-newsletter-frame"', html)
        self.assertNotIn('"/api/newsletter-subscribe"', script)
        self.assertNotIn("newsletter_subscribe", script)
        self.assertNotIn("BREVO_API_KEY", html + script)
        self.assertIn("Sexta-feira, 9h00", html)


if __name__ == "__main__":
    unittest.main()
