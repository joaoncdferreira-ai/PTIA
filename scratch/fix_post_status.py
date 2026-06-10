import json
from pathlib import Path

db_path = Path("data/final_posts.jsonl")

with open(db_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if not line.strip():
        continue
    post = json.loads(line)
    # The 09:00 post on June 5
    if post.get("post_id") == "post_60ea1b18273927d434":
        post["status"] = "scheduled"
        post["buffer_post_id"] = "6a21fab5bd9c37a0c74b6875"
        post["scheduled_time"] = "2026-06-05T09:00:00+01:00"
        lines[idx] = json.dumps(post, ensure_ascii=False) + "\n"
        print("Restored post_60ea1b18273927d434 to scheduled.")
        break

with open(db_path, "w", encoding="utf-8") as f:
    f.writelines(lines)
