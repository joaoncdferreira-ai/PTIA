import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "final_posts.jsonl"

topics = [
    "topic_15fa24ba54c6288dc7", # 16:00
    "topic_3fb5a8b3efe2408277"  # 21:00
]

with open(db_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        post = json.loads(line)
        if post.get("topic_id") in topics:
            print("=" * 80)
            print(f"ID: {post.get('post_id')} | Channel: {post.get('channel')} | Status: {post.get('status')}")
            print(f"Title: {post.get('title')}")
            print(f"Image Path: {post.get('image_path')}")
            print("Content:")
            # Note: FinalPost uses 'body' or 'copy' depending on models. Let's print the dict keys and values
            for k in ["copy", "body", "text", "content"]:
                if k in post:
                    print(f"  {k}: {post[k]}")
            print("-" * 80)
