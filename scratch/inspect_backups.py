import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
data_dir = ROOT / "data"

backups = sorted(data_dir.glob("final_posts.jsonl.bak_before_schedule_*"))

for backup in backups:
    print(f"\n--- BACKUP: {backup.name} ---")
    content = backup.read_text(encoding="utf-8")
    for line in content.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("topic_id") == "topic_866460195a3bac2212":
            print(f"ID: {record.get('post_id')} | Channel: {record.get('channel')} | Status: {record.get('status')} | Buffer ID: {record.get('buffer_post_id')} | Time: {record.get('scheduled_time')} | Title: {record.get('title')[:40]}")
