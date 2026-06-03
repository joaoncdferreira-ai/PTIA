import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "final_posts.jsonl"

with open(db_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        post = json.loads(line)
        if post.get("topic_id") == "topic_15fa24ba54c6288dc7":
            print("=" * 80)
            print(json.dumps(post, indent=2, ensure_ascii=False))
            print("=" * 80)
