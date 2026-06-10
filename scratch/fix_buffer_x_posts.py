import json
import os
import sys
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

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

from ptia_engine.buffer_api import BufferClient

# The 4 Buffer IDs for tomorrow's X posts
x_buffer_ids = [
    "6a21fab5bd9c37a0c74b6875",  # post_60ea1b18273927d434 (09:00)
    "6a21fac7c6e450c20fccce9c",  # post_b1be62faeb38e227df (13:00)
    "6a21fac936cde591228d15e3",  # post_3fc3d7e49759324e63 (16:00)
    "6a21fad973651bfe9d4a4cd9"   # post_81cca8665b434bdec2 (21:00)
]

print("=== DELETING X POSTS FROM BUFFER ===")
client = BufferClient()
for bid in x_buffer_ids:
    try:
        success = client.delete_post(bid)
        print(f"Delete Buffer ID {bid}: {'SUCCESS' if success else 'FAILED'}")
    except Exception as e:
        print(f"Error deleting Buffer ID {bid}: {e}")

print("\n=== RESETTING X POSTS IN LOCAL DATABASE ===")
db_path = ROOT / "data" / "final_posts.jsonl"

with open(db_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

reset_count = 0
target_ids = {
    "post_60ea1b18273927d434",
    "post_b1be62faeb38e227df",
    "post_3fc3d7e49759324e63",
    "post_81cca8665b434bdec2"
}

for idx, line in enumerate(lines):
    if not line.strip():
        continue
    post = json.loads(line)
    if post.get("post_id") in target_ids:
        post["status"] = "approved_for_schedule"
        post["buffer_post_id"] = None
        post["scheduled_time"] = None
        lines[idx] = json.dumps(post, ensure_ascii=False) + "\n"
        reset_count += 1
        print(f"Reset status: {post.get('post_id')} ({post.get('channel')})")

with open(db_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"Database updated. {reset_count} X posts reset to approved_for_schedule.")
