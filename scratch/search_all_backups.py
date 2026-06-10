import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
data_dir = ROOT / "data"

print("--- SEARCHING X POSTS IN BACKUPS ---")
for backup in sorted(data_dir.glob("final_posts.jsonl*")):
    if "bak" in backup.name or backup.name == "final_posts.jsonl":
        try:
            content = backup.read_text(encoding="utf-8")
            for line in content.splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                post_id = record.get("post_id")
                # Anthropic topic posts
                if post_id in {"post_0357526a44045c199d", "post_6a4f15d04449b4f788"}:
                    bid = record.get("buffer_post_id")
                    if bid:
                        print(f"{backup.name} | Post ID: {post_id} | Channel: {record.get('channel')} | Status: {record.get('status')} | Buffer ID: {bid}")
        except Exception as e:
            print(f"Error reading {backup.name}: {e}")
