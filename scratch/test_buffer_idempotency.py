import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set up paths
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Reconfigure stdout for UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Load environment
def load_dotenv() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_dotenv()

from ptia_engine.dashboard import (
    DashboardState,
    _schedule_post_in_buffer,
    load_final_posts,
)
from ptia_engine.buffer_api import BufferClient, BufferPostDetails

class TestIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmp_dir) / "data"
        self.data_dir.mkdir(parents=True)
        self.final_posts_path = self.data_dir / "final_posts.jsonl"
        self.buffer_channels_path = self.data_dir / "buffer_channels.json"
        
        # Create a mock channel config file
        self.buffer_channels_path.write_text(json.dumps({
            "channels": {
                "linkedin": "chan_linkedin_123",
                "x": "chan_x_123"
            }
        }))
        
        # Create a dummy final post
        self.dummy_post = {
            "post_id": "test_post_linkedin",
            "topic_id": "topic_test_123",
            "channel": "linkedin",
            "status": "approved_for_schedule",
            "title": "Estudo da Anthropic sobre IA",
            "body": "Um estudo recente da Anthropic revela que homens usam mais agentes de IA.",
            "source_urls": [],
            "image_path": None,
            "created_at": "2026-06-07T12:00:00Z",
            "updated_at": "2026-06-07T12:00:00Z"
        }
        self.final_posts_path.write_text(json.dumps(self.dummy_post) + "\n")
        
        self.state = DashboardState(self.data_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    @patch("ptia_engine.dashboard._ensure_public_images_for_buffer")
    @patch("ptia_engine.dashboard._sync_static_site_feed")
    @patch.object(BufferClient, "scheduled_posts")
    @patch.object(BufferClient, "create_scheduled_post")
    def test_idempotency_matches_existing_post(self, mock_create, mock_scheduled, mock_sync_feed, mock_ensure_img):
        # Configure scheduled_posts to return a post that matches the text & time
        mock_scheduled.return_value = [
            BufferPostDetails(
                id="existing_buffer_post_999",
                text="Um estudo recente da Anthropic revela que homens usam mais agentes de IA.",
                status="scheduled",
                due_at="2026-06-08T08:00:00.000Z", # UTC representation of 09:00:00+01:00
                channel_id="chan_linkedin_123",
                channel_service="linkedin"
            )
        ]
        
        # If create_scheduled_post is called, the test should fail
        mock_create.side_effect = AssertionError("create_scheduled_post should NOT be called!")

        # Call the scheduling function
        scheduled_time = "2026-06-08T09:00:00+01:00"
        result = _schedule_post_in_buffer(self.state, "test_post_linkedin", scheduled_time)

        # Assertions
        self.assertEqual(result.status, "scheduled")
        self.assertEqual(result.buffer_post_id, "existing_buffer_post_999")
        self.assertEqual(result.scheduled_time, scheduled_time)
        
        # Verify the database state was also updated
        updated_posts = load_final_posts(self.final_posts_path)
        self.assertEqual(len(updated_posts), 1)
        self.assertEqual(updated_posts[0].status, "scheduled")
        self.assertEqual(updated_posts[0].buffer_post_id, "existing_buffer_post_999")
        
        print("-> Unit Test Passed: Idempotency logic correctly reused the existing Buffer post!")

def main():
    print("=== RUNNING BUFFER IDEMPOTENCY UNIT TESTS ===")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIdempotency)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)

if __name__ == "__main__":
    main()
