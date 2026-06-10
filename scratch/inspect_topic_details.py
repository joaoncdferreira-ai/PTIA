import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
posts_file = ROOT / "data/final_posts.jsonl"

with open(posts_file, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        post = json.loads(line)
        if post.get("topic_id") == "topic_bea871e53735138a7c":
            print(f"--- Channel: {post['channel']} | ID: {post['post_id']} ---")
            print(f"Title: {repr(post['title'])}")
            print(f"Body: {repr(post['body'])}")
            print(f"Status: {post['status']}")
