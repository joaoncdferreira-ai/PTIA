import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

print("=== Scheduled or Published Posts ===")
dates = {}
for post in posts:
    if post.status in {"scheduled", "published"}:
        time_str = post.scheduled_time or "no-time"
        date_part = time_str[:10]
        dates[date_part] = dates.get(date_part, 0) + 1

for d, count in sorted(dates.items()):
    print(f"Date: {d} | Count: {count}")

print("\n=== approved_for_schedule Posts ===")
approved = {}
for post in posts:
    if post.status == "approved_for_schedule":
        # Ver o tempo agendado proposto se existir
        time_str = post.scheduled_time or "no-time"
        approved[time_str] = approved.get(time_str, 0) + 1

for t, count in sorted(approved.items()):
    print(f"Proposed Time: {t} | Count: {count}")
