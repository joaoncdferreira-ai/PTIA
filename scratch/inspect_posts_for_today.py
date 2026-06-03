import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "final_posts.jsonl"

topics = [
    "topic_f917c693560cc81134",
    "topic_deb760708fa8dfb7d6",
    "topic_15fa24ba54c6288dc7",
    "topic_3fb5a8b3efe2408277"
]

print("=== INSPECTING TODAY'S POSTS ===")
with open(db_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        try:
            post = json.loads(line)
            if post.get("topic_id") in topics:
                print(f"Post ID: {post.get('post_id')} | Topic: {post.get('topic_id')} | Channel: {post.get('channel')} | Status: {post.get('status')}")
                if post.get("channel") == "x":
                    print(f"  X Text: {post.get('copy')}")
        except Exception as e:
            print(f"Error parsing line: {e}")
