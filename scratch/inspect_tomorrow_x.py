import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

sys_path = Path("data/final_posts.jsonl")
if sys_path.exists():
    posts = []
    with sys_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                posts.append(json.loads(line))
    
    tomorrow_x = [p for p in posts if p.get("channel") == "x" and p.get("scheduled_time", "").startswith("2026-06-05")]
    print(f"Found {len(tomorrow_x)} X posts for tomorrow:")
    for idx, p in enumerate(tomorrow_x):
        print(f"\nPost #{idx + 1} ({p.get('post_id')}):")
        print(f"  Title: {p.get('title')}")
        print(f"  Scheduled Time: {p.get('scheduled_time')}")
        print(f"  Body:\n{p.get('body')}")
        print("-" * 50)
else:
    print("data/final_posts.jsonl does not exist.")
