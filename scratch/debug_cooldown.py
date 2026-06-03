import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "linkedin_comments.jsonl"

with open(db_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

records = []
for line in lines:
    if line.strip():
        records.append(json.loads(line))

last_record = records[-1]
last_time_str = last_record.get("created_at", "")
last_time = datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
now = datetime.now(timezone.utc)
diff = (now - last_time).total_seconds() / 60

print(f"Last record: {last_record.get('profile_name')} | Status: {last_record.get('status')}")
print(f"Last time (UTC): {last_time}")
print(f"Now (UTC): {now}")
print(f"Difference: {diff:.2f} minutes")
print(f"Cooldown active: {diff < 180}")
