import json
import sys
from pathlib import Path

# Reconfigure stdout to use UTF-8
sys.stdout.reconfigure(encoding='utf-8')

sys_path = Path("data/linkedin_comments.jsonl")
if sys_path.exists():
    comments = []
    with sys_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                comments.append(json.loads(line))
    
    drafts = [c for c in comments if c.get("status") == "draft"]
    print(f"Total drafts found: {len(drafts)}")
    
    for idx, d in enumerate(drafts):
        print(f"\nDraft #{idx + 1}:")
        print(f"  Created At: {d.get('created_at')}")
        print(f"  Post URL: {d.get('post_url')}")
        print(f"  Profile: {d.get('profile_name')}")
        print(f"  Screenshot: {d.get('screenshot_path')}")
        print(f"  Comment Text:\n{d.get('comment_text')}")
        print("-" * 50)
else:
    print("data/linkedin_comments.jsonl does not exist.")
