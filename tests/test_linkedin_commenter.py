import unittest
from datetime import datetime, timedelta, timezone
from ptia_engine.linkedin_commenter import _is_profile_recently_commented_in_week

class TestLinkedinCommenter(unittest.TestCase):
    def test_empty_history(self):
        self.assertFalse(_is_profile_recently_commented_in_week([], "Defined.ai"))

    def test_no_match(self):
        history = [
            {"profile_name": "Unbabel", "status": "commented", "created_at": datetime.now(timezone.utc).isoformat()}
        ]
        self.assertFalse(_is_profile_recently_commented_in_week(history, "Defined.ai"))

    def test_match_recently(self):
        now = datetime.now(timezone.utc)
        history = [
            {
                "profile_name": "Defined.ai",
                "status": "commented",
                "created_at": (now - timedelta(days=3)).isoformat()
            }
        ]
        self.assertTrue(_is_profile_recently_commented_in_week(history, "Defined.ai"))

    def test_match_recently_draft(self):
        now = datetime.now(timezone.utc)
        history = [
            {
                "profile_name": "Defined.ai",
                "status": "draft",
                "created_at": (now - timedelta(days=5)).isoformat()
            }
        ]
        self.assertTrue(_is_profile_recently_commented_in_week(history, "Defined.ai"))

    def test_match_older_than_7_days(self):
        now = datetime.now(timezone.utc)
        history = [
            {
                "profile_name": "Defined.ai",
                "status": "commented",
                "created_at": (now - timedelta(days=8)).isoformat()
            }
        ]
        self.assertFalse(_is_profile_recently_commented_in_week(history, "Defined.ai"))

    def test_case_insensitive_and_whitespace(self):
        now = datetime.now(timezone.utc)
        history = [
            {
                "profile_name": "  Defined.ai  ",
                "status": "commented",
                "created_at": (now - timedelta(days=2)).isoformat()
            }
        ]
        self.assertTrue(_is_profile_recently_commented_in_week(history, "defined.ai"))

    def test_other_statuses_are_ignored(self):
        now = datetime.now(timezone.utc)
        history = [
            {
                "profile_name": "Defined.ai",
                "status": "rejected_by_ai",
                "created_at": (now - timedelta(days=2)).isoformat()
            },
            {
                "profile_name": "Defined.ai",
                "status": "failed",
                "created_at": (now - timedelta(days=2)).isoformat()
            }
        ]
        self.assertFalse(_is_profile_recently_commented_in_week(history, "Defined.ai"))

if __name__ == "__main__":
    unittest.main()
