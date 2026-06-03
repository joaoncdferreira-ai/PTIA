import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "final_posts.jsonl"

topics = [
    "topic_f917c693560cc81134",
    "topic_deb760708fa8dfb7d6"
]

with open(db_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        post = json.loads(line)
        if post.get("topic_id") in topics and post.get("channel") == "x":
            print("=" * 80)
            print(f"ID: {post.get('post_id')} | Topic: {post.get('topic_id')} | Status: {post.get('status')}")
            print(f"Body: {post.get('body')}")
            print("=" * 80)
