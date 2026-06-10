import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

plan_topic_ids = {
    "topic_9c9a63c2c44df11dc6",
    "topic_84c837ac4930992e12",
    "topic_d0d01b1d0755c68998",
    "topic_89a3bf38de1eec038e",
}

for post in posts:
    if post.topic_id in plan_topic_ids and post.status == "approved_for_schedule":
        print("=" * 80)
        print(f"Post ID: {post.post_id}")
        print(f"Topic ID: {post.topic_id}")
        print(f"Channel: {post.channel}")
        print(f"Title: {post.title}")
        print(f"Body (first 150 chars):\n{post.body[:150]}...")
        print(f"Source URLs: {post.source_urls}")
