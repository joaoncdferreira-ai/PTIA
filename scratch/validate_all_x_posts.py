import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts
from ptia_engine.services.social_text import x_post_validation_issues

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

plan_topic_ids = {
    "topic_9c9a63c2c44df11dc6",
    "topic_84c837ac4930992e12",
    "topic_d0d01b1d0755c68998",
    "topic_89a3bf38de1eec038e",
}

print("=== Validating X Posts ===")
errors_count = 0
for post in posts:
    if post.topic_id in plan_topic_ids and post.channel == "x":
        issues = x_post_validation_issues(post.body, "https://mock-image-url.com/img.jpg") # mock image url to pass image check
        print("-" * 50)
        print(f"Post ID: {post.post_id} | Title: {post.title}")
        print(f"Body: {post.body}")
        if issues:
            errors_count += len(issues)
            print(f"   [ISSUES FOUND]: {'; '.join(issues)}")
        else:
            print("   [OK]: Passa em todas as validações de X.")

print(f"\nTotal errors found: {errors_count}")
