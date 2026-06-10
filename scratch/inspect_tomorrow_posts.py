import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "data" / "final_posts.jsonl"

print("--- POSTS FOR 2026-06-07 ---")
if db_path.exists():
    for line in db_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        sch_time = record.get("scheduled_time", "")
        if sch_time.startswith("2026-06-07"):
            print(f"ID: {record.get('post_id')} | Channel: {record.get('channel')} | Time: {sch_time} | Status: {record.get('status')} | Image: {record.get('image_path')} | Buffer ID: {record.get('buffer_post_id')} | Title: {record.get('title')[:40]}")
