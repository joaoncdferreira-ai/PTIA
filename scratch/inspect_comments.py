import json
from pathlib import Path
from collections import Counter

sys_path = Path("data/linkedin_comments.jsonl")
if sys_path.exists():
    comments = []
    with sys_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                comments.append(json.loads(line))
    print(f"Total entries in linkedin_comments.jsonl: {len(comments)}")
    
    # Group by status
    statuses = Counter(c.get("status") for c in comments)
    print("\nEntries by status:")
    for k, v in statuses.items():
        print(f"  - {k}: {v}")
        
    print("\nRecent 10 entries:")
    for c in comments[-10:]:
        print(f"  - ID: {c.get('comment_id')} | Status: {c.get('status')} | Date: {c.get('created_at')} | Author: {c.get('author_name')} | Url: {c.get('post_url')}")
        body = c.get('comment_body', '') or c.get('body', '')
        print(f"    Body: {body[:100]}...")
else:
    print("data/linkedin_comments.jsonl does not exist.")
