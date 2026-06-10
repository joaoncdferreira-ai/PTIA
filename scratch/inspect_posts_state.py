import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

print(f"Total posts in DB: {len(posts)}")
print("\n--- Posts for 2026-06-10 and 2026-06-11 ---")
for post in posts:
    sch_time = post.scheduled_time or ""
    # let's look at posts scheduled for today (10th) or tomorrow (11th), or status 'rever', 'final ok', 'draft'
    if sch_time.startswith("2026-06-10") or sch_time.startswith("2026-06-11") or post.status in ["rever", "final ok", "draft"]:
        print(f"ID: {post.post_id} | Topic: {post.topic_id} | Channel: {post.channel:<10} | Status: {post.status:<12} | Time: {sch_time:<20} | Title: {post.title[:40]}")

