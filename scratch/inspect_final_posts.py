import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
posts_file = ROOT / "data/final_posts.jsonl"

print("Posts in approved_for_schedule:")
with open(posts_file, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        post = json.loads(line)
        if post.get("status") == "approved_for_schedule":
            print(f"ID: {post['post_id']}, Topic: {post['topic_id']}, Channel: {post['channel']}, Scheduled Time: {post['scheduled_time']}, Title: {post['title']}")
