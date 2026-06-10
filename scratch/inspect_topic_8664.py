import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "data" / "final_posts.jsonl"

print("--- ALL POSTS FOR TOPIC topic_866460195a3bac2212 ---")
for line in db_path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    record = json.loads(line)
    if record.get("topic_id") == "topic_866460195a3bac2212":
        print(f"ID: {record.get('post_id')} | Channel: {record.get('channel')} | Status: {record.get('status')} | Buffer ID: {record.get('buffer_post_id')} | Time: {record.get('scheduled_time')} | Title: {record.get('title')[:40]}")
