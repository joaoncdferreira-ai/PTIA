import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

print("=== Posts in needs_final_review or approved_for_schedule ===")
count = 0
for post in posts:
    if post.status in {"needs_final_review", "approved_for_schedule"}:
        count += 1
        print(f"ID: {post.post_id} | Topic: {post.topic_id} | Channel: {post.channel:<10} | Status: {post.status:<25} | Title: {post.title[:50]}")

print(f"Total found: {count}")
