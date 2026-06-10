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

print("=== Checking Post Images ===")
for post in posts:
    if post.topic_id in plan_topic_ids and post.channel in {"instagram", "linkedin", "x"}:
        img_path = post.image_path or "None"
        variants = post.image_variants or {}
        has_local_variants = all(Path(v).exists() for v in variants.values()) if variants else False
        print(f"ID: {post.post_id} | Channel: {post.channel:<10} | Image Path: {img_path:<60} | Has Variants: {bool(variants)} | Local Files Exist: {has_local_variants}")
