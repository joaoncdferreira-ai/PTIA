import argparse
import io
import os
import shutil
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path

from ptia_engine.cli import cmd_schedule_day
from ptia_engine.editorial_board import add_final_post, update_final_post_status


class ScheduleCliTests(unittest.TestCase):
    def setUp(self):
        self.previous_cwd = Path.cwd()
        self.root = self.previous_cwd / ".test_tmp" / uuid.uuid4().hex
        self.data_dir = self.root / "data"
        self.data_dir.mkdir(parents=True)
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def _post(self, channel: str):
        image = self.data_dir / f"{channel}.jpg"
        image.write_bytes(b"image")
        post = add_final_post(
            self.data_dir / "final_posts.jsonl",
            topic_id="topic_1",
            channel=channel,
            title=f"Post {channel}",
            body=(
                "Texto factual sobre a noticia, com contexto suficiente para publicar.\n\n"
                "A leitura editorial explica a consequencia para equipas reais.\n\n"
                "Fonte: https://example.com/source"
            ),
            hashtags="#IA",
            image_prompt="",
            source_urls=["https://example.com/source"],
            image_path=str(image),
        )
        return update_final_post_status(
            self.data_dir / "final_posts.jsonl",
            post.post_id,
            "approved_for_schedule",
            scheduled_time="2026-06-04T09:00:00+01:00",
        )

    def _args(self, **overrides):
        values = {
            "date": "2026-06-04",
            "data_dir": str(self.data_dir),
            "plan": "",
            "execution_plan": False,
            "simulate_execute": False,
            "execute_real": False,
            "publish_assets": False,
            "send_buffer": False,
            "write_site_feed": False,
            "confirm": "",
            "audit_log": "",
            "json": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_execute_real_enters_execution_gate_without_execution_plan_flag(self):
        for channel in ("linkedin", "instagram", "x", "site"):
            self._post(channel)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = cmd_schedule_day(
                self._args(execute_real=True, confirm="2026-06-04")
            )

        self.assertEqual(result, 2)
        self.assertIn("missing explicit execution flags", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
