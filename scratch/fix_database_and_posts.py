import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts, write_jsonl
from ptia_engine.services.editorial_hygiene import apply_ptia_editorial_rules

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

updated_count = 0
status_changed_count = 0

for post in posts:
    # Check if the post needs status update
    if post.status == "needs_final_review":
        post.status = "approved_for_schedule"
        status_changed_count += 1
        print(f"Moving post {post.post_id} ({post.channel}) from needs_final_review to approved_for_schedule")
    
    if post.status == "approved_for_schedule":
        # Apply editorial rules (which now includes single asterisk processing!)
        old_body = post.body
        old_title = post.title
        clean_title, clean_body = apply_ptia_editorial_rules(post.title, post.body, post.channel)
        
        # Let's also do a double check if any residual single/double asterisks are there and handle them
        if post.channel in ("instagram", "linkedin", "x"):
            import re
            clean_body = re.sub(r"\*(.*?)\*", r"\1", clean_body)
            clean_body = re.sub(r"\*\*(.*?)\*\*", r"\1", clean_body)
        elif post.channel == "site":
            import re
            clean_body = re.sub(r"\*(.*?)\*", r"<i>\1</i>", clean_body)
        
        if clean_body != old_body or clean_title != old_title:
            post.body = clean_body
            post.title = clean_title
            updated_count += 1
            print(f"Updated copy for post {post.post_id} ({post.channel})")

# Save posts back to database
write_jsonl(ROOT / "data/final_posts.jsonl", posts)
print(f"Done! Status changed: {status_changed_count}, Copy updated: {updated_count}")
