import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

plan_topic_ids = {
    "topic_bea871e53735138a7c",
    "topic_9f608c63c7c00e7174",
    "topic_847f4f1387a2651eee",
    "topic_5324eae70c3277eb71",
}

for post in posts:
    if post.topic_id in plan_topic_ids and post.channel == "x":
        print("=" * 60)
        print(f"Post ID: {post.post_id}")
        print(f"Status: {post.status}")
        print(f"Title: {post.title}")
        print(f"Body:\n{post.body}")
