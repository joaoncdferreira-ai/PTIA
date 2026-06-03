import json
import sys
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.dashboard import DashboardState, _final_post_text, load_final_posts

state = DashboardState(ROOT / "data")
posts = load_final_posts(state.final_posts_path)

x_post_ids = ["post_cf02ffcea47c0706f1", "post_f99b6bed5ef16caf31"]

for post_id in x_post_ids:
    post = next((p for p in posts if p.post_id == post_id), None)
    if not post:
        print(f"Post {post_id} not found!")
        continue
    print("=" * 80)
    print(f"Post ID: {post.post_id} | Channel: {post.channel}")
    print(f"Original Body:\n{post.body}")
    print("-" * 40)
    try:
        final_text = _final_post_text(post)
        print(f"Final Scheduled Text (Length {len(final_text)}):\n{final_text}")
        from ptia_engine.dashboard import _x_post_validation_issues
        issues = _x_post_validation_issues(final_text, "http://dummy.img")
        print(f"Validation issues (with dummy image): {issues}")
    except Exception as e:
        print(f"Error: {e}")
    print("=" * 80)
