import importlib.util
import unittest

from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "auto_newsletter_scheduler.py"
SPEC = importlib.util.spec_from_file_location("auto_newsletter_scheduler", SCRIPT_PATH)
assert SPEC and SPEC.loader
SCHEDULER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCHEDULER)


class NewsletterSchedulerCLITests(unittest.TestCase):
    def test_cli_defaults_to_local_compilation(self):
        args = SCHEDULER.build_parser().parse_args([])

        self.assertFalse(args.live)
        self.assertFalse(args.dry_run)

    def test_live_mode_requires_explicit_flag(self):
        args = SCHEDULER.build_parser().parse_args(["--live"])

        self.assertTrue(args.live)

    def test_target_date_uses_lisbon_time(self):
        target = SCHEDULER._target_send_at("2026-06-12", hour=9, minute=0)

        self.assertEqual(target.isoformat(), "2026-06-12T09:00:00+01:00")


if __name__ == "__main__":
    unittest.main()
