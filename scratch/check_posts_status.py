import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
posts_file = ROOT / "data/final_posts.jsonl"

status_counts = {}
by_status = {}

with open(posts_file, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        post = json.loads(line)
        status = post.get("status")
        status_counts[status] = status_counts.get(status, 0) + 1
        by_status.setdefault(status, []).append(post)

print("Status counts:", status_counts)
print("\nPosts that are not rejected or published:")
for status, posts in by_status.items():
    if status in ("rejected", "published"):
        continue
    print(f"\n--- Status: {status} ({len(posts)} posts) ---")
    for post in posts[:10]:
        print(f"ID: {post['post_id']}, Topic: {post['topic_id']}, Channel: {post['channel']}, Title: {post['title']}, Status: {post['status']}")
